import asyncio
import copy
import json
import sqlite3

import httpx
import pytest

from pka import answer_evaluation as evaluation
from pka.config import source_url

COMMIT = 'a' * 40
FACT = {'id': 'database', 'phrases': [['PostgreSQL', 'Postgres'], ['asyncpg']],
        'references': [{'path': 'db.py', 'start': 1, 'end': 10}]}
CASE = {'id': 'database', 'question': 'Which database and driver?', 'behavior': 'answer', 'facts': [FACT]}
SPEC = {'version': 1, 'repo': 'acme/shop', 'commit': COMMIT, 'cases': [CASE]}


def answer():
    return {'repo': 'acme/shop', 'commit': COMMIT, 'answer_id': 3,
            'statements': [{'text': 'PostgreSQL is accessed using asyncpg.', 'source_ids': ['S1']}],
            'sources': [{'source_id': 'S1', 'path': 'db.py', 'start': 1, 'end': 20,
                         'url': source_url('acme/shop', COMMIT, 'db.py', 1, 20), 'text': 'PRIVATE_SOURCE'}],
            'missing_information': '', 'error': None, 'elapsed_seconds': 1.5}


def test_cited_reference_checks_are_separate_from_human_correctness():
    row = evaluation.score_answer(CASE, answer(), SPEC)
    assert row['status'] == 'passed_checks'
    assert row['retrieval']['reference_excerpt_found'] is True
    assert row['human_review'] is None
    assert 'PRIVATE_SOURCE' not in json.dumps(row)
    assert 'PostgreSQL is accessed' not in json.dumps(row)


@pytest.mark.parametrize('mutation', ['unknown_citation', 'uncited', 'duplicate', 'wrong_link', 'wrong_scope', 'error'])
def test_broken_answers_fail_mechanical_checks(mutation):
    body = answer()
    if mutation == 'unknown_citation':
        body['statements'][0]['source_ids'] = ['S99']
    elif mutation == 'uncited':
        body['statements'][0]['source_ids'] = []
    elif mutation == 'duplicate':
        body['sources'].append(copy.deepcopy(body['sources'][0]))
    elif mutation == 'wrong_link':
        body['sources'][0]['url'] = 'https://github.com/acme/shop/blob/main/db.py'
    elif mutation == 'wrong_scope':
        body['commit'] = 'b' * 40
    else:
        body['error'] = 'PRIVATE_UPSTREAM_ERROR'
    row = evaluation.score_answer(CASE, body, SPEC)
    assert row['status'] == 'failed_checks'
    assert 'PRIVATE_UPSTREAM_ERROR' not in json.dumps(row)


def test_reference_phrase_must_occur_in_statement_citing_reference_excerpt():
    body = answer()
    body['statements'][0]['text'] = 'The application has a database.'
    body['missing_information'] = 'PostgreSQL asyncpg'
    assert evaluation.score_answer(CASE, body, SPEC)['reference_phrase_checks'][0]['cited_reference_phrase_match'] is False
    body['statements'][0]['text'] = 'PostgreSQL asyncpg'
    body['sources'][0].update(start=50, end=70)
    row = evaluation.score_answer(CASE, body, SPEC)
    assert row['retrieval']['reference_excerpt_found'] is False
    assert row['reference_phrase_checks'][0]['cited_reference_phrase_match'] is False


def test_refusal_is_not_credited_for_generation_failure():
    case = {'id': 'reject', 'behavior': 'abstain', 'facts': []}
    body = answer()
    body.update(statements=[], sources=[], missing_information='No evidence.', error='Model unavailable.')
    assert evaluation.score_answer(case, body, SPEC)['status'] == 'failed_checks'
    body['error'] = None
    row = evaluation.score_answer(case, body, SPEC)
    assert row['status'] == 'passed_checks'
    assert row['citations']['references'] == 0
    assert row['retrieval']['reference_excerpt_found'] is None


def test_phrase_overlap_is_not_a_factual_accuracy_verdict():
    body = answer()
    body['statements'][0]['text'] = 'This does not use PostgreSQL or asyncpg.'
    row = evaluation.score_answer(CASE, body, SPEC)
    assert row['reference_phrase_checks'][0]['cited_reference_phrase_match'] is True
    report = evaluation.summarize({'cases_planned': 1, 'results': [row]})
    assert report['quality_acceptance'] == 'pending_human_review'
    assert report['summary']['human_correctness']['correct'] == 0


