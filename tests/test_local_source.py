"""Local-folder snapshot, permission and integration checks; no user's project is touched."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from auth_helpers import OwnerClient, PASSWORD
from pka.auth_web import cookie_name
from pka.config import LIMITS, source_url
from pka.connectors.base import SourceError
from pka.connectors.local import LocalSource, local_selection
from pka.index import Index
from pka.mcp_client import connect
from pka.service import Service
from pka.web import create_app


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_EMBED_MODEL', '')
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path / 'app-data'))
    monkeypatch.setenv('PKA_LOG_DIR', str(tmp_path / 'app-logs'))
    root = tmp_path / 'project with spaces'
    root.mkdir()
    (root / 'README.md').write_text('# Login project\nLogin verifies a password before creating a session.\nRun python app.py.\n', encoding='utf-8')
    (root / 'app.py').write_text('def login(password):\n    return check_password(password)\n', encoding='utf-8')
    return root


def settings(folder):
    repo, branch = local_selection(str(folder))
    return {'repo':repo, 'branch':branch, 'source_kind':'local', 'local_path':str(folder)}


@asynccontextmanager
async def factory(cfg, demo=False):
    yield LocalSource(cfg['repo'])


def test_folder_path_and_file_link_are_the_same_selection(folder):
    assert local_selection(str(folder)) == local_selection(folder.as_uri())
    assert local_selection('"' + str(folder) + '"') == local_selection(str(folder))


@pytest.mark.parametrize('value', ['', '.', '../project', 'https://github.com/a/b', 'file://remote/share/folder', '\\\\server\\share', 'file:///C:/app?token=x'])
def test_invalid_local_selections(value):
    with pytest.raises(ValueError):
        local_selection(value)


def test_rejects_file_drive_root_and_missing_folder(folder):
    for path in (folder / 'app.py', Path(folder.anchor), folder / 'missing'):
        with pytest.raises(ValueError):
            local_selection(str(path))


def test_snapshot_reads_working_files_but_skips_secrets_dependencies_and_binary(folder):
    (folder / '.env').write_text('TOKEN=never-index-me')
    (folder / 'credentials.json').write_text('{"token":"never-index-me"}')
    (folder / 'node_modules').mkdir()
    (folder / 'node_modules' / 'dependency.js').write_text('ignored dependency')
    (folder / 'new_untracked.py').write_text('def uncommitted(): return 7')
    (folder / 'binary.txt').write_bytes(b'hello\x00world')
    source = LocalSource(settings(folder)['repo'])
    run(source.begin_snapshot())
    entries = {e['path']:e for e in run(source.list_files())['files']}
    assert entries['.env']['skip'] == 'potential_secret_file'
    assert entries['credentials.json']['skip'] == 'potential_secret_file'
    assert 'node_modules/dependency.js' not in entries
    assert 'uncommitted' in run(source.read_file('new_untracked.py'))['text']
    assert run(source.read_file('binary.txt'))['skip'] == 'binary'
    with pytest.raises(SourceError):
        run(source.read_file('.env'))
    for value in ('../outside.py', str(folder / 'app.py'), 'C:\\Windows\\file.py'):
        with pytest.raises(SourceError):
            run(source.read_file(value))


def test_digest_changes_for_edit_add_delete_and_rejects_edit_during_scan(folder):
    source = LocalSource(settings(folder)['repo'])
    original = run(source.begin_snapshot())['commit']
    assert run(source.check_access(original))['head'] == original
    (folder / 'app.py').write_text('def login(password): return False')
    with pytest.raises(SourceError, match='changed'):
        run(source.read_file('app.py'))
    edited = run(source.check_access())['head']
    assert edited != original
    (folder / 'new.py').write_text('x = 1')
    added = run(source.check_access())['head']
    assert added != edited
    (folder / 'new.py').unlink()
    assert run(source.check_access())['head'] == edited


def test_bounded_file_reads_and_coverage(folder, monkeypatch):
    import pka.connectors.local as module
    monkeypatch.setattr(module, 'LIMITS', replace(LIMITS, max_files=1))
    source = LocalSource(settings(folder)['repo'])
    run(source.begin_snapshot())
    assert len(source.allowed) == 1
    assert source.entries[0]['path'] == 'README.md'
    assert any(e['skip'] == 'scan_size_limit' for e in source.entries)
    monkeypatch.setattr(module, 'LIMITS', replace(LIMITS, max_entries=1))
    assert run(source.begin_snapshot())['tree_incomplete']


def test_file_replaced_by_link_is_refused_before_read(folder, monkeypatch):
    import pka.connectors.local as module
    actual = module._linked
    monkeypatch.setattr(module, '_linked', lambda info: actual(info) or info.st_ino == (folder / 'app.py').stat().st_ino)
    source = LocalSource(settings(folder)['repo'])
    with pytest.raises(SourceError, match='Linked folders'):
        run(source.begin_snapshot())


def test_mcp_local_tools_are_fixed_to_the_selected_folder(folder):
    async def scenario():
        async with connect(settings(folder)) as source:
            snapshot = await source.begin_snapshot()
            assert len(snapshot['commit']) == 64
            assert 'login' in (await source.read_file('app.py'))['text']
            with pytest.raises(SourceError):
                await source.read_file('../outside.py')
            with pytest.raises(SourceError):
                await source.call('github_begin_snapshot')
    run(scenario())


def test_scan_answers_overview_and_invalidation_use_local_evidence(folder, tmp_path):
    index = Index(tmp_path / 'index.sqlite3')
    index.configure(settings(folder))
    calls = []
    async def model(question, sources):
        calls.append(sources)
        return {'statements':[{'text':'Login verifies a password before creating a session.', 'source_ids':[sources[0]['source_id']]}], 'missing_information':''}
    service = Service(index, connector_factory=factory, generator=model)
    run(service.scan())
    scan = index.active_scan()
    assert scan and scan['read'] == 2
    answer = run(service.ask('How does login check the password?'))
    assert answer['sources'] and calls
    assert all(s['url'].startswith('/source?snapshot=') for s in answer['sources'])
    run(service.build_overview())
    assert index.overview(scan['commit'])['complete']
    (folder / 'app.py').write_text('def changed(): return True')
    with pytest.raises(SourceError, match='changed'):
        run(service.ask('How does login work?'))
    assert index.active_scan() is None
    assert index.overview(scan['commit']) is None


def test_changes_during_answer_generation_withhold_result(folder, tmp_path):
    index = Index(tmp_path / 'index.sqlite3')
    index.configure(settings(folder))
    async def model(question, sources):
        (folder / 'app.py').write_text('def changed(): return True')
        return {'statements':[{'text':'Login verifies passwords.', 'source_ids':[sources[0]['source_id']]}], 'missing_information':''}
    service = Service(index, connector_factory=factory, generator=model)
    run(service.scan())
    with pytest.raises(SourceError, match='changed'):
        run(service.ask('How does login work?'))
    with index.db() as db:
        assert not db.execute('SELECT count(*) FROM answers').fetchone()[0]


def test_owner_config_source_view_and_member_boundary(folder, tmp_path):
    app = create_app(db_path=tmp_path / 'index.sqlite3', connector_factory=factory)
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as owner:
        result = owner.post('/api/config', json={'source_kind':'local', 'local_path':folder.as_uri()})
        assert result.status_code == 200
        service = app.state.service
        run(service.scan())
        scan = service.index.active_scan()
        response = owner.get('/api/local-source', params={'path':'app.py', 'snapshot':scan['commit']})
        assert response.status_code == 200 and response.json()['lines'][0]['number'] == 1
        assert owner.get('/api/local-source', params={'path':'../outside.py', 'snapshot':scan['commit']}).status_code == 404
        assert owner.get('/api/local-source', params={'path':'app.py', 'snapshot':'old'}).status_code == 409
        assert owner.get('/api/local-source', params={'path':'app.py', 'snapshot':scan['commit']}, headers={'x-pka-request':''}).status_code == 403
        assert 'local' in owner.get('/api/import-coverage').json()['sources']
        app.state.auth.create_member('member', PASSWORD)
        token = app.state.auth.login('member', PASSWORD, 'http://localhost:8000')
        with TestClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'},
                        cookies={cookie_name(app.state.auth):token}) as member:
            assert member.post('/api/config', json={'source_kind':'local', 'local_path':str(folder)}).status_code == 403
            assert member.get('/api/local-source', params={'path':'app.py', 'snapshot':scan['commit']}).status_code == 403
            assert 'app.py' not in member.get('/api/status').text
        (folder / 'app.py').unlink()
        assert owner.get('/api/local-source', params={'path':'app.py', 'snapshot':scan['commit']}).status_code == 409


def test_local_citation_encodes_file_and_snapshot(folder):
    url = source_url(settings(folder)['repo'], 'abc123', 'a folder/read me.md', 12)
    assert url == '/source?snapshot=abc123&path=a%20folder%2Fread%20me.md#L12'


def test_reselecting_changed_folder_requests_a_new_scan(folder, tmp_path):
    app = create_app(db_path=tmp_path / 'index.sqlite3', connector_factory=factory)
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as owner:
        choice = {'source_kind':'local', 'local_path':str(folder)}
        assert owner.post('/api/config', json=choice).status_code == 200
        run(app.state.service.scan())
        assert owner.post('/api/config', json=choice).json()['reconnected']
        (folder / 'app.py').write_text('def changed(): return True')
        assert owner.post('/api/config', json=choice).json()['reconnected'] is False
        assert app.state.service.index.active_scan() is None


def test_local_code_can_be_retrieved_together_with_jira_and_slack(folder, tmp_path):
    from pka.connectors.jira import issue_block
    class Combined(LocalSource):
        async def jira_begin_read(self):
            return {'project':'ENG', 'issues':1, 'blocks':1}
        async def jira_issues(self, cursor=0):
            return {'blocks':[issue_block('https://acme.atlassian.net', {'key':'ENG-1', 'fields':{
                'summary':'Login requires password verification', 'description':'Login verifies passwords before creating a session.'}})], 'next_cursor':None}
        async def jira_check_issues_access(self, issue_keys, snapshots=None):
            return {'checked':len(issue_keys)}
        async def slack_messages(self, channel_id):
            return [{'ts':'1700000000.0', 'user':'U1', 'text':'Login password verification was agreed before creating a session.'}]
        async def slack_check_channel_access(self, channel_id, snapshot_digest=''):
            return {'channel':channel_id, 'readable':True, 'snapshot':snapshot_digest}
    @asynccontextmanager
    async def combined(cfg, demo=False):
        yield Combined(cfg['repo'])
    index = Index(tmp_path / 'combined.sqlite3')
    index.configure(settings(folder))
    async def model(question, sources):
        return {'statements':[{'text':'Login verifies passwords before creating a session.',
            'source_ids':[s['source_id'] for s in sources]}], 'missing_information':''}
    service = Service(index, connector_factory=combined, generator=model)
    run(service.scan())
    index.configure_source('jira', {'project':'ENG'})
    index.configure_slack({'workspace':'acme', 'channels':[{'id':'C1', 'name':'engineering'}]})
    run(service.read_jira('ENG'))
    run(service.read_slack('acme', index.settings()['slack']['channels']))
    answer = run(service.ask('How does login verify passwords before creating a session?'))
    paths = [s['path'] for s in answer['sources']]
    assert any(p.startswith('jira/') for p in paths)
    assert any(p.startswith('slack/') for p in paths)
    assert any(not p.startswith(('jira/', 'slack/')) for p in paths)


def test_additional_folder_preserves_github_jira_slack_and_pins_citations(folder, tmp_path):
    from pka.connectors.fixture import FixtureSource
    from pka.connectors.jira import issue_block
    class FourSources(FixtureSource):
        async def jira_begin_read(self):
            return {'project':'SHOP', 'issues':1, 'blocks':1}
        async def jira_issues(self, cursor=0):
            return {'blocks':[issue_block('https://acme.atlassian.net', {'key':'SHOP-1', 'fields':{
                'summary':'Login password verification', 'description':'Login checks passwords before creating a session.'}})], 'next_cursor':None}
        async def jira_check_issues_access(self, issue_keys, snapshots=None):
            return {'checked':len(issue_keys)}
        async def slack_messages(self, channel_id):
            return [{'ts':'1700000000.0', 'user':'U1', 'text':'Login password verification was agreed before creating a session.'}]
        async def slack_check_channel_access(self, channel_id, snapshot_digest=''):
            return {'channel':channel_id, 'readable':True, 'snapshot':snapshot_digest}
    @asynccontextmanager
    async def mixed(cfg, demo=False):
        yield LocalSource(cfg['repo']) if cfg['repo'].startswith('local:') else FourSources()
    app = create_app(db_path=tmp_path / 'mixed.sqlite3', connector_factory=mixed)
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as owner:
        assert owner.post('/api/config', json={'repo':'acme/shop', 'branch':'main'}).status_code == 200
        service, index = app.state.service, app.state.service.index
        run(service.scan())
        scan = index.active_scan()
        index.configure_source('jira', {'project':'SHOP'})
        index.configure_slack({'workspace':'acme', 'channels':[{'id':'C1', 'name':'engineering'}]})
        run(service.read_jira('SHOP'))
        run(service.read_slack('acme', index.settings()['slack']['channels']))
        before = {p for p in index.indexed_paths(scan['id'])}
        assert any(p.startswith('jira/') for p in before) and any(p.startswith('slack/') for p in before)
        choice = {'source_kind':'local', 'local_path':str(folder), 'add_to_project':True}
        response = owner.post('/api/config', json=choice)
        assert response.status_code == 200 and response.json()['additional_local']
        assert index.settings()['repo'] == 'acme/shop'
        assert index.settings()['project_name'] == 'shop'
        assert index.active_scan()['id'] == scan['id']
        run(service.read_local())
        assert before <= set(index.indexed_paths(scan['id']))
        saved = index.source_import('local')
        path = 'local://' + saved['snapshot'] + '/app.py'
        assert path in index.code_paths(scan['id'])
        url = source_url(scan['repo'], scan['commit'], path, 1)
        assert url.startswith('/source?') and saved['snapshot'] in url
        viewed = owner.get('/api/local-source', params={'path':path, 'snapshot':saved['snapshot']})
        assert viewed.status_code == 200 and viewed.json()['path'] == 'app.py'
        async def model(question, sources):
            return {'statements':[], 'missing_information':'Inspect the sources.'}
        service.generator = model
        answer = run(service.ask('How does login check passwords and create sessions?'))
        assert any(s['path'].startswith('local://') for s in answer['sources'])
        assert any(s['url'] and s['url'].startswith('https://github.com/') for s in answer['sources'])
        run(service.build_overview())
        overview = index.overview(scan['commit'])
        assert overview and overview['complete']
        assert 'local://' in str(overview) and '/source?snapshot=' in str(overview)
        (folder / 'app.py').write_text('def login(password): return False')
        assert owner.get('/api/local-source', params={'path':path, 'snapshot':saved['snapshot']}).status_code == 409
        assert index.active_scan()['id'] == scan['id']
        assert before <= set(index.indexed_paths(scan['id']))
        assert not index.source_import('local')
        assert not index.overview(scan['commit'])
        run(service.read_local())
        assert index.source_import('local')['snapshot'] != saved['snapshot']
        assert owner.get('/api/local-source', params={'path':path, 'snapshot':saved['snapshot']}).status_code == 409
        assert before <= set(index.indexed_paths(scan['id']))


def test_import_diagrams_keep_github_and_local_modules_separate():
    from pka.diagram import _lookup, imports_in
    prefix = 'local://' + 'a' * 64 + '/'
    paths = ['app.py', 'helper.py', prefix+'app.py', prefix+'helper.py', prefix+'local_only.py']
    table = _lookup(paths)
    assert imports_in(prefix+'app.py', [(1, 'import helper')], table) == [(prefix+'helper.py', 1)]
    assert imports_in('app.py', [(1, 'import helper')], table) == [('helper.py', 1)]
    assert imports_in('app.py', [(1, 'import local_only')], table) == []


def test_project_name_follows_new_selections_and_survives_reconnect(folder, tmp_path):
    db_path = tmp_path / 'project-names.sqlite3'
    app = create_app(db_path=db_path, connector_factory=factory)
    headers = {'x-pka-request':'1'}
    with OwnerClient(app, base_url='http://localhost:8000', headers=headers) as owner:
        github = {'repo':'acme/shop', 'branch':'main'}
        assert owner.post('/api/config', json=github).status_code == 200
        assert owner.get('/api/status').json()['settings']['project_name'] == 'shop'
        assert owner.post('/api/config', json={'source_kind':'local', 'local_path':str(folder)}).status_code == 200
        current = owner.get('/api/status').json()['settings']
        assert current['project_name'] == folder.name and current['repo'] == settings(folder)['repo']
        added = tmp_path / 'new-local-project'
        added.mkdir()
        assert owner.post('/api/config', json={'source_kind':'local', 'local_path':str(added)}).status_code == 200
        assert owner.get('/api/status').json()['settings']['project_name'] == added.name
        assert owner.post('/api/config', json={'source_kind':'local', 'local_path':str(added / 'missing')}).status_code == 422
        assert owner.get('/api/status').json()['settings']['project_name'] == added.name

    restarted = create_app(db_path=db_path, connector_factory=factory)
    with OwnerClient(restarted, base_url='http://localhost:8000', headers=headers) as owner:
        assert owner.get('/api/status').json()['stored_project']['project_name'] == added.name
        assert owner.post('/api/config', json=github).status_code == 200
        assert owner.get('/api/status').json()['settings']['project_name'] == 'shop'
        assert owner.post('/api/config', json={'repo':'acme/new-repository', 'branch':'main'}).status_code == 200
        current = owner.get('/api/status').json()['settings']
        assert current['project_name'] == 'new-repository'
        assert not current.get('local') and not current.get('local_path')


def test_older_mixed_source_workspace_gets_local_project_name(folder, tmp_path):
    app = create_app(db_path=tmp_path / 'legacy-name.sqlite3', connector_factory=factory)
    index = app.state.service.index
    index.configure({'repo':'acme/shop', 'branch':'main', 'local':{'path':str(folder)}})
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as owner:
        stored = owner.get('/api/status').json()['stored_project']
        assert stored['project_name'] == folder.name
        assert stored['source_kind'] == 'local'
        assert Path(stored['local_path']) == folder
        assert owner.post('/api/config', json={'repo':'acme/shop', 'branch':'main'}).status_code == 200
        assert owner.get('/api/status').json()['settings']['project_name'] == 'shop'


def test_new_local_project_survives_restart_without_the_previous_github_repository(folder, tmp_path):
    db_path = tmp_path / 'saved-connection.sqlite3'
    headers = {'x-pka-request':'1'}
    github = {'repo':'acme/shop', 'branch':'main'}
    local = {'source_kind':'local', 'local_path':folder.as_uri()}
    app = create_app(db_path=db_path, connector_factory=factory)
    with OwnerClient(app, base_url='http://localhost:8000', headers=headers) as owner:
        assert owner.post('/api/config', json=github).status_code == 200
        assert owner.post('/api/config', json=local).status_code == 200
        current = owner.get('/api/status').json()['settings']
        assert current['selected_source'] == 'local'
        assert current['repo'] == settings(folder)['repo']

    restarted = create_app(db_path=db_path, connector_factory=factory)
    with OwnerClient(restarted, base_url='http://localhost:8000', headers=headers) as owner:
        stored = owner.get('/api/status').json()['stored_project']
        assert stored['source_kind'] == 'local'
        assert Path(stored['local_path']) == folder
        # Reconnect with the form fields; project_name is read-only display metadata.
        reconnect = {'source_kind':stored['source_kind'], 'local_path':stored['local_path'],
                     'repo':'', 'branch':'working-tree'}
        assert owner.post('/api/config', json=reconnect).status_code == 200
        assert owner.get('/api/status').json()['settings']['selected_source'] == 'local'
        # Choosing GitHub starts its own project and survives navigation/restart.
        assert owner.post('/api/config', json=github).status_code == 200
        assert owner.get('/api/status').json()['settings']['selected_source'] == 'github'
        assert not owner.get('/api/status').json()['settings'].get('local')

    restarted = create_app(db_path=db_path, connector_factory=factory)
    with OwnerClient(restarted, base_url='http://localhost:8000', headers=headers) as owner:
        stored = owner.get('/api/status').json()['stored_project']
        assert stored['source_kind'] == 'github'
        assert stored['repo'] == 'acme/shop'
