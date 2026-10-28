import asyncio
from contextlib import asynccontextmanager

import pytest
from auth_helpers import OwnerClient
from pka import architecture
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource, COMMIT
from pka.index import chunk_file
from pka.web import create_app


@pytest.fixture
def client_state(tmp_path):
    @asynccontextmanager
    async def factory(settings, demo=False):
        yield FixtureSource()
    app = create_app(False, tmp_path/'index.sqlite3', connector_factory=factory)
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as client:
        assert client.post('/api/config', json={'repo':'acme/shop','branch':'main'}).status_code == 200
        service = app.state.service
        asyncio.run(service.scan())
        yield client, service


def test_refresh_derives_current_files_without_reading_or_replacing_saved_overview(client_state, monkeypatch):
    client, service = client_state
    scan = service.index.active_scan()
    old = {'diagrams':[{'title':'OLD SAVED OVERVIEW'}]}
    service.index.save_overview(scan['id'], scan['commit'], old)
    old = service.index.overview(scan['commit'])
    first = client.get('/api/architecture').json()
    assert first['available'] and first['architecture']['systems']
    assert 'OLD SAVED OVERVIEW' not in str(first)
    assert service.index.overview(scan['commit']) == old
    original = architecture.derive
    def changed(index, scan):
        result = original(index, scan)
        result['systems'][0]['name'] = 'Freshly recalculated'
        return result
    monkeypatch.setattr(architecture, 'derive', changed)
    second = client.get('/api/architecture').json()
    assert second['architecture']['systems'][0]['name'] == 'Freshly recalculated'
    assert service.index.overview(scan['commit']) == old


def test_diagrams_and_facts_keep_repository_and_local_systems_separate(client_state):
    client, service = client_state
    index, scan = service.index, service.index.active_scan()
    prefix = 'local://' + 'c' * 64 + '/'
    index.configure_source('local', {'repo':'local:D:/Projects/matching'})
    files = {'app.py':'from orders import place\n@app.post("/orders")\ndef create():\n    return place()\n',
             'orders.py':'def place():\n    return True\n',
             prefix+'app.py':'from investors import match\n@app.post("/investors")\ndef create():\n    return match()\n',
             prefix+'investors.py':'def match():\n    return True\n'}
    index.activate(scan['id'], [c for path,text in files.items() for c in chunk_file(path,text)], scan)
    response = client.get('/api/architecture')
    assert response.status_code == 200
    body = response.json()['architecture']
    assert body['knowledge_revision'] == index.revision
    systems = body['systems']
    assert [s['name'] for s in systems] == ['shop','matching']
    assert '/investors' not in str(systems[0]) and '/orders' not in str(systems[1])
    for position, system in enumerate(systems):
        paths = [node['path'] for d in system['diagrams'] for node in d['nodes'] if node.get('path')]
        assert paths and all(p.startswith(prefix) == bool(position) for p in paths)


@pytest.mark.parametrize('change', ['revision', 'read'])
def test_architecture_withholds_results_when_sources_change_during_derivation(client_state, monkeypatch, change):
    client, service = client_state
    original = architecture.derive
    def racing(index, scan):
        result = original(index, scan)
        if change == 'revision':
            index.invalidate()
        else:
            service.local_progress = {'phase':'Reading changed files'}
        return result
    monkeypatch.setattr(architecture, 'derive', racing)
    response = client.get('/api/architecture')
    assert response.status_code == 409 and 'systems' not in response.json()


def test_architecture_checks_access_and_hides_old_data_while_importing(client_state, monkeypatch):
    client, service = client_state
    async def denied(scan):
        raise SourceError('access_denied', 'Read access revoked')
    monkeypatch.setattr(service, 'check_external_access', denied)
    denied_reply = client.get('/api/architecture')
    assert denied_reply.status_code == 409 and 'Read access revoked' in denied_reply.text
    assert 'systems' not in denied_reply.json()
    service.local_progress = {'phase':'Reading files'}
    pending = client.get('/api/architecture').json()
    assert not pending['available'] and pending['architecture'] is None
