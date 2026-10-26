"""Task 5.2: saved evaluations, exact-answer review and source isolation."""
import asyncio
from contextlib import asynccontextmanager
import copy
import json

import httpx
import pytest

from auth_helpers import auth_cookies
from pka import quality
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource
from pka.config import source_url
from pka.index import Index, chunk_file
from pka.web import create_app


COMMIT = 'a' * 40
CASE = {'id': 'database', 'question': 'Which database and driver does the project use?', 'behavior': 'answer',
        'facts': [{'id': 'database', 'phrases': [['PostgreSQL'], ['asyncpg']],
                   'references': [{'path': 'README.md', 'start': 1, 'end': 10}]}]}
SPEC = {'version': 1, 'repo': 'acme/shop', 'commit': COMMIT, 'cases': [CASE, {**CASE, 'id': 'second'}]}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(quality, 'SETS', {'test_set': ('Fixture questions', 'unused.json')})
    original = quality.spec_for
    monkeypatch.setattr(quality, 'spec_for', lambda name: copy.deepcopy(SPEC) if name == 'test_set' else original(name))
    source = FixtureSource()
    @asynccontextmanager
    async def factory(settings, demo=False):
        yield source
    app = create_app(True, tmp_path / 'index.sqlite3', connector_factory=factory)
    svc = app.state.service
    index = svc.index
    index.configure({'repo': 'acme/shop', 'branch': 'main'})
    scan = {'repo': 'acme/shop', 'branch': 'main', 'commit': COMMIT, 'status': 'complete', 'finished': '2026-10-26'}
    scan_id = index.new_scan(scan)
    index.save_scan(scan_id, scan)
    index.activate(scan_id, chunk_file('README.md', '# Project database\nThis project uses PostgreSQL with the asyncpg driver for all database connections.'), scan)
    svc.demo = False
    calls = []
    async def ask(question):
        calls.append(question)
        answer = {'repo': 'acme/shop', 'commit': COMMIT, 'knowledge_revision': index.revision,
                  'statements': [{'text': 'PostgreSQL is accessed using asyncpg.', 'source_ids': ['S1']}],
                  'sources': [{'source_id': 'S1', 'path': 'README.md', 'start': 1, 'end': 2,
                               'url': source_url('acme/shop', COMMIT, 'README.md', 1, 2), 'text': 'PRIVATE_SOURCE'}],
                  'missing_information': '', 'error': None, 'elapsed_seconds': 0.1}
        answer['answer_id'] = index.record_answer(scan_id, question, answer, 0.1)
        return answer
    monkeypatch.setattr(svc, 'ask', ask)
    return app, svc, source, calls


async def completed(svc):
    run_id = svc.start_job('evaluation', target='test_set')
    await svc.task
    assert svc.job['state'] == 'succeeded'
    return run_id


def test_run_uses_ask_and_retains_metrics_without_source_text(setup):
    app, svc, source, calls = setup
    run_id = asyncio.run(completed(svc))
    report = quality.runs(svc.index, run_id)[0]
    assert len(calls) == 2
    assert report['summary']['automatic_checks_passed'] == 2
    assert report['quality_acceptance'] == 'pending_human_review'
    assert report['summary']['human_reviewed'] == 0
    assert 'PRIVATE_SOURCE' not in json.dumps(report)
    assert CASE['question'] not in json.dumps(report)
    detail = asyncio.run(quality.inspect(svc, run_id, 'database'))
    assert detail['answer']['sources'][0]['text'] == 'PRIVATE_SOURCE'
    assert detail['case']['question'] == CASE['question']


