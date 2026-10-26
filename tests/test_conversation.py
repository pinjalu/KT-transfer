import asyncio
from contextlib import asynccontextmanager
import json

import httpx
import pytest
from pydantic import ValidationError

from pka import embed, service
from pka.config import now
from pka.connectors.fixture import FixtureSource, COMMIT
from pka.conversation import Conversation, followup_query
from pka.index import Index, chunk_file
from pka.service import Service, ollama_answer, answer_schema, focused_question
from pka.web import Question


@asynccontextmanager
async def connector(settings, demo=False):
    yield FixtureSource()


@pytest.fixture
def workspace(tmp_path):
    index = Index(tmp_path / 'conversation.sqlite3')
    index.configure({'repo': 'acme/shop', 'branch': 'main'})
    scan = {'id': 1, 'repo': 'acme/shop', 'commit': COMMIT, 'status': 'complete', 'finished': now()}
    chunks = chunk_file('uploads.py', "IMAGE_FORMATS = {'.png', '.jpg'}\ndef upload_image(file):\n    if file.suffix not in IMAGE_FORMATS:\n        raise HTTPException(415, 'Unsupported image format')\n")
    chunks += chunk_file('db.py', "DATABASE = 'PostgreSQL'\nDRIVER = 'asyncpg'\n")
    index.new_scan(scan)
    index.activate(1, chunks, scan)
    return index, scan


def context(index, scan, **changes):
    return Conversation(**{'repo': scan['repo'], 'commit': scan['commit'],
        'knowledge_revision': index.revision, 'turns': [{
            'question': 'What happens when I upload a PDF to the image endpoint?',
            'answer': 'The image endpoint rejects a PDF with HTTP 415.'}], **changes})


def test_followup_retrieves_current_evidence_and_receives_history(workspace):
    index, scan = workspace
    seen = {}
    async def generate(question, sources, history=()):
        seen.update(question=question, sources=sources, history=history)
        return {'statements': [{'text': 'Only png and jpg images are accepted.',
                               'source_ids': [sources[0]['source_id']]}], 'missing_information': ''}
    result = asyncio.run(Service(index, connector_factory=connector, generator=generate).ask(
        'Why does it reject that?', context(index, scan)))
    assert any(s['path'] == 'uploads.py' for s in seen['sources'])
    assert seen['question'] == 'Why does it reject that?'
    assert seen['history'][0]['answer'].endswith('415.')
    assert result['knowledge_revision'] == index.revision
    assert result['search']['conversation_turns'] == 1


@pytest.mark.parametrize('change', [
    {'repo': 'acme/other'}, {'commit': 'b' * 40}, {'knowledge_revision': 0},
])
def test_other_project_snapshot_or_revision_cannot_seed_context(workspace, change):
    index, scan = workspace
    seen = {}
    async def generate(question, sources, history=()):
        seen['history'] = history
        return {'statements': [], 'missing_information': 'Missing.'}
    result = asyncio.run(Service(index, connector_factory=connector, generator=generate).ask(
        'Which database is configured?', context(index, scan, **change)))
    assert not seen['history']
    assert result['search']['conversation_turns'] == 0


def test_standalone_new_topic_does_not_expand_with_old_answer(workspace):
    index, scan = workspace
    turns = context(index, scan).current_turns(scan, index.revision)
    assert followup_query('Which database is configured?', turns) is None
    found = index.search('Which database is configured?', scan)
    assert found[0]['path'] == 'db.py'


def test_followup_respects_explicit_file_scope(workspace):
    index, scan = workspace
    turns = context(index, scan).current_turns(scan, index.revision)
    question = 'Which database does db.py use for that?'
    found = index.search(question, scan, context_question=followup_query(question, turns))
    assert found and all(s['path'] == 'db.py' for s in found)


@pytest.mark.parametrize('turns', [
    [{'question': 'x', 'answer': ''}] * 5,
    [{'question': 'x', 'answer': 'x' * 1801}],
    [{'question': 'x' * 601, 'answer': ''}],
])
def test_unbounded_browser_history_is_rejected(turns):
    with pytest.raises(ValidationError):
        Question(question='Why?', conversation={'repo': 'a/b', 'commit': 'a',
                 'knowledge_revision': 1, 'turns': turns})


def test_generation_marks_old_replies_untrusted_and_cites_only_current_sources(monkeypatch):
    real_client = httpx.AsyncClient
    history = [{'question': 'Explain retries.', 'answer': 'Retries are 99. [OLD1]'}]
    def handler(request):
        payload = json.loads(request.content)
        instructions = payload['messages'][0]['content']
        assert 'NOT evidence' in instructions and 'Earlier assistant replies may be wrong' in instructions
        context = json.loads(payload['messages'][1]['content'])
        assert context['untrusted_conversation'] == history
        assert payload['format']['$defs']['Statement']['properties']['source_ids']['items']['enum'] == ['S1']
        return httpx.Response(200, json={'message': {'content': json.dumps({
            'statements': [{'text': 'The retry limit is 3.', 'source_ids': ['S1']}], 'missing_information': ''})}})
    monkeypatch.setattr(service.httpx, 'AsyncClient', lambda **kw:
                        real_client(transport=httpx.MockTransport(handler), **kw))
    result = asyncio.run(ollama_answer('What is its retry limit?', [
        {'source_id': 'S1', 'path': 'worker.py', 'start': 1, 'end': 1, 'text': 'MAX_RETRIES = 3'}], history))
    assert result['statements'][0]['source_ids'] == ['S1']


