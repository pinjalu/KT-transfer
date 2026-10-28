"""New project selections must never retain another project's sources or derived content."""
from contextlib import asynccontextmanager

import pytest

from auth_helpers import OwnerClient
from pka.connectors.fixture import FixtureSource
from pka.connectors.local import LocalSource, is_local
from pka.index import chunk_file
from pka.web import create_app
from test_zip_projects import archive, upload, wait_scan


@asynccontextmanager
async def factory(cfg, demo=False):
    yield LocalSource(cfg['repo']) if is_local(cfg['repo']) else FixtureSource()


@pytest.mark.parametrize('before_kind', ['github', 'local', 'zip'])
@pytest.mark.parametrize('after_kind', ['github', 'local', 'zip'])
def test_switching_projects_clears_previous_sources_and_saved_content(tmp_path, monkeypatch, before_kind, after_kind):
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('PKA_LOG_DIR', str(tmp_path / 'logs'))
    app = create_app(db_path=tmp_path / 'index.sqlite3', connector_factory=factory)
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as client:
        def select(kind, name):
            if kind == 'zip':
                reply = upload(client, archive({f'{name}.py':f'{name.upper()} = True\n'}), name=f'{name}.zip')
            else:
                if kind == 'local':
                    folder = tmp_path / name
                    folder.mkdir()
                    (folder / f'{name}.py').write_text(f'{name.upper()} = True\n')
                    choice = {'source_kind':'local', 'local_path':str(folder)}
                else:
                    choice = {'repo':f'acme/{name}', 'branch':'main'}
                reply = client.post('/api/config', json=choice)
                assert reply.status_code == 200, reply.text
                assert not reply.json()['reconnected']
                status = client.get('/api/status').json()
                assert not status['ready'] and status['scan'] is None and status['job'] is None
                assert not client.get('/api/overview').json()['available']
                assert not client.get('/api/features').json()['features']
                reply = client.post('/api/scan')
            assert reply.status_code == 200, reply.text
            return wait_scan(client)

        before = select(before_kind, 'old_project')
        index = app.state.service.index
        assert client.post('/api/search-mode', json={'mode':'basic'}).status_code == 200
        index.configure_source('jira', {'project':'OLD'})
        index.configure_slack({'workspace':'old', 'channels':[{'id':'COLD', 'name':'old'}]})
        index.configure_source('local', {'repo':'local:old-extra', 'path':'old-extra'})
        scan = index.active_scan()
        for prefix in ('jira/', 'slack/', 'local://'):
            index.replace_source(scan['id'], prefix, chunk_file(prefix + 'old-only.md', 'OLD_PROJECT_ONLY'))
        index.save_overview(scan['id'], scan['commit'], {'repo':scan['repo'], 'marker':'OLD_PROJECT_ONLY'})
        index.record_answer(scan['id'], 'Old project question', {'marker':'OLD_PROJECT_ONLY'}, 0)
        app.state.service.job_error = 'Old project failure'

        after = select(after_kind, 'new_project')
        current = after['settings']
        assert current['repo'] != before['settings']['repo']
        assert current['project_name'] == 'new_project'
        assert not any(current.get(key) for key in ('jira', 'slack', 'local'))
        assert current['search_mode'] == 'basic'
        assert after['job_error'] == ''
        if after_kind == 'github':
            assert not current.get('archive') and not current.get('local_path')
        assert not index.overview(after['scan']['commit'])
        assert not any('old-only' in path for path in index.indexed_paths(after['scan']['id']))
        with index.db() as db:
            for table in ('answers', 'overviews', 'ai_topic_cache', 'source_imports',
                          'jira_explanations', 'decision_summaries', 'evaluation_runs'):
                assert db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
        coverage = client.get('/api/import-coverage').json()['sources']
        assert not any(coverage.get(key, {}).get('available') for key in ('jira', 'slack'))


def test_adding_a_folder_requires_an_active_github_project(tmp_path):
    folder = tmp_path / 'project'
    folder.mkdir()
    (folder / 'app.py').write_text('NEW = True\n')
    app = create_app(db_path=tmp_path / 'index.sqlite3', connector_factory=factory)
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as client:
        choice = {'source_kind':'local', 'local_path':str(folder), 'add_to_project':True}
        assert client.post('/api/config', json=choice).status_code == 409
        assert client.post('/api/config', json={'repo':'acme/shop'}).status_code == 200
        assert client.post('/api/config', json=choice).status_code == 409
        assert client.get('/api/status').json()['settings']['repo'] == 'acme/shop'