@pytest.mark.parametrize('url', ['https://example.com', 'http://127.0.0.1:8000@evil.example',
                                'http://127.0.0.1:8000/path', 'http://localhost:8000?token=private'])
def test_evaluation_cannot_send_questions_to_remote_urls(url):
    with pytest.raises(ValueError):
        evaluation.local_url(url)


def test_duplicate_cases_and_empty_reference_labels_are_refused():
    spec = copy.deepcopy(SPEC)
    spec['cases'].append(copy.deepcopy(CASE))
    with pytest.raises(ValueError):
        evaluation.validate_spec(spec)
    spec = copy.deepcopy(SPEC)
    spec['cases'][0]['facts'] = []
    with pytest.raises(ValueError):
        evaluation.validate_spec(spec)


def test_live_pipeline_uses_real_app_route_and_does_not_export_content(tmp_path):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        assert request.headers['X-PKA-Request'] == '1'
        if request.url.path == '/api/status':
            return httpx.Response(200, json={'ready': True, 'busy': False, 'demo': False,
                'model': 'local-model', 'last_successful_scan': '2026-10-01T09:00:00+05:30',
                'scan': {'status': 'partial', 'repo': 'acme/shop', 'commit': COMMIT}})
        assert json.loads(request.content) == {'question': CASE['question']}
        return httpx.Response(200, json=answer())

    path = tmp_path / 'report.json'
    report = asyncio.run(evaluation.run_live(SPEC, path, transport=httpx.MockTransport(handler)))
    assert calls == [('GET', '/api/status'), ('POST', '/api/ask')]
    assert report['automatic_checks_passed'] is True
    assert report['scan_status'] == 'partial'
    assert report['quality_acceptance'] == 'pending_human_review'
    saved = path.read_text()
    assert 'PRIVATE_SOURCE' not in saved and CASE['question'] not in saved
    assert 'PostgreSQL is accessed' not in saved


@pytest.mark.parametrize('changed', [{'repo': 'other/repo'}, {'commit': 'b' * 40}])
def test_wrong_project_or_commit_is_rejected_before_asking(tmp_path, changed):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={'ready': True, 'busy': False, 'demo': False,
            'scan': {'status': 'partial', 'repo': 'acme/shop', 'commit': COMMIT, **changed}})
    with pytest.raises(ValueError):
        asyncio.run(evaluation.run_live(SPEC, tmp_path / 'report.json', transport=httpx.MockTransport(handler)))
    assert calls == ['/api/status']


def test_failed_request_stops_run_and_checkpoint_has_no_response_body(tmp_path):
    spec = copy.deepcopy(SPEC)
    spec['cases'].append({**CASE, 'id': 'second'})
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/api/status':
            return httpx.Response(200, json={'ready': True, 'scan': {'status': 'partial', 'repo': 'acme/shop', 'commit': COMMIT}})
        return httpx.Response(503, text='PRIVATE_SERVICE_BODY')
    path = tmp_path / 'report.json'
    report = asyncio.run(evaluation.run_live(spec, path, transport=httpx.MockTransport(handler)))
    assert calls.count('/api/ask') == 1
    assert report['run_complete'] is False
    assert 'PRIVATE_SERVICE_BODY' not in path.read_text()


def test_human_reviews_bind_to_exact_answers_and_keep_sufficiency_separate():
    row = evaluation.score_answer(CASE, answer(), SPEC)
    report = {'dataset_hash': evaluation.digest(SPEC), 'cases_planned': 1, 'results': [row]}
    reviews = {'dataset_hash': report['dataset_hash'], 'reviews': [
        {'case_id': 'database', 'response_hash': row['response_hash'], 'reviewer_type': 'human',
         'reviewer': 'Tester', 'correctness': 'partially correct', 'source_sufficiency': 'sufficient'}]}
    updated = evaluation.apply_reviews(copy.deepcopy(report), reviews)
    assert updated['quality_acceptance'] == 'human_review_complete'
    assert updated['summary']['human_correctness']['partially correct'] == 1
    reviews['reviews'][0]['response_hash'] = 'not-this-response'
    with pytest.raises(ValueError):
        evaluation.apply_reviews(copy.deepcopy(report), reviews)
    reviews['reviews'][0]['response_hash'] = row['response_hash']
    reviews['reviews'][0]['reviewer_type'] = 'model'
    with pytest.raises(ValueError):
        evaluation.apply_reviews(copy.deepcopy(report), reviews)


