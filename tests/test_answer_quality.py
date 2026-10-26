import asyncio
import json

import httpx
import pytest

from pka.config import now
from pka.index import Index, chunk_file
from pka.service import GroundedAnswer, answer_schema, focused_question, ollama_answer


@pytest.fixture
def repository(tmp_path):
    index = Index(tmp_path / 'index.sqlite3')
    index.configure({'repo': 'example/service', 'branch': 'main'})
    scan = {'id': 1, 'repo': 'example/service', 'commit': 'a' * 40,
            'status': 'complete', 'finished': now()}
    return index, scan


@pytest.mark.parametrize('value', ['vector-alpha-v2', 'vector-beta-v9'])
@pytest.mark.parametrize('question', [
    'Which model is used for embeddings?',
    'I want to ask about the name of the model which we use for embeddings',
    'What is the embedding model?',
])
def test_retrieval_returns_configured_value_not_classifier_name(repository, value, question):
    index, scan = repository
    text = 'import os\nEMBED_MODEL = "' + value + '"\n\n'
    text += ''.join(f'def unrelated_{i}():\n    return {i}\n\n' for i in range(40))
    text += 'def embed_query(text):\n    return client.embeddings.create(model=EMBED_MODEL, input=text)\n'
    chunks = chunk_file('vectors.py', text)
    chunks += chunk_file('classify.py', ''.join(
        f'def norm_model_{i}(name):\n    """Map a model name to a canonical model."""\n    return name\n\n'
        for i in range(85)))
    index.activate(1, chunks, scan)
    sources = index.search(question, scan)
    assert value in sources[0]['text']
    assert sources[0]['path'] == 'vectors.py'
    assert sources[0]['start'] <= 2 <= sources[0]['end']
    assert sum(len(s['text']) for s in sources) <= 7200


@pytest.mark.parametrize('path,source,question,expected', [
    ('server.ts', 'export const serverPort = 9321;\n', 'What port does the server use?', '9321'),
    ('limits.json', '{\n  "requestTimeout": 23\n}\n', 'What is the request timeout?', '23'),
    ('images.py', 'IMAGE_FORMATS = {".avif", ".png"}\n', 'Which image formats are accepted?', '.avif'),
])
def test_definition_ranking_generalizes_to_other_values_and_languages(repository, path, source, question, expected):
    index, scan = repository
    chunks = chunk_file(path, source)
    chunks += chunk_file('helpers.py', 'def model_name(name):\n    return name\n')
    index.activate(1, chunks, scan)
    found = index.search(question, scan)
    assert found[0]['path'] == path and expected in found[0]['text']


def test_missing_definition_is_not_invented_and_unrelated_questions_still_refuse(repository):
    index, scan = repository
    index.activate(1, chunk_file('vectors.py',
        'def embed_query(text):\n    return client.embeddings.create(model=EMBED_MODEL, input=text)\n'), scan)
    found = index.search('Which embedding model is used?', scan)
    assert found and not any('EMBED_MODEL =' in s['text'] for s in found)
    assert not index.search('quasar nebula zebras', scan)