def test_browser_api_review_binds_hashes_and_uses_authenticated_identity(setup):
    app, svc, source, calls = setup
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://localhost:8000',
                cookies=auth_cookies(app), headers={'X-PKA-Request': '1'}) as client:
            catalog = await client.get('/api/quality')
            assert catalog.status_code == 200 and catalog.json()['sets'][0]['available']
            start = await client.post('/api/quality/runs', json={'set_id': 'test_set'})
            assert start.status_code == 200
            await svc.task
            run_id = start.json()['job_id']
            path = f'/api/quality/runs/{run_id}/cases/database'
            detail = (await client.get(path)).json()
            item = {'dataset_hash': detail['dataset_hash'], 'response_hash': detail['result']['response_hash'],
                    'correctness': 'partially correct', 'source_sufficiency': 'insufficient'}
            bad = await client.post(path + '/review', json={**item, 'response_hash': 'b' * 64})
            assert bad.status_code == 409
            forged = await client.post(path + '/review', json={**item, 'reviewer': 'someone else'})
            assert forged.status_code == 422
            reply = await client.post(path + '/review', json=item)
            assert reply.status_code == 200
            assert reply.json()['review']['reviewer'] == 'fixture-owner'
            report = (await client.get('/api/quality')).json()['runs'][0]
            assert report['summary']['human_correctness']['partially correct'] == 1
            assert report['summary']['human_source_sufficiency']['insufficient'] == 1
            assert report['quality_acceptance'] == 'pending_human_review'
    asyncio.run(scenario())


@pytest.mark.parametrize('mutation', ['repo', 'commit', 'demo', 'unknown'])
def test_wrong_scope_or_unknown_set_never_starts(setup, mutation):
    app, svc, source, calls = setup
    if mutation == 'repo':
        svc.index.configure({'repo': 'another/repo', 'branch': 'main'})
    elif mutation == 'commit':
        scan = svc.index.active_scan()
        svc.index.save_scan(scan['id'], {**scan, 'commit': 'b' * 40})
    elif mutation == 'demo':
        svc.demo = True
    async def scenario():
        with pytest.raises(SourceError):
            svc.start_job('evaluation', target='../test_set' if mutation == 'unknown' else 'test_set')
    asyncio.run(scenario())
    assert not calls and not quality.runs(svc.index)


def test_cancel_and_retry_preserve_partial_run_and_start_fresh(setup, monkeypatch):
    app, svc, source, calls = setup
    original = svc.ask
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow(question):
            entered.set()
            await release.wait()
            return await original(question)
        monkeypatch.setattr(svc, 'ask', slow)
        first = svc.start_job('evaluation', target='test_set')
        await entered.wait()
        with pytest.raises(SourceError, match='Another task'):
            svc.start_job('evaluation', target='test_set')
        svc.cancel_job(first)
        release.set()
        await svc.task
        assert svc.job['state'] == 'cancelled'
        assert len(quality.runs(svc.index, first)[0]['results']) == 1
        second = svc.start_job('evaluation', retry_id=first)
        await svc.task
        assert second != first and svc.job['state'] == 'succeeded'
        assert len(quality.runs(svc.index, second)[0]['results']) == 2
    asyncio.run(scenario())


def test_revision_change_cannot_publish_or_resurrect_old_evaluation(setup, monkeypatch):
    app, svc, source, calls = setup
    original = svc.ask
    async def changed(question):
        answer = await original(question)
        svc.index.configure_source('jira', {'project': 'OTHER'})
        return answer
    monkeypatch.setattr(svc, 'ask', changed)
    async def scenario():
        svc.start_job('evaluation', target='test_set')
        await svc.task
        assert svc.job['state'] == 'failed'
    asyncio.run(scenario())
    assert not quality.runs(svc.index)


@pytest.mark.parametrize('change', ['rescan', 'source', 'repository', 'invalidate'])
def test_source_changes_remove_runs_and_exact_answers(setup, change):
    app, svc, source, calls = setup
    run_id = asyncio.run(completed(svc))
    if change == 'rescan':
        svc.index.new_scan({'repo': 'acme/shop', 'branch': 'main'})
    elif change == 'source':
        svc.index.configure_source('jira', {'project': 'CHANGED'})
    elif change == 'repository':
        svc.index.configure({'repo': 'another/repo', 'branch': 'main'})
    else:
        svc.index.invalidate()
    assert not quality.runs(svc.index)
    with pytest.raises(SourceError):
        quality.retained(svc.index, run_id, 'database')