def test_no_cases_measured_does_not_report_perfect_rates():
    report = evaluation.summarize({'cases_planned': 2, 'results': []})
    assert report['summary']['reference_retrieval_rate'] is None
    assert report['summary']['cited_reference_phrase_rate'] is None
    assert not report['automatic_checks_passed'] and not report['run_complete']


@pytest.mark.parametrize('field,value', [('repo', None), ('commit', 123)])
def test_non_string_scope_labels_are_rejected(field, value):
    with pytest.raises(ValueError):
        evaluation.validate_spec({**SPEC, field: value})


def test_missing_information_must_be_text():
    body = answer()
    body['missing_information'] = ['not a disclosure']
    with pytest.raises(ValueError):
        evaluation.score_answer(CASE, body, SPEC)


def test_review_batch_is_validated_before_any_rating_changes():
    row = evaluation.score_answer(CASE, answer(), SPEC)
    report = {'dataset_hash': evaluation.digest(SPEC), 'cases_planned': 1, 'results': [row]}
    reviews = {'dataset_hash': report['dataset_hash'], 'reviews': [
        {'case_id': 'database', 'response_hash': row['response_hash'], 'reviewer_type': 'human',
         'reviewer': 'Tester', 'correctness': 'correct', 'source_sufficiency': 'sufficient'},
        {'case_id': 'not-in-report'}]}
    with pytest.raises(ValueError):
        evaluation.apply_reviews(report, reviews)
    assert report['results'][0]['human_review'] is None


@pytest.mark.parametrize('changed', [{'repo': 'other/project'}, {'commit': 'b' * 40}])
def test_retrieval_cli_refuses_labels_for_another_scope(tmp_path, monkeypatch, changed):
    from pka import evaluate
    spec = {'repo': 'acme/shop', 'commit': COMMIT,
            'questions': [{'id': 'one', 'band': 'lexical', 'ask': 'database', 'expect': ['db.py']}]}
    path = tmp_path / 'retrieval.json'
    path.write_text(json.dumps(spec))
    class FakeIndex:
        def active_scan(self):
            return {'id': 1, 'repo': 'acme/shop', 'commit': COMMIT, **changed}
        def embedded(self, scan):
            pytest.fail('A mismatched set must stop before scoring or embedding.')
    monkeypatch.setattr(evaluate, 'Index', lambda path: FakeIndex())
    assert evaluate.main(['--set', str(path), '--db', 'unused']) == 1


def test_review_inspection_reads_exact_retained_answer_and_refuses_stale_records(tmp_path):
    path = tmp_path / 'index.sqlite3'
    body = answer()
    report = {'results': [evaluation.score_answer(CASE, body, SPEC)]}
    saved = {k: v for k, v in body.items() if k != 'answer_id'}
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE answers(id INTEGER, scan_id INTEGER, question TEXT, response TEXT)')
        db.execute('CREATE TABLE active(id INTEGER, scan_id INTEGER)')
        db.execute('INSERT INTO active VALUES(1,10)')
        db.execute('INSERT INTO answers VALUES(3,10,?,?)', (CASE['question'], json.dumps(saved)))
    before = path.read_bytes()
    inspected = evaluation.inspect_case(report, 'database', path)
    assert inspected['question'] == CASE['question']
    assert inspected['sources'][0]['text'] == 'PRIVATE_SOURCE'
    assert path.read_bytes() == before, 'Inspection must not mutate the database.'
    with pytest.raises(ValueError):
        evaluation.inspect_case(report, 'missing', path)
    report['results'][0]['response_hash'] = 'different-answer'
    with pytest.raises(ValueError):
        evaluation.inspect_case(report, 'database', path)
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM answers')
    with pytest.raises(ValueError):
        evaluation.inspect_case(report, 'database', path)
