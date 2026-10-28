"""File import changes, restart recovery and access boundaries without remote accounts."""
import asyncio
import hashlib
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest

from pka import service as service_module
from pka.config import LIMITS
from pka.connectors.base import SourceError
from pka.connectors.github import GitHubSource
from pka.connectors.local import LocalSource, local_selection
from pka.import_cache import FileCheckpoints
from pka.index import Index
from pka.service import Service
from test_core import github_transport


def run(work):
    return asyncio.run(work)


class ChangingFiles:
    def __init__(self):
        self.files = {'README.md':'# Project\nA small project.\n', 'app.py':'VALUE = 1\n', 'old.py':'REMOVED = True\n'}
        self.calls, self.access_checks = [], 0
        self.fail = self.on_read = None
        self.denied = False
        self.excluded = set()

    def head(self):
        return hashlib.sha256(repr(sorted(self.files.items())).encode()).hexdigest()

    async def begin_snapshot(self):
        if self.denied:
            raise SourceError('access_denied', 'Access revoked.')
        return {'commit':self.head(), 'entries':len(self.files), 'tree_incomplete':False}

    async def list_files(self, cursor=0):
        return {'files':[{'path':p, 'size':len(t.encode()), 'sha':hashlib.sha256(t.encode()).hexdigest(),
                          'skip':'excluded' if p in self.excluded else ''} for p,t in self.files.items()], 'next_cursor':None}

    async def check_access(self, commit=''):
        self.access_checks += 1
        if self.denied:
            raise SourceError('access_denied', 'Access revoked.')
        return {'head':self.head()}

    async def read_file(self, path):
        self.calls.append(path)
        if path == self.fail:
            raise SourceError('network', 'Temporary connection failure.')
        text = self.files[path]
        if self.on_read:
            self.on_read(path)
        return {'text':text, 'bytes':len(text.encode()), 'sha':hashlib.sha256(text.encode()).hexdigest()}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_READ_CONCURRENCY', '1')
    monkeypatch.setenv('PKA_LOG_DIR', str(tmp_path / 'logs'))
    index = Index(tmp_path / 'index.sqlite3')
    index.configure({'repo':'acme/shop', 'branch':'main'})
    source = ChangingFiles()

    @asynccontextmanager
    async def factory(cfg, demo=False):
        yield source

    return Service(index, connector_factory=factory), source


def cache_rows(index):
    with index.db() as db:
        return [dict(row) for row in db.execute('SELECT * FROM file_checkpoints')]


def test_refresh_fetches_changes_drops_deleted_and_repins_citations(setup):
    svc, source = setup
    run(svc.scan())
    assert svc.index.active_scan()['fetched'] == 3
    first_commit = svc.index.active_scan()['commit']
    source.calls.clear()
    source.files['app.py'] = 'VALUE = 2\n'
    del source.files['old.py']
    source.files['new.py'] = 'ADDED = True\n'
    run(svc.scan())
    scan = svc.index.active_scan()
    assert (scan['read'], scan['reused'], scan['fetched']) == (3, 1, 2)
    assert source.calls == ['app.py', 'new.py']
    assert scan['commit'] != first_commit and source.access_checks == 2
    assert 'old.py' not in svc.index.indexed_paths(scan['id'])
    assert {r['path'] for r in cache_rows(svc.index)} == set(source.files)
    results = svc.index.search('VALUE', scan)
    assert results and all(scan['commit'] in r['url'] for r in results)


def test_unchanged_refresh_fetches_nothing_and_still_checks_access(setup):
    svc, source = setup
    run(svc.scan())
    source.calls.clear()
    run(svc.scan())
    assert source.calls == [] and source.access_checks == 2
    assert svc.index.active_scan()['reused'] == 3


@pytest.mark.parametrize('stop', ['network', 'cancel', 'restart'])
def test_retry_after_stop_reuses_durable_files_without_publishing_partial_work(setup, stop):
    svc, source = setup
    if stop == 'network':
        source.fail = 'app.py'
        run(svc.scan())
    elif stop == 'cancel':
        source.on_read = lambda path: svc.cancel.set()
        run(svc.scan())
    else:
        original = source.read_file
        async def read(path):
            if path == 'app.py':
                raise asyncio.CancelledError()
            return await original(path)
        source.read_file = read
        with pytest.raises(asyncio.CancelledError):
            run(svc.scan())
        source.read_file = original
    assert svc.index.active_scan() is None
    assert len(cache_rows(svc.index)) == 1
    source.fail = source.on_read = None
    source.calls.clear()
    # Recreate the database/client just like a process restart.
    recovered = Service(Index(svc.index.path), connector_factory=svc.connector_factory)
    run(recovered.scan())
    assert source.calls == ['app.py', 'old.py']
    assert recovered.index.active_scan()['reused'] == 1