def test_revoked_access_cannot_expose_saved_answer(setup, monkeypatch):
    app, svc, source, calls = setup
    run_id = asyncio.run(completed(svc))
    async def denied(commit):
        raise SourceError('access_denied', 'Access denied.')
    monkeypatch.setattr(source, 'check_access', denied)
    with pytest.raises(SourceError):
        asyncio.run(quality.inspect(svc, run_id, 'database'))
    assert not quality.runs(svc.index)


def test_modified_answer_or_question_set_is_not_reviewable(setup, monkeypatch):
    app, svc, source, calls = setup
    run_id = asyncio.run(completed(svc))
    report = quality.runs(svc.index, run_id)[0]
    with svc.index.db() as db:
        db.execute("UPDATE answers SET response='{}' WHERE id=?", (report['results'][0]['answer_id'],))
    with pytest.raises(SourceError, match='exact answer'):
        quality.retained(svc.index, run_id, 'database')
    monkeypatch.setattr(quality, 'spec_for', lambda name: {**SPEC, 'label_provenance': 'changed'})
    with pytest.raises(SourceError, match='question set changed'):
        quality.retained(svc.index, run_id, 'second')


def test_restart_marks_run_interrupted_and_other_workspace_cannot_read_it(setup, tmp_path):
    app, svc, source, calls = setup
    run_id = asyncio.run(completed(svc))
    svc.job['state'] = 'running'
    svc.index.save_job(svc.job)
    reopened = Index(svc.index.path)
    reopened.recover()
    assert quality.runs(reopened, run_id)[0]['state'] == 'interrupted'
    other = Index(tmp_path / 'other.sqlite3')
    assert quality.runs(other, run_id) == []
    with pytest.raises(SourceError):
        quality.retained(other, run_id, 'database')


def test_all_shipped_question_sets_are_valid():
    # Resolve independently of the fixture catalog patch.
    from pka.config import ROOT
    from pka.answer_evaluation import validate_spec
    for path in (ROOT / 'evals').glob('answers_*.json'):
        validate_spec(json.loads(path.read_text(encoding='utf-8')))


def test_run_through_real_answer_pipeline(setup, monkeypatch):
    from pka.service import Service
    app, svc, source, calls = setup
    monkeypatch.setattr(svc, 'ask', Service.ask.__get__(svc))
    generated = []
    async def generator(question, sources, **kwargs):
        generated.append(question)
        return {'statements': [{'text': 'The project uses PostgreSQL with the asyncpg driver.',
                                'source_ids': [sources[0]['source_id']]}], 'missing_information': ''}
    svc.generator = generator
    async def scenario():
        job = svc._new_job('evaluation', target='test_set')
        await quality.run(svc, 'test_set')
        return job['id']
    run_id = asyncio.run(scenario())
    report = quality.runs(svc.index, run_id)[0]
    assert len(generated) == 2
    assert report['summary']['automatic_checks_passed'] == 2
    assert quality.retained(svc.index, run_id, 'database')[3]['sources']


def test_generation_error_stops_batch_without_counting_it_as_correct(setup, monkeypatch):
    app, svc, source, calls = setup
    original = svc.ask
    async def failed(question):
        answer = await original(question)
        answer['error'] = 'Fixture generator unavailable'
        return answer
    monkeypatch.setattr(svc, 'ask', failed)
    async def scenario():
        run_id = svc.start_job('evaluation', target='test_set')
        await svc.task
        assert svc.job['state'] == 'partial'
        report = quality.runs(svc.index, run_id)[0]
        assert len(report['results']) == 1 and not report['run_complete']
        assert report['summary']['automatic_checks_passed'] == 0
        assert report['summary']['human_reviewed'] == 0
    asyncio.run(scenario())