def test_ollama_can_refuse_when_retrieved_excerpts_do_not_answer(monkeypatch):
    from pka import service
    real_client = httpx.AsyncClient
    def handler(request):
        body = json.loads(request.content)
        assert 'vector-alpha' not in body['messages'][0]['content']
        return httpx.Response(200, json={'message': {'content': json.dumps({
            'statements': [], 'missing_information': 'The model value is not defined in the supplied excerpts.'})}})
    monkeypatch.setattr(service.httpx, 'AsyncClient', lambda **kwargs:
                        real_client(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(ollama_answer('Which embedding model is used?', [
        {'source_id': 'S1', 'path': 'vectors.py', 'start': 1, 'end': 2,
         'text': 'def embed(text):\n    return client.embed(model=MODEL, input=text)'}]))
    assert result['statements'] == [] and result['missing_information']


def test_a_refusal_must_explain_the_gap():
    with pytest.raises(ValueError):
        GroundedAnswer(statements=[], missing_information='   ')


@pytest.mark.parametrize('question', ['Which model do we use?', 'What is the server port?',
                                    'How many retries are configured?', 'Where is the timeout set?',
                                    'Can a public image prove private signing works?',
                                    'Does retry create a new job ID?'])
def test_focused_schema_cannot_combine_an_answer_with_a_missing_message(question):
    schema = answer_schema(question)
    complete, missing = schema['anyOf']
    assert complete['properties']['statements']['maxItems'] == 1
    assert complete['properties']['missing_information']['const'] == ''
    assert missing['properties']['statements']['maxItems'] == 0
    assert missing['properties']['missing_information']['minLength'] == 1


@pytest.mark.parametrize('question', ['Explain how requests are authenticated',
                                    'Compare the two storage implementations',
                                    'How does the pipeline work?'])
def test_explanations_keep_room_for_partial_evidence_and_details(question):
    assert not focused_question(question)
    assert answer_schema(question)['properties']['statements']['maxItems'] == 4


@pytest.mark.parametrize('question', [
    'Which database and Python driver does the service use?',
    'What command starts the worker, and which port does it use?',
])
def test_multi_part_lookup_keeps_room_for_each_requested_fact(question):
    schema = answer_schema(question)
    assert schema['anyOf'][0]['properties']['statements']['maxItems'] == 2


@pytest.mark.parametrize('question', ['Which database is configured?', 'Explain how storage works'])
def test_generation_schema_limits_citations_to_actual_retrieved_ids(question):
    schema = answer_schema(question, [{'source_id': 'S2'}, {'source_id': 'S8'}])
    allowed = schema['$defs']['Statement']['properties']['source_ids']['items']['enum']
    assert allowed == ['S2', 'S8']


def test_named_file_lookup_cannot_borrow_other_uploaders_formats(repository):
    index, scan = repository
    chunks = chunk_file('images.py', 'IMAGE_FORMATS = {".avif", ".png"}\n')
    chunks += chunk_file('documents.py', 'DOCUMENT_FORMATS = {".pdf"}\n')
    index.activate(1, chunks, scan)
    found = index.search('Which formats does images.py accept?', scan)
    assert found and all(s['path'] == 'images.py' for s in found)
    related = index.search('Compare formats in images.py and documents.py', scan)
    assert {s['path'] for s in related} == {'images.py', 'documents.py'}


def test_documented_service_heading_beats_proxy_mentions(repository):
    index, scan = repository
    docs = '# Application\n\n## Worker API\n\nRun the worker with:\n```sh\nuvicorn worker:app --port 8123\n```\n'
    proxy = '# Web proxy\n# Starts a command to talk to the Worker API on a port.\nPORT = 3100\n'
    index.activate(1, chunk_file('README.md', docs) + chunk_file('proxy.py', proxy), scan)
    found = index.search('What command starts the Worker API, and which port does it use?', scan)
    assert found[0]['path'] == 'README.md' and '8123' in found[0]['text']


def test_bold_command_labels_rank_a_run_section_before_architecture(repository):
    index, scan = repository
    docs = ('# Application\n\n## Architecture\n\nThe Worker API calls another service.\n\n'
            '## Running\n\n**Worker API (port 8123)**\n```sh\nuvicorn worker:app --port 8123\n```\n')
    index.activate(1, chunk_file('README.md', docs), scan)
    found = index.search('What command starts the Worker API, and which port does it use?', scan)
    assert 'uvicorn worker:app --port 8123' in found[0]['text']
    assert len({(s['path'], s['start'], s['end']) for s in found}) == len(found)


@pytest.mark.parametrize('name', ['assistant-nova', 'assistant-solis'])
def test_answering_bot_model_is_not_confused_with_a_vehicle_model(repository, name):
    index, scan = repository
    chunks = chunk_file('chat.py', f'CHAT_MODEL = "{name}"\n')
    chunks += chunk_file('fleet.py', 'MOTORCYCLE_MODEL = "Roadster"\n# The bot answers questions about this motorcycle.\n')
    index.activate(1, chunks, scan)
    found = index.search('For answering questions in this bot which model is used?', scan)
    assert found[0]['path'] == 'chat.py' and name in found[0]['text']
    vehicle = index.search('Which motorcycle model does the bot cover?', scan)
    assert vehicle[0]['path'] == 'fleet.py' and 'Roadster' in vehicle[0]['text']
