import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json

import httpx
import pytest

from pka import test_plans
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource
from pka.index import Index, chunk_file
from pka.service import Service, focused_question, ollama_answer


SOURCES = [{'source_id': 'S1', 'path': 'images.py', 'start': 1, 'end': 3,
            'text': 'Private images require a signed URL. A public image is not evidence that private signing succeeded.'}]


def raw_plan():
    return {'tests': [{
        'title': 'Read a private image with its signed URL',
        'reason': 'A public fallback could hide a broken private signing path.',
        'setup': ['Supply a known private test image and its object key.'],
        'steps': ['Request a signed URL for the private test image.', 'Fetch the image using the returned signed URL.'],
        'expected_result': 'The signed request should return the intended private image content.',
        'verification': ['Compare the response bytes with the known test image and record the signing path.'],
        'assumptions': ['The test operator must supply the object key; it is not in the excerpt.'],
        'evidence': [{'source_id': 'S1', 'quote': 'Private images require a signed URL.'}],
    }], 'missing_information': ''}


@pytest.mark.parametrize('question', [
    'Suggest two tests for private S3 image signing based on SCRUM-24.',
    'What tests should we add for the 0.45 handoff threshold?',
    'Which integration tests are missing for retry?',
    'How can we test a database timeout?',
    'Recommend checks for access failures.',
])
def test_test_requests_are_not_reduced_to_fact_lookups(question):
    assert test_plans.requested(question)
    assert not focused_question(question)


@pytest.mark.parametrize('question', [
    'Which tests already exist?', 'Have the tests passed?', 'Explain the existing retry tests.',
    'A response scores exactly 0.45. Will it suggest handoff?',
    'Do not suggest tests; tell me the current threshold.', 'What does suggestHandoff do?',
    'Does the generator create tests?',
])
def test_existing_test_and_fact_questions_keep_the_normal_answer_path(question):
    assert not test_plans.requested(question)


def test_requested_count_is_bounded_and_does_not_read_threshold_or_ticket_numbers_as_counts():
    assert test_plans.count('Suggest one test for SCRUM-24 at 0.45') == (1, 1)
    assert test_plans.count('Suggest tests for SCRUM-24 at 0.45') == (2, 2)
    assert test_plans.count('Suggest three regression tests') == (3, 3)
    assert test_plans.count('Suggest 12 tests') == (4, 12)
    assert test_plans.count('Suggest three security tests') == (3, 3)
    assert test_plans.count('Suggest SCRUM-24 tests') == (2, 2)


def test_valid_plan_has_server_assigned_suggestion_status_and_preserves_verification():
    result = test_plans.prepare(raw_plan(), 'Suggest one test for private images', SOURCES)
    test = result['test_suggestions'][0]
    assert test['status'] == 'suggested_not_run'
    assert test['evidence'][0]['kind'] == 'code'
    assert 'response bytes' in test['verification'][0]
    assert result['statements'][0]['text'].startswith('Suggested test:')
    assert result['statements'][0]['source_ids'] == ['S1']


@pytest.mark.parametrize('fault', ['missing_steps', 'summary_only', 'no_reason', 'empty_verification',
                                  'unknown_citation', 'invented_quote', 'forged_status', 'execution_claim'])
def test_summary_only_incomplete_forged_or_uncited_plans_are_withheld(fault):
    plan = raw_plan()
    test = plan['tests'][0]
    if fault == 'missing_steps': del test['steps']
    if fault == 'summary_only': plan = {'statements': [{'text': 'The project uses private images.', 'source_ids': ['S1']}], 'missing_information': ''}
    if fault == 'no_reason': test['reason'] = '   '
    if fault == 'empty_verification': test['verification'] = []
    if fault == 'unknown_citation': test['evidence'][0]['source_id'] = 'S999'
    if fault == 'invented_quote': test['evidence'][0]['quote'] = 'All private signing tests passed in production.'
    if fault == 'forged_status': test['status'] = 'verified_code'
    if fault == 'execution_claim': test['reason'] = 'We executed the private image test and confirmed it passed.'
    with pytest.raises(SourceError):
        test_plans.prepare(plan, 'Suggest one test for private images', SOURCES)


def test_duplicate_and_unexplained_incomplete_counts_are_rejected_but_explicit_gap_is_preserved():
    plan = raw_plan()
    with pytest.raises(SourceError): test_plans.prepare(plan, 'Suggest two tests', SOURCES)
    plan['tests'].append(deepcopy(plan['tests'][0]))
    with pytest.raises(SourceError): test_plans.prepare(plan, 'Suggest two tests', SOURCES)
    plan = raw_plan()
    plan['missing_information'] = 'Only one scenario is grounded; no failure-path requirements were retrieved.'
    assert test_plans.prepare(plan, 'Suggest two tests', SOURCES)['missing_information']
    assert test_plans.prepare({'tests': [], 'missing_information': 'No relevant implementation or requirement was retrieved.'},
                              'Suggest two tests', SOURCES)['test_suggestions'] == []


