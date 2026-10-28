import asyncio
import json
from contextlib import asynccontextmanager

from auth_helpers import OwnerClient
from pka.connectors.fixture import FixtureSource
from pka.index import chunk_file
from pka.web import create_app


def test_legacy_local_selection_hides_old_repository_cards_and_generates_only_local_files(tmp_path, monkeypatch):
    from pka import service as module
    checks, generated = [], []
    @asynccontextmanager
    async def factory(settings, demo=False):
        source = FixtureSource()
        original = source.check_access
        async def check(snapshot):
            checks.append(settings['repo'])
            return {'head':snapshot} if settings['repo'].startswith('local:') else await original(snapshot)
        source.check_access = check
        yield source
    app = create_app(False, tmp_path/'index.sqlite3', connector_factory=factory)
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as client:
        assert client.post('/api/config', json={'repo':'acme/old-chatbot','branch':'main'}).status_code == 200
        svc = app.state.service
        asyncio.run(svc.scan())
        index, scan = svc.index, svc.index.active_scan()
        local = {'repo':'local:D:/famas_matching_square','path':'D:/famas_matching_square'}
        index.configure_source('local', local)
        index.configure({'selected_source':'local','project_name':'famas_matching_square'})
        snapshot = 'c' * 64
        prefix = 'local://' + snapshot + '/'
        files = {'README.md':'# Famas matching\nFind matching investors from an industry query.\n',
                 'app.py':'from matching import find\n@app.post("/match")\ndef match(industry):\n    return find(industry)\n',
                 'matching.py':'def find(industry):\n    return {"industry":industry}\n'}
        blocks = [chunk for path,text in files.items() for chunk in chunk_file(prefix+path,text)]
        index.replace_source(scan['id'], 'local://', blocks, {'snapshot':snapshot,
            'scope':index.source_scope('local',local), 'report':{'skipped':2,'read_at':'2026-10-28T10:00:00Z'}})
        index.save_overview(scan['id'], scan['commit'], {'repo':scan['repo'],'branch':'main','commit':scan['commit'],
            'files_indexed':57, 'sections':[{'text':'OLD CHATBOT CONTENT'}]})
        checks.clear()
        response = client.get('/api/overview')
        assert response.status_code == 200
        body = response.json()['overview']
        assert body['repo'] == local['repo'] and body['project_name'] == 'famas_matching_square'
        assert body['branch'] == '' and body['commit'] == snapshot
        assert body['files_indexed'] == 3 and body['files_skipped'] == 2
        assert body['topics_done'] == 0 and body['scope_update_available']
        assert 'old-chatbot' not in json.dumps(body) and 'OLD CHATBOT' not in json.dumps(body)
        assert all(repo == local['repo'] for repo in checks)
        assert body['overview_features']['repo'] == local['repo']
        assert [f['name'] for f in body['overview_features']['features']] == ['Match']
        async def generator(question, sources):
            generated.extend(sources)
            return {'statements':[{'text':'The matching app receives an industry query.', 'source_ids':[sources[0]['source_id']]}], 'missing_information':''}
        svc.generator = generator
        monkeypatch.setattr(module, 'topics_for', lambda present: [next(t for t in module.TOPICS if t['key']=='flows')])
        built = asyncio.run(svc.build_overview())
        assert built['repo'] == local['repo'] and built['files_indexed'] == 3 and built['branch'] == ''
        assert generated and all(s['path'].startswith(prefix) for s in generated)
        loaded = client.get('/api/overview').json()['overview']
        assert not loaded.get('scope_update_available') and loaded['topics_done'] == 1
        assert 'old-chatbot' not in json.dumps(loaded)