def test_retry_uses_new_manifest_when_branch_changed_during_interruption(setup):
    svc, source = setup
    source.fail = 'app.py'
    run(svc.scan())
    source.fail = None
    source.calls.clear()
    source.files['README.md'] = '# Changed README\n'
    run(svc.scan())
    assert source.calls == list(source.files)
    assert svc.index.active_scan()['reused'] == 0


@pytest.mark.parametrize('point', ['begin', 'publish'])
def test_revocation_purges_checkpoints_and_never_publishes_reused_text(setup, point):
    svc, source = setup
    run(svc.scan())
    if point == 'begin':
        source.denied = True
    else:
        source.files['new.py'] = 'CHANGED = True\n'
        source.on_read = lambda path: setattr(source, 'denied', True)
    run(svc.scan())
    assert not cache_rows(svc.index)
    assert svc.index.active_scan() is None
    assert svc.index.latest()['error_code'] == 'access_denied'


def test_new_credential_identity_cannot_reuse_old_checkpoints(setup, monkeypatch):
    svc, source = setup
    monkeypatch.setattr(service_module.credentials, 'source_fingerprint', lambda _: 'first')
    run(svc.scan())
    source.calls.clear()
    monkeypatch.setattr(service_module.credentials, 'source_fingerprint', lambda _: 'second')
    run(svc.scan())
    assert source.calls == list(source.files)
    assert svc.index.active_scan()['reused'] == 0


@pytest.mark.parametrize('selection', [{'repo':'acme/other'}, {'branch':'other'}])
def test_changed_selection_clears_checkpoints(setup, selection):
    svc, source = setup
    run(svc.scan())
    svc.index.configure(selection)
    assert not cache_rows(svc.index)


def test_cached_file_obeys_new_exclusion_and_scan_limit(setup, monkeypatch):
    svc, source = setup
    run(svc.scan())
    source.excluded = {'app.py'}
    monkeypatch.setattr(service_module, 'LIMITS', replace(LIMITS, max_files=1))
    run(svc.scan())
    scan = svc.index.active_scan()
    assert scan['read'] == scan['reused'] == 1 and scan['status'] == 'partial'
    assert svc.index.indexed_paths(scan['id']) == ['README.md']
    assert 'app.py' not in {r['path'] for r in cache_rows(svc.index)}


def test_stale_check_clears_search_but_retains_safe_resume_data(setup):
    svc, source = setup
    run(svc.scan())
    scan = svc.index.active_scan()
    source.files['new.py'] = 'ADDED = True\n'
    with pytest.raises(SourceError, match='branch changed'):
        run(svc.check_external_access(scan, names=('github',)))
    assert svc.index.active_scan() is None and len(cache_rows(svc.index)) == 3
    source.calls.clear()
    run(svc.scan())
    assert source.calls == ['new.py']


def test_revocation_during_pending_read_cannot_recreate_checkpoints(setup):
    svc, source = setup
    source.on_read = lambda path: svc.index.invalidate()
    run(svc.scan())
    assert not cache_rows(svc.index)
    assert svc.index.active_scan() is None


def test_checkpoints_are_private_to_account_database(setup, tmp_path):
    svc, source = setup
    run(svc.scan())
    other = Index(tmp_path / 'other.sqlite3')
    cfg = svc.index.settings()
    other.configure(cfg)
    assert FileCheckpoints(other, 'repository', cfg['repo'], cfg['branch'], '').hashes() == {}


def test_github_budget_counts_only_missing_blobs():
    tree = [{'path':f'mod{i}.py', 'type':'blob', 'mode':'100644', 'size':30, 'sha':str(i)*40} for i in range(9)]
    def small(request):
        if request.url.path == '/rate_limit':
            return httpx.Response(200, json={'resources':{'core':{'limit':60,'remaining':3,'reset':0,'used':57}}})
        if '/git/trees/' in request.url.path:
            return httpx.Response(200, json={'truncated':False, 'tree':tree})
    transport, requests = github_transport(small)
    source = GitHubSource('acme/shop', 'main', transport=transport)
    snap = run(source.begin_incremental({e['path']:e['sha'] for e in tree[:7]}))
    assert snap['requests_needed'] == 2
    assert not any('/git/blobs/' in r.url.path for r in requests)