def test_generation_uses_structured_schema_and_keeps_history_as_untrusted_context(monkeypatch):
    captured = []
    async def request(payload, started):
        captured.append(payload)
        result = raw_plan()
        result['tests'][0]['evidence'] = [{'evidence_id': 'E1'}]
        return httpx.Response(200, json={'message': {'content': json.dumps(result)}})
    monkeypatch.setattr('pka.service._ask_ollama', request)
    raw = asyncio.run(ollama_answer('Suggest one test for private images', SOURCES, history=[{'question': 'Earlier', 'answer': 'Untrusted claim'}]))
    assert raw['tests']
    payload = captured[0]
    assert payload['format']['properties']['tests']['maxItems'] == 1
    assert payload['format']['$defs']['Evidence']['properties']['evidence_id']['enum'] == ['E1']
    assert raw['tests'][0]['evidence'] == [{'source_id': 'S1', 'quote': SOURCES[0]['text']}]
    assert 'untrusted DATA' in payload['messages'][0]['content']
    assert 'untrusted_conversation' in json.loads(payload['messages'][1]['content'])


def test_evidence_selections_cannot_mix_a_quote_with_another_source():
    sources = [*SOURCES, {**SOURCES[0], 'source_id': 'S2', 'text': 'Another source describes a different public image.'}]
    choices = test_plans.evidence_choices(sources)
    plan = raw_plan()
    plan['tests'][0]['evidence'] = [{'evidence_id': 'E2'}]
    resolved = test_plans.resolve_evidence(plan, choices)
    assert resolved['tests'][0]['evidence'] == [{'source_id': 'S2', 'quote': sources[1]['text']}]
    assert test_plans.prepare(resolved, 'Suggest one test', sources)['test_suggestions']
    for item in ({'evidence_id': 'E999'}, {'evidence_id': 'E1', 'source_id': 'S2'},
                 {'source_id': 'S1', 'quote': 'Invented evidence'}):
        plan = raw_plan()
        plan['tests'][0]['evidence'] = [item]
        with pytest.raises(SourceError): test_plans.resolve_evidence(plan, choices)


def test_evidence_context_preserves_code_indentation_and_short_lines_without_duplicating_text():
    source = {**SOURCES[0], 'text': 'if ready:\n    return value\nelse:\n    return None\n#'}
    choices = test_plans.evidence_choices([source])
    context = test_plans.evidence_context([source], choices)[0]['text']
    assert context == '[E1] if ready:\n[E2]     return value\nelse:\n[E3]     return None\n#'
    assert context.count('return value') == 1


def service(tmp_path):
    index = Index(tmp_path / 'index.sqlite3')
    index.configure({'repo': 'acme/images', 'branch': 'main'})
    scan = {'repo': 'acme/images', 'branch': 'main', 'commit': 'a' * 40, 'status': 'complete', 'finished': '2026-10-26'}
    scan_id = index.new_scan(scan)
    index.activate(scan_id, chunk_file('images.py', SOURCES[0]['text']), scan)
    @asynccontextmanager
    async def factory(settings, demo=False): yield FixtureSource()
    async def generate(question, sources, **kwargs):
        raw = raw_plan()
        raw['tests'][0]['evidence'][0]['source_id'] = sources[0]['source_id']
        return raw
    return Service(index, connector_factory=factory, generator=generate)


def test_real_ask_pipeline_saves_structured_plan_and_never_marks_it_verified(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    svc = service(tmp_path)
    def numeric_shortcut(*args):
        raise AssertionError('Test requests must not become a numeric fact answer')
    monkeypatch.setattr('pka.service.checked_answer', numeric_shortcut)
    result = asyncio.run(svc.ask('Suggest one test for private signed images'))
    assert not result['error']
    assert result['test_suggestions'][0]['status'] == 'suggested_not_run'
    assert result['statements'][0]['evidence']['kind'] == 'suggestion'
    with svc.index.db() as db:
        saved = json.loads(db.execute('SELECT response FROM answers WHERE id=?', (result['answer_id'],)).fetchone()[0])
    assert saved['test_suggestions'] == result['test_suggestions']


def test_changed_sources_after_generation_prevent_plan_publication(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    svc = service(tmp_path)
    async def generate(question, sources):
        svc.index.invalidate()
        return raw_plan()
    svc.generator = generate
    with pytest.raises(SourceError): asyncio.run(svc.ask('Suggest one test for private signed images'))


def test_tiny_excerpts_disclose_a_gap_without_calling_the_model(monkeypatch):
    async def request(*args): raise AssertionError('No quote can support a test plan')
    monkeypatch.setattr('pka.service._ask_ollama', request)
    result = asyncio.run(test_plans.generate('Suggest one test', [{**SOURCES[0], 'text': 'x'}]))
    assert not result['tests'] and 'too little source text' in result['missing_information']