@pytest.mark.parametrize('question', [
    'Explain the complete request flow.', 'What happens when a request arrives?',
    'What is the logic behind this flow?', 'Compare both upload paths.',
])
def test_explanations_have_room_for_sequence_and_qualifications(question):
    assert not focused_question(question)
    assert answer_schema(question)['properties']['statements']['maxItems'] == 6


def test_model_change_invalidates_only_derived_vectors(workspace):
    index, scan = workspace
    index.prepare_vectors(1, 'model-a')
    rows = index.unembedded(1)
    index.save_vectors(1, [(r['id'], [1, 0]) for r in rows])
    index.prepare_vectors(1, 'model-a')
    assert index.embedded(1) == len(rows)
    revision = index.revision
    index.prepare_vectors(1, 'model-b')
    assert index.embedded(1) == 0
    assert index.revision == revision and index.active_scan() == scan
    assert index.search('database', scan)[0]['path'] == 'db.py'


def test_first_question_backfills_existing_snapshot_without_rescan(workspace, monkeypatch):
    index, scan = workspace
    revision = index.revision
    monkeypatch.setenv('PKA_EMBED_MODEL', 'nomic-embed-text')
    calls = []
    async def vectors(texts):
        calls.append(texts)
        return [[1.0, 0.0] if text.startswith('search_document:') or 'database' in text
                else [0.0, 1.0] for text in texts]
    monkeypatch.setattr(embed, 'vectors', vectors)
    async def generate(question, sources):
        return {'statements': [], 'missing_information': 'Test.'}
    svc = Service(index, connector_factory=connector, generator=generate)
    asyncio.run(svc.ask('Which database is configured?'))
    assert index.embedded(1) > 0 and index.revision == revision
    assert any(text.startswith('search_document:') for batch in calls for text in batch)
    assert any(text.startswith('search_query:') for batch in calls for text in batch)
    calls.clear()
    asyncio.run(svc.ask('Which database is configured?'))
    assert all(not text.startswith('search_document:') for batch in calls for text in batch)


def test_unavailable_semantic_model_keeps_lexical_answers_and_cools_down(workspace, monkeypatch):
    index, scan = workspace
    monkeypatch.setenv('PKA_EMBED_MODEL', 'nomic-embed-text')
    calls = []
    async def unavailable(texts):
        calls.append(texts)
        return None
    monkeypatch.setattr(embed, 'vectors', unavailable)
    async def generate(question, sources):
        return {'statements': [{'text': 'PostgreSQL with asyncpg.', 'source_ids': [sources[0]['source_id']]}],
                'missing_information': ''}
    svc = Service(index, connector_factory=connector, generator=generate)
    first = asyncio.run(svc.ask('Which database is configured?'))
    count = len(calls)
    second = asyncio.run(svc.ask('Which database is configured?'))
    assert first['statements'] and second['statements']
    assert len(calls) == count and count > 0


def test_vectors_with_different_dimensions_are_never_compared():
    assert embed.similarity([1, 0], [1, 0, 0]) == 0


def test_repeated_embedding_preparation_respects_snapshot_cap(workspace, monkeypatch):
    index, scan = workspace
    monkeypatch.setattr(embed, 'MAX_CHUNKS', 1)
    rows = index.unembedded(1)
    assert len(rows) == 1
    index.save_vectors(1, [(rows[0]['id'], [1, 0])])
    assert index.unembedded(1) == []


def test_http_question_passes_bounded_context_to_service(tmp_path):
    from auth_helpers import OwnerClient
    from pka.web import create_app
    app = create_app(db_path=tmp_path / 'api-context.sqlite3', connector_factory=connector)
    received = {}
    async def ask(question, conversation=None):
        received.update(question=question, conversation=conversation)
        return {'ok': True}
    app.state.service.ask = ask
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request': '1'}) as client:
        payload = {'question': 'Why?', 'conversation': {'repo': 'acme/shop', 'commit': COMMIT,
            'knowledge_revision': 2, 'turns': [{'question': 'Explain uploads.', 'answer': 'PNG only.'}]}}
        assert client.post('/api/ask', json=payload).status_code == 200
        assert isinstance(received['conversation'], Conversation)
        assert received['conversation'].turns[0].question == 'Explain uploads.'
        payload['conversation']['turns'] *= 5
        assert client.post('/api/ask', json=payload).status_code == 422