@pytest.mark.parametrize('additional', [False, True])
def test_real_local_hashes_reuse_only_unchanged_content(setup, tmp_path, additional):
    svc, source = setup
    folder = tmp_path / 'local'
    folder.mkdir()
    (folder / 'first.py').write_text('VALUE = 1\n')
    (folder / 'second.py').write_text('SECOND = 2\n')
    repo, branch = local_selection(str(folder))
    calls = []
    class CountedLocal(LocalSource):
        async def read_file(self, path):
            calls.append(path)
            return await super().read_file(path)
    @asynccontextmanager
    async def factory(cfg, demo=False):
        yield CountedLocal(cfg['repo'])
    if additional:
        run(svc.scan())
        svc.index.configure_source('local', {'repo':repo, 'path':str(folder)})
    else:
        svc.index.configure({'repo':repo, 'branch':branch})
    svc.connector_factory = factory
    work = svc.read_local if additional else svc.scan
    run(work())
    calls.clear()
    (folder / 'second.py').write_text('SECOND = 3\n')
    run(work())
    report = svc.index.source_import('local')['report'] if additional else svc.index.active_scan()
    assert calls == ['second.py']
    assert (report['reused'], report['fetched']) == (1, 1)


@pytest.mark.parametrize('same_model', [True, False])
def test_refresh_reuses_vectors_only_for_unchanged_inputs_and_same_model(setup, monkeypatch, same_model):
    from pka import embed
    svc, source = setup
    run(svc.scan())
    scan = svc.index.active_scan()
    monkeypatch.setenv('PKA_EMBED_MODEL', 'model-one')
    svc.index.prepare_vectors(scan['id'], embed.signature())
    svc.index.save_vectors(scan['id'], [(r['id'], [1.0, 0.0]) for r in svc.index.unembedded(scan['id'])])
    source.files['app.py'] = 'VALUE = 3\n'
    if not same_model:
        monkeypatch.setenv('PKA_EMBED_MODEL', 'model-two')
    # Observe what activation retained before the embedding phase would fill gaps.
    async def inspect_vectors(scan_id):
        return svc.index.embedded(scan_id)
    svc.embed_snapshot = inspect_vectors
    run(svc.scan())
    scan = svc.index.active_scan()
    assert scan['reused_vectors'] == (2 if same_model else 0)
    assert {r['path'] for r in svc.index.unembedded(scan['id'])} == ({'app.py'} if same_model else set(source.files))


def test_incremental_flow_through_real_mcp_process(setup):
    svc, _ = setup
    # Uses only built-in demo files, through the real MCP client/server protocol.
    svc = Service(svc.index, demo=True)
    run(svc.scan())
    assert svc.index.active_scan()['fetched'] == 3
    run(svc.scan())
    assert svc.index.active_scan()['reused'] == 3
    assert svc.index.active_scan()['fetched'] == 0


@pytest.mark.parametrize('same_model', [True, False])
def test_local_refresh_reuses_meaning_index_and_updates_citations(setup, tmp_path, monkeypatch, same_model):
    from pka import embed
    svc, source = setup
    run(svc.scan())
    folder = tmp_path / 'local'
    folder.mkdir()
    for name, text in [('keep.py', 'KEEP = 1'), ('edit.py', 'EDIT = 1'), ('remove.py', 'REMOVED = 1')]:
        (folder / name).write_text(text)
    repo, _ = local_selection(str(folder))
    svc.index.configure_source('local', {'repo':repo, 'path':str(folder)})

    @asynccontextmanager
    async def factory(cfg, demo=False):
        yield LocalSource(cfg['repo']) if cfg['repo'].startswith('local:') else source
    svc.connector_factory = factory
    monkeypatch.setenv('PKA_EMBED_MODEL', 'fixture-one')
    calls = []
    async def vectors(texts):
        if texts != list(embed.PROBES):
            calls.extend(texts)
        return [[1.0, 0.0] for _ in texts]
    monkeypatch.setattr(embed, 'vectors', vectors)
    run(svc.read_local())
    assert len([text for text in calls if text.startswith('local://')]) == 3
    old_snapshot = svc.index.source_import('local')['snapshot']
    calls.clear()
    (folder / 'edit.py').write_text('EDIT = 2')
    (folder / 'remove.py').unlink()
    (folder / 'new.py').write_text('NEW = 1')
    if not same_model:
        monkeypatch.setenv('PKA_EMBED_MODEL', 'fixture-two')
    report = run(svc.read_local())
    snapshot = svc.index.source_import('local')['snapshot']
    assert snapshot != old_snapshot
    assert report['reused_vectors'] == (1 if same_model else 0)
    local_calls = [text for text in calls if text.startswith('local://')]
    assert len(local_calls) == (2 if same_model else 3)
    assert all('remove.py' not in text for text in calls)
    if same_model:
        assert all('keep.py' not in text for text in calls)
    with svc.index.db() as db:
        rows = db.execute("SELECT c.path,c.text,c.url FROM chunks c JOIN vectors v ON c.id=v.chunk_id WHERE c.path LIKE 'local://%'").fetchall()
    assert len(rows) == 3
    assert all(snapshot in row['path'] and old_snapshot not in row['url'] for row in rows)
    assert not any('REMOVED' in row['text'] for row in rows)
    calls.clear()
    assert run(svc.read_local())['reused_vectors'] == 3
    assert calls == [], 'An unchanged folder must not re-embed its document text'
