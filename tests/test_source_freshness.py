"""Regression checks for source refresh and permission boundaries; no live accounts."""
import asyncio
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from pka import credentials
from pka.config import now
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource, COMMIT
from pka.connectors.jira import JiraSource, issue_block
from pka.connectors.slack import SlackSource, transcript
from pka.index import Index
from pka.service import Service
from pka.web import create_app


def run(coro):
    return asyncio.run(coro)


class Sources(FixtureSource):
    def __init__(self):
        self.checked = []
        self.denied = None
        self.after_read = None

    async def jira_begin_read(self):
        return {'project':'ENG', 'issues':1, 'blocks':1}

    async def jira_issues(self, cursor=0):
        if self.after_read:
            self.after_read()
        return {'blocks':[issue_block('https://acme.atlassian.net',
                {'key':'ENG-1', 'fields':{'summary':'Login requires password verification'}})],
                'next_cursor':None}

    async def slack_messages(self, channel_id):
        if self.after_read:
            self.after_read()
        return [{'ts':'1700000000.0', 'user':'U1', 'text':'Login requires password verification'}]

    async def jira_check_issues_access(self, issue_keys, snapshots=None):
        self.checked.append(('jira', issue_keys))
        if self.denied:
            raise self.denied
        return {'checked':len(issue_keys)}

    async def slack_check_channel_access(self, channel_id):
        self.checked.append(('slack', channel_id))
        if self.denied:
            raise self.denied
        return {'channel':channel_id, 'readable':True}


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, 'ENV_PATH', tmp_path/'unused.env')
    for name in ('JIRA_SITE', 'JIRA_EMAIL', 'JIRA_API_TOKEN', 'SLACK_USER_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    source = Sources()
    @asynccontextmanager
    async def factory(settings, demo=False):
        yield source
    index = Index(tmp_path/'test.sqlite3')
    index.configure({'repo':'acme/shop','branch':'main'})
    async def model(question, sources):
        return {'statements':[{'text':'Login requires password verification.',
                              'source_ids':[sources[0]['source_id']]}], 'missing_information':''}
    svc = Service(index, connector_factory=factory, generator=model)
    run(svc.scan())
    index.configure_source('jira', {'project':'ENG'})
    index.configure_slack({'workspace':'acme','channels':[{'id':'C1','name':'eng'}]})
    return index, svc, source, factory


def import_one(state, name):
    index, svc, _, _ = state
    return run(svc.read_jira('ENG') if name == 'jira' else
               svc.read_slack('acme', index.settings()['slack']['channels']))


def cache(index):
    scan = index.active_scan()
    answer = index.record_answer(scan['id'], 'login', {'secret':'old answer'}, 0)
    index.save_overview(scan['id'], COMMIT, {'secret':'old overview'})
    return answer


@pytest.mark.parametrize('name', ['jira','slack'])
def test_refresh_clears_derived_content_and_persists_read_time(state, name):
    index, svc, _, _ = state
    answer = cache(index)
    index.vocabulary(index.active_scan()['id'])
    report = import_one(state, name)
    assert index.overview(COMMIT) is None
    assert not index.feedback(answer, 'correct', 'sufficient')
    assert index._vocab is None
    assert index.settings()[name]['read_at'] == report['read_at']
    assert index.source_import(name)['report'] == report
    assert index.source_blocks(index.active_scan()['id'], name+'/') == 1
    assert index.code_paths(index.active_scan()['id'])
    run(svc.check_external_access(index.active_scan()))


@pytest.mark.parametrize('name', ['jira','slack'])
def test_scope_change_removes_old_content_without_a_refresh(state, name):
    index, _, _, _ = state
    import_one(state, name)
    answer = cache(index)
    previous = index.settings()[name]
    index.configure_source(name, previous)
    assert index.overview(COMMIT), 'saving the same scope must not destroy its cache'
    changed = {**previous, 'project':'OPS'} if name == 'jira' else {**previous, 'channels':[]}
    index.configure_source(name, changed)
    assert index.source_blocks(index.active_scan()['id'], name+'/') == 0
    assert index.overview(COMMIT) is None
    assert not index.feedback(answer, 'correct', 'sufficient')
    assert not index.settings()[name].get('read_at')
    assert index.source_import(name) is None


def test_same_commit_rescan_drops_overview_that_used_external_sources(state):
    index, svc, _, _ = state
    import_one(state, 'jira')
    cache(index)
    run(svc.scan())
    assert index.overview(COMMIT) is None
    assert not index.settings()['jira'].get('read_at')
    assert index.source_import('jira') is None


@pytest.mark.parametrize('name', ['jira','slack'])
@pytest.mark.parametrize('code', ['access_denied','network','rate_limit'])
def test_failed_permission_check_never_generates_an_answer(state, name, code):
    index, svc, source, _ = state
    import_one(state, name)
    cache(index)
    source.denied = SourceError(code, 'Access unavailable')
    called = []
    async def model(*args):
        called.append(True)
        raise AssertionError('Must not reach the model')
    svc.generator = model
    with pytest.raises(SourceError):
        run(svc.ask('How does login work?'))
    assert not called
    assert source.checked
    assert bool(index.source_blocks(index.active_scan()['id'], name+'/')) == (code != 'access_denied')
    assert bool(index.overview(COMMIT)) == (code != 'access_denied')
    assert index.code_paths(index.active_scan()['id'])


@pytest.mark.parametrize('name', ['jira','slack'])
def test_changed_credentials_discard_saved_source(state, name, monkeypatch):
    index, svc, _, _ = state
    import_one(state, name)
    cache(index)
    monkeypatch.setenv('JIRA_API_TOKEN' if name == 'jira' else 'SLACK_USER_TOKEN', 'new-account-token')
    svc.sync_source_credentials()
    assert not index.source_blocks(index.active_scan()['id'], name+'/')
    assert index.overview(COMMIT) is None
    assert not index.settings()[name].get('read_at')


@pytest.mark.parametrize('name', ['jira', 'slack'])
@pytest.mark.parametrize('endpoint', ['/api/overview','/api/features','/api/features/login'])
def test_cached_and_derived_views_recheck_external_access(state, endpoint, name):
    index, _, source, factory = state
    import_one(state, name)
    cache(index)
    source.denied = SourceError('access_denied', 'Issue no longer accessible')
    app = create_app(False, index.path, connector_factory=factory)
    with TestClient(app, base_url='http://localhost:8000') as client:
        response = client.get(endpoint, headers={'X-PKA-Request':'1'})
    assert response.status_code == 409
    assert 'old overview' not in response.text
    assert source.checked == [('jira', ['ENG-1'])] if name == 'jira' else source.checked == [('slack', 'C1')]
    assert index.overview(COMMIT) is None


def test_legacy_external_content_requires_reimport(state):
    index, svc, _, _ = state
    index.replace_slack(index.active_scan()['id'], transcript('eng',
        [{'ts':'1','text':'old login discussion'}], 'acme', 'C1'))
    with pytest.raises(SourceError, match='Read that source again'):
        run(svc.check_external_access(index.active_scan()))
    assert not index.slack_blocks(index.active_scan()['id'])


def test_permission_success_reaches_model_and_does_not_expose_fingerprint(state):
    index, svc, source, _ = state
    import_one(state, 'jira')
    import_one(state, 'slack')
    answer = run(svc.ask('How does login work?'))
    assert answer['statements'] and answer['sources']
    assert ('jira', ['ENG-1']) in source.checked
    assert ('slack', 'C1') in source.checked
    assert 'identity' not in str(index.settings())
    assert 'identity' not in str(answer)


def test_revocation_during_model_call_cannot_recreate_the_cache(state):
    index, svc, _, _ = state
    import_one(state, 'jira')
    async def revoked(question, sources):
        index.discard_source('jira')
        return {'statements':[], 'missing_information':'old secret'}
    svc.generator = revoked
    with pytest.raises(SourceError, match='changed during'):
        run(svc.ask('How does login work?'))
    with index.db() as db:
        assert db.execute('SELECT COUNT(*) FROM answers').fetchone()[0] == 0


@pytest.mark.parametrize('name', ['jira','slack'])
def test_new_import_clears_old_cancellation_but_last_page_cancel_is_not_committed(state, name):
    index, svc, source, _ = state
    svc.cancel.set()
    first = import_one(state, name)
    assert not svc.cancel.is_set()
    previous = index.source_import(name)
    source.after_read = svc.cancel.set
    with pytest.raises(SourceError, match='cancelled'):
        import_one(state, name)
    assert index.source_import(name) == previous
    assert index.settings()[name]['read_at'] == first['read_at']


def test_overview_cannot_save_after_source_revocation(state):
    index, svc, _, _ = state
    import_one(state, 'jira')
    async def revoked(question, sources):
        index.discard_source('jira')
        return {'statements':[], 'missing_information':'old secret'}
    svc.generator = revoked
    with pytest.raises(SourceError, match='changed during'):
        run(svc.build_overview())
    assert index.overview(COMMIT) is None


def test_jira_access_checks_issue_permissions_and_pages():
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/myself'):
            return httpx.Response(200, json={'accountId':'reader'})
        assert request.method == 'GET'
        assert request.url.path.endswith('/search/jql')
        assert 'project = "ENG"' in request.url.params['jql']
        if 'nextPageToken' not in request.url.params:
            return httpx.Response(200, json={'issues':[{'key':'ENG-1'}], 'nextPageToken':'next'})
        return httpx.Response(200, json={'issues':[{'key':'ENG-2'}], 'isLast':True})
    source = JiraSource('https://acme.atlassian.net','reader@example.com','token',httpx.MockTransport(handler))
    assert run(source.check_issues_access('ENG', ['ENG-1','ENG-2'])) == {'checked':2}
    assert len(calls) == 3
    with pytest.raises(SourceError) as denied:
        run(source.check_issues_access('ENG', ['ENG-3']))
    assert denied.value.code == 'access_denied'
    before = len(calls)
    with pytest.raises(SourceError):
        run(source.check_issues_access('ENG', ['OPS-1']))
    with pytest.raises(SourceError):
        run(source.check_issues_access('ENG', ['ENG-1" OR 1=1']))
    assert len(calls) == before


def test_slack_access_probes_history_without_returning_the_message():
    def handler(request):
        assert request.method == 'GET'
        assert request.url.path == '/api/conversations.history'
        assert request.url.params['channel'] == 'C1' and request.url.params['limit'] == '1'
        return httpx.Response(200, json={'ok':True,'messages':[{'text':'never return this probe'}]})
    source = SlackSource('token', httpx.MockTransport(handler))
    assert run(source.check_channel_access('C1')) == {'channel':'C1','readable':True}


@pytest.mark.parametrize('error', ['token_revoked','not_in_channel','missing_scope','channel_not_found'])
def test_slack_permission_failures_are_distinguished_from_temporary_errors(error):
    source = SlackSource('token', httpx.MockTransport(
        lambda r: httpx.Response(200, json={'ok':False,'error':error})))
    with pytest.raises(SourceError) as denied:
        run(source.check_channel_access('C1'))
    assert denied.value.code == 'access_denied'


def test_import_timestamp_is_exposed_by_status_after_restart(state):
    index, _, _, factory = state
    report = import_one(state, 'jira')
    app = create_app(False, index.path, connector_factory=factory)
    h = {'X-PKA-Request':'1'}
    with TestClient(app, base_url='http://localhost:8000') as client:
        client.post('/api/config', headers=h, json={'repo':'acme/shop','branch':'main'})
        status = client.get('/api/status', headers=h).json()
        history = client.get('/api/import-history', headers=h).json()
    assert status['settings']['jira']['read_at'] == report['read_at']
    assert history['jira_read_at'] == report['read_at']


def test_permission_tools_cannot_widen_the_server_scope(monkeypatch):
    from pka import mcp_server
    monkeypatch.setattr(mcp_server, 'SLACK_CHANNELS', {'C1'})
    monkeypatch.setattr(mcp_server, 'JIRA_PROJECT', 'ENG')
    reader = JiraSource('https://acme.atlassian.net', 'reader@example.com', 'token',
                        httpx.MockTransport(lambda r: pytest.fail('Out-of-scope request reached the network')))
    monkeypatch.setattr(mcp_server, 'jira', lambda: reader)
    assert run(mcp_server.slack_check_channel_access('C2'))['code'] == 'scope'
    assert run(mcp_server.jira_check_issues_access(['OPS-1']))['code'] == 'scope'


def test_partial_slack_import_reports_missing_channels_and_removes_their_old_content(state):
    index, svc, source, _ = state
    channels = [{'id':'C1','name':'eng'}, {'id':'C2','name':'private'}]
    index.configure_slack({'workspace':'acme','channels':channels})
    run(svc.read_slack('acme', channels))
    cache(index)
    original = source.slack_messages
    async def partial(channel_id):
        if channel_id == 'C2':
            raise SourceError('access_denied', 'No longer a member')
        return await original(channel_id)
    source.slack_messages = partial
    report = run(svc.background('slack', svc.read_slack('acme', channels)))
    assert report['failed'] == 1
    assert 'partial' in svc.job_error
    assert 'slack/private' not in index.indexed_paths(index.active_scan()['id'])
    assert index.overview(COMMIT) is None
    assert index.settings()['slack']['import_report']['failed'] == 1


@pytest.mark.parametrize('action', ['invalidate','repository'])
def test_removed_snapshot_does_not_advertise_old_source_timestamps(state, action):
    index, _, _, _ = state
    import_one(state, 'jira')
    if action == 'invalidate':
        index.invalidate()
    else:
        index.configure({'repo':'acme/another','branch':'main'})
    assert not index.settings()['jira'].get('read_at')
    assert index.source_import('jira') is None


def test_failed_jira_import_preserves_last_successful_snapshot_and_timestamp(state):
    index, svc, source, _ = state
    report = import_one(state, 'jira')
    cache(index)
    async def failed(cursor=0):
        raise SourceError('network', 'Jira is temporarily unavailable')
    source.jira_issues = failed
    assert run(svc.background('jira', svc.read_jira('ENG'))) is None
    assert svc.job_error and svc.jira_progress is None
    assert index.settings()['jira']['read_at'] == report['read_at']
    assert index.source_blocks(index.active_scan()['id'], 'jira/') == 1
    assert index.overview(COMMIT)


def test_import_failure_rolls_back_both_data_and_cache_invalidation(state):
    index, _, _, _ = state
    import_one(state, 'jira')
    cache(index)
    previous = index.source_import('jira')
    with pytest.raises(KeyError):
        index.replace_source(index.active_scan()['id'], 'jira/', [{'path':'jira/ENG-2'}])
    assert index.source_import('jira') == previous
    assert index.overview(COMMIT)
    assert 'jira/ENG-1' in index.indexed_paths(index.active_scan()['id'])


def test_revision_survives_restart_and_is_shared_by_index_instances(state):
    index, _, _, _ = state
    previous = index.revision
    reopened = Index(index.path)
    assert reopened.revision == previous
    import_one(state, 'jira')
    assert reopened.revision == index.revision == previous + 1
    assert Index(index.path).revision == previous + 1
    reopened.vocabulary(index.active_scan()['id'])
    index.replace_source(index.active_scan()['id'], 'jira/', [
        issue_block('https://acme.atlassian.net', {'key':'ENG-2', 'fields':{'summary':'Zebraprocessor'}})])
    assert 'zebraprocessor' in reopened.vocabulary(index.active_scan()['id'])


def test_revision_and_caches_roll_back_when_metadata_write_fails(state):
    index, _, _, _ = state
    import_one(state, 'jira')
    answer = cache(index)
    previous = index.revision
    # Fails after _changed, so even the version increment must roll back.
    with pytest.raises(KeyError):
        index.replace_source(index.active_scan()['id'], 'jira/', [], {'report':{}})
    assert index.revision == Index(index.path).revision == previous
    assert index.overview(COMMIT)
    assert index.feedback(answer, 'correct', 'sufficient')
    assert index.source_blocks(index.active_scan()['id'], 'jira/') == 1


@pytest.mark.parametrize('name', ['jira', 'slack'])
def test_refresh_replaces_edited_and_deleted_text_and_next_answer(state, name):
    index, svc, source, _ = state
    import_one(state, name)
    scan = index.active_scan()
    answer = cache(index)
    previous = index.revision
    with index.db() as db:
        cid = db.execute('SELECT id FROM chunks WHERE path LIKE ?', (name+'/%',)).fetchone()[0]
        db.execute('INSERT INTO vectors VALUES(?,?,?)', (cid, scan['id'], b'old vector'))
    async def edited_issues(cursor=0):
        return {'blocks':[issue_block('https://acme.atlassian.net',
            {'key':'ENG-2', 'fields':{'summary':'Zebraprocessor uses neutronqueue'}})], 'next_cursor':None}
    async def edited_messages(channel_id):
        return [{'ts':'1700000001.0', 'user':'U1', 'text':
                 'Zebraprocessor uses neutronqueue. The team confirmed this configuration for processing incoming requests.'}]
    source.jira_issues = edited_issues
    source.slack_messages = edited_messages
    import_one(state, name)
    assert index.revision == previous + 1
    with index.db() as db:
        assert not db.execute('SELECT 1 FROM vectors WHERE chunk_id=?', (cid,)).fetchone()
        text = '\n'.join(r[0] for r in db.execute('SELECT text FROM chunks WHERE path LIKE ?', (name+'/%',)))
        assert 'password verification' not in text and 'neutronqueue' in text
    assert not index.feedback(answer, 'correct', 'sufficient')
    assert index.overview(COMMIT) is None
    async def answer_from_refreshed_source(question, sources):
        evidence = next(s for s in sources if 'neutronqueue' in s['text'])
        return {'statements':[{'text':'Zebraprocessor uses neutronqueue.',
                              'source_ids':[evidence['source_id']]}], 'missing_information':''}
    svc.generator = answer_from_refreshed_source
    result = run(svc.ask('What does Zebraprocessor use?'))
    assert any('neutronqueue' in s['text'] for s in result['statements'])
    assert any(s['path'].startswith(name+'/') for s in result['sources'])
    async def empty_issues(cursor=0):
        return {'blocks':[], 'next_cursor':None}
    async def empty_messages(channel_id):
        return []
    source.jira_issues = empty_issues
    source.slack_messages = empty_messages
    import_one(state, name)
    assert index.source_blocks(scan['id'], name+'/') == 0
    assert 'neutronqueue' not in index.vocabulary(scan['id'])


def test_starting_scan_invalidates_open_answers_before_network_completes(state):
    index, _, _, _ = state
    answer = cache(index)
    previous = index.revision
    index.new_scan({'status':'running'})
    assert index.revision == previous + 1
    assert index.active_scan() is None
    assert index.overview(COMMIT) is None
    assert not index.feedback(answer, 'correct', 'sufficient')


def test_jira_recheck_covers_comment_visibility_not_only_issue_visibility():
    issue = {'key':'ENG-1', 'fields':{'summary':'Login', 'comment':{'total':1, 'comments':[
        {'id':'1', 'body':'Restricted discussion', 'author':{'displayName':'Engineer'}}]}}}
    digest = hashlib.sha256(issue_block('https://acme.atlassian.net', issue)['text'].encode()).hexdigest()
    def handler(request):
        if request.url.path.endswith('/myself'):
            return httpx.Response(200, json={'accountId':'reader'})
        assert request.method == 'GET' and 'comment' in request.url.params['fields']
        return httpx.Response(200, json={'issues':[issue], 'isLast':True})
    reader = JiraSource('https://acme.atlassian.net', 'reader@example.com', 'token', httpx.MockTransport(handler))
    assert run(reader.check_issues_access('ENG', ['ENG-1'], {'ENG-1':digest})) == {'checked':1}
    issue['fields']['comment']['comments'] = []
    issue['fields']['comment']['total'] = 0
    with pytest.raises(SourceError) as denied:
        run(reader.check_issues_access('ENG', ['ENG-1'], {'ENG-1':digest}))
    assert denied.value.code == 'stale_source'


@pytest.mark.parametrize('snapshots', [{'OPS-1':'a'*64}, {'ENG-1':'invalid'}, {}])
def test_jira_snapshot_checks_cannot_widen_issue_scope(snapshots):
    reader = JiraSource('https://acme.atlassian.net', 'reader@example.com', 'token',
                        httpx.MockTransport(lambda r: pytest.fail('Invalid scope reached the network')))
    with pytest.raises(SourceError) as denied:
        run(reader.check_issues_access('ENG', ['ENG-1'], snapshots))
    assert denied.value.code == 'scope'


@pytest.mark.parametrize('name,result', [('jira', {'checked':0}), ('jira', {'checked':True}),
    ('jira', None), ('slack', {'channel':'C1','readable':False}),
    ('slack', {'channel':'C2','readable':True}), ('slack', None)])
def test_incomplete_permission_result_blocks_generation_without_purging(state, name, result):
    index, svc, source, _ = state
    import_one(state, name)
    cache(index)
    async def incomplete(*args, **kwargs):
        return result
    setattr(source, 'jira_check_issues_access' if name == 'jira' else 'slack_check_channel_access', incomplete)
    async def forbidden(*args):
        pytest.fail('Unverified content reached the model')
    svc.generator = forbidden
    with pytest.raises(SourceError) as blocked:
        run(svc.ask('How does login work?'))
    assert blocked.value.code == 'access_unverified'
    assert index.source_blocks(index.active_scan()['id'], name+'/') == 1
    assert index.overview(COMMIT)


@pytest.mark.parametrize('name', ['jira', 'slack'])
@pytest.mark.parametrize('code', ['access_denied', 'network'])
def test_remote_access_loss_during_generation_withholds_answer(state, monkeypatch, name, code):
    index, svc, source, _ = state
    import_one(state, name)
    saved = cache(index)
    path = 'jira/ENG-1' if name == 'jira' else 'slack/eng'
    evidence = {'source_id':'S1', 'path':path, 'start':1, 'end':1,
                'text':'Login requires password verification.', 'url':'', 'split':False}
    monkeypatch.setattr(index, 'search', lambda *args, **kwargs: [evidence])
    async def revoke(*args):
        source.denied = SourceError(code, 'Access no longer verified')
        return {'statements':[{'text':'Login requires password verification.', 'source_ids':['S1']}],
                'missing_information':''}
    svc.generator = revoke
    with pytest.raises(SourceError):
        run(svc.ask('How does login work?'))
    with index.db() as db:
        ids = [r[0] for r in db.execute('SELECT id FROM answers')]
    assert ids == ([saved] if code == 'network' else [])
    assert bool(index.source_blocks(index.active_scan()['id'], name+'/')) == (code == 'network')
    assert len(source.checked) == 2


def test_changed_jira_comment_snapshot_clears_derived_caches(state):
    index, svc, source, _ = state
    import_one(state, 'jira')
    cache(index)
    source.denied = SourceError('stale_source', 'A comment is no longer visible')
    with pytest.raises(SourceError) as blocked:
        run(svc.check_external_access(index.active_scan()))
    assert blocked.value.code == 'stale'
    assert not index.source_blocks(index.active_scan()['id'], 'jira/')
    assert not index.overview(COMMIT)
    assert index.code_paths(index.active_scan()['id'])


@pytest.mark.parametrize('denied', [False, True])
def test_access_check_runner_never_changes_the_original_index(state, denied):
    from pka.access_check import check_saved_access
    index, _, source, factory = state
    import_one(state, 'jira')
    import_one(state, 'slack')
    cache(index)
    before = Path(index.path).read_bytes()
    if denied:
        source.denied = SourceError('access_denied', 'secret provider response')
    report = run(check_saved_access(index.path, factory))
    assert report['status'] == ('blocked' if denied else 'passed')
    assert report['saved_sources'] == {'jira_issues':1, 'slack_channels':1}
    assert Path(index.path).read_bytes() == before
    assert index.overview(COMMIT)
    assert 'secret provider response' not in str(report)


def test_access_check_missing_index_does_not_create_one(tmp_path):
    from pka.access_check import check_saved_access
    target = tmp_path/'missing.sqlite3'
    assert run(check_saved_access(target))['status'] == 'blocked'
    assert not target.exists()


@pytest.mark.parametrize('remove_file', [False, True])
def test_removed_file_credential_invalidates_its_saved_source(state, monkeypatch, tmp_path, remove_file):
    index, svc, _, _ = state
    env = tmp_path/'credentials.env'
    monkeypatch.setattr(credentials, 'ENV_PATH', env)
    monkeypatch.setenv('SLACK_USER_TOKEN', 'initial')
    env.write_text('SLACK_USER_TOKEN=file-owned-token\n')
    credentials.refresh()
    import_one(state, 'slack')
    cache(index)
    if remove_file:
        env.unlink()
    else:
        env.write_text('# token removed\n')
    svc.sync_source_credentials()
    assert not index.source_blocks(index.active_scan()['id'], 'slack/')
    assert not index.overview(COMMIT)


def test_refresh_preserves_credentials_supplied_only_by_the_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, 'ENV_PATH', tmp_path/'missing.env')
    monkeypatch.setenv('SLACK_USER_TOKEN', 'inherited-token')
    credentials.refresh()
    import os
    assert os.environ['SLACK_USER_TOKEN'] == 'inherited-token'


@pytest.mark.parametrize('name', ['jira', 'slack'])
def test_remote_revocation_during_overview_does_not_save_generated_content(state, monkeypatch, name):
    from pka import service
    index, svc, source, _ = state
    import_one(state, name)
    monkeypatch.setattr(service, 'topics_for', lambda present: [
        {'key':'purpose', 'title':'Purpose', 'queries':['login'], 'ask':'Explain login'}])
    evidence = {'source_id':'S1', 'path':'jira/ENG-1' if name == 'jira' else 'slack/eng',
                'start':1, 'end':1, 'text':'Login requires password verification.', 'url':'', 'split':False}
    monkeypatch.setattr(index, 'search_many', lambda *args, **kwargs: [evidence])
    async def revoke(*args):
        source.denied = SourceError('access_denied', 'No longer visible')
        return {'statements':[{'text':'Login requires password verification.', 'source_ids':['S1']}],
                'missing_information':''}
    svc.generator = revoke
    with pytest.raises(SourceError):
        run(svc.build_overview())
    assert not index.overview(COMMIT)
