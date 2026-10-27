import asyncio
from contextlib import asynccontextmanager

import pytest
from auth_helpers import OwnerClient

from pka import feature_kt
from pka.config import now
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource, COMMIT
from pka.index import Index, chunk_file
from pka.service import Service
from pka.web import create_app


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_EMBED_MODEL', '')
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    state = {'denied':False, 'calls':0}
    class Source(FixtureSource):
        async def check_access(self, commit=''):
            state['calls'] += 1
            if state['denied']: raise SourceError('access_denied', 'Permission revoked.')
            return await super().check_access(commit)
    @asynccontextmanager
    async def factory(settings, demo=False): yield Source()
    index = Index(tmp_path / 'index.sqlite3')
    index.configure({'repo':'acme/shop', 'branch':'main'})
    scan = {'repo':'acme/shop', 'branch':'main', 'commit':COMMIT, 'status':'complete', 'finished':now()}
    scan['id'] = index.new_scan(scan)
    files = {
        'app.py':'from orders import create\n@app.post("/orders")\ndef new_order():\n    return create()\n',
        'orders.py':'def create():\n    """Create an order for a customer."""\n    return {"order": "pending"}\n',
        'README.md':'# Orders\nCustomers use orders to request products from the shop.\n',
        'tests/test_orders.py':'from orders import create\ndef test_orders():\n    assert create()["order"] == "pending"\n',
        'unrelated.py':'# orders customers purpose\nPRIVATE_UNRELATED = "must not be retrieved"\n',
    }
    index.activate(scan['id'], [c for path, text in files.items() for c in chunk_file(path, text)], scan)
    service = Service(index, connector_factory=factory)
    async def generate(question, sources):
        state['prompt'] = question
        state['sources'] = sources
        return {'statements':[{'text':'Customers use orders to request products from the shop.',
            'source_ids':[s['source_id'] for s in sources if s['path'] == 'README.md'] or [sources[0]['source_id']]}],
            'missing_information':'The deployed runtime has not been observed.'}
    service.generator = generate
    return service, state, factory


@pytest.mark.parametrize('section', [item['key'] for item in feature_kt.SECTIONS])
def test_sections_are_scoped_cited_and_not_runtime_verified(context, section):
    service, state, _ = context
    reply = asyncio.run(feature_kt.build(service, 'orders', section))
    assert reply['key'] == section and reply['feature_id'] == 'orders'
    assert reply['knowledge_revision'] == service.index.revision
    assert reply['sources'] and reply['generated_at']
    assert all(s['path'] != 'unrelated.py' for s in reply['sources'])
    assert all(s['source_id'].startswith('kt-'+section+'-') for s in reply['sources'])
    assert {sid for s in reply['statements'] for sid in s['source_ids']} <= {s['source_id'] for s in reply['sources']}
    assert all(s['evidence']['kind'] != 'verified_code' for s in reply['statements'])
    assert 'declared entry routes' in state['prompt']
    assert state['calls'] == 2


@pytest.mark.parametrize('change', ['revision', 'revoked'])
def test_changes_during_generation_discard_the_result(context, change):
    service, state, _ = context
    async def generate(question, sources):
        if change == 'revision': service.index.invalidate()
        else: state['denied'] = True
        return {'statements':[], 'missing_information':'Old result'}
    service.generator = generate
    with pytest.raises(SourceError): asyncio.run(feature_kt.build(service, 'orders', 'purpose'))


def test_missing_section_feature_and_evidence_are_explicit(context, monkeypatch):
    service, _, _ = context
    with pytest.raises(SourceError): asyncio.run(feature_kt.build(service, 'orders', 'unknown'))
    with pytest.raises(SourceError): asyncio.run(feature_kt.build(service, 'missing', 'purpose'))
    monkeypatch.setattr(service.index, 'search_many', lambda *a, **kw: [])
    reply = asyncio.run(feature_kt.build(service, 'orders', 'purpose'))
    assert reply['statements'] == [] and 'No matching excerpts' in reply['missing_information']


def test_web_requires_selection_and_refuses_concurrent_work(context):
    service, _, factory = context
    app = create_app(False, service.index.path, connector_factory=factory)
    app.state.service.generator = service.generator
    with OwnerClient(app, base_url='http://localhost:8000', headers={'X-PKA-Request':'1'}) as client:
        endpoint = '/api/features/orders/walkthrough/purpose'
        assert client.post(endpoint).status_code == 409
        assert client.post('/api/config', json={'repo':'acme/shop', 'branch':'main'}).status_code == 200
        assert len(client.get('/api/features/orders').json()['walkthrough_sections']) == 6
        response = client.post(endpoint)
        assert response.status_code == 200, response.text
        assert response.json()['sources']
        app.state.service.lock = asyncio.Lock()
        asyncio.run(app.state.service.lock.acquire())
        try: assert client.post(endpoint).status_code == 409
        finally: app.state.service.lock.release()


def test_live_story_regression_withholds_unrelated_route_and_invented_result(context, monkeypatch):
    service, state, _ = context
    monkeypatch.setattr(service.index, 'search_many', lambda *args, **kwargs: [{
        'source_id':'S1', 'path':'app.py', 'start':1, 'end':4,
        'text':'from orders import create\n@app.post("/orders")\ndef new_order():\n    return create()\n'}])
    async def generate(question, sources):
        assert 'Choose ONE route' in question and 'preserving its validation' in question
        return {'statements':[
            {'text':'POST /orders calls create in app.py.', 'source_ids':[sources[0]['source_id']]},
            {'text':'GET /admin calls create in app.py.', 'source_ids':[sources[0]['source_id']]},
            {'text':'Result: returns a 200 OK response with a JSON object containing the analytics data.',
             'source_ids':[sources[0]['source_id']]}], 'missing_information':''}
    service.generator = generate
    reply = asyncio.run(feature_kt.build(service, 'orders', 'story'))
    assert [statement['text'] for statement in reply['statements']] == ['POST /orders calls create in app.py.']
    assert reply['checks']['withheld_statements'] == 2
    assert '2 generated statement(s) were withheld' in reply['missing_information']
    assert reply['sources'] and reply['statements'][0]['evidence']['kind'] == 'code'


@pytest.mark.parametrize('claim,citation,keep', [
    ('GET /orders', '@app.post("/orders")', False),
    ('GET /orders', '@app.get("/orders/{id}")', False),
    ('GET /orders', '@app.get("/Orders")', False),
    ('GET /orders', 'router.get("/orders", listOrders)', True),
    ('POST `/orders`', 'POST /orders creates an order.', True),
])
def test_routes_require_exact_method_and_path_in_the_cited_excerpt(claim, citation, keep):
    section = {'statements':[{'text':claim, 'source_ids':['S1'], 'support':'supported'}],
               'sources':[{'source_id':'S1', 'text':citation}], 'checks':{}, 'missing_information':''}
    result = feature_kt.restrict_claims(section)
    assert bool(result['statements']) == keep
    assert result['checks']['withheld_statements'] == (0 if keep else 1)
