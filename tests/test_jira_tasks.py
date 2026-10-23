from auth_helpers import auth_cookies
"""Selected-issue explanations: evidence isolation, access, jobs and persisted results."""
import asyncio
from contextlib import asynccontextmanager
import json

import httpx
import pytest

from pka import credentials, jira_tasks
from pka.config import LIMITS
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource
from pka.connectors.jira import issue_blocks
from pka.index import Index
from pka.service import Service
from pka.web import create_app


def run(coro):
    return asyncio.run(coro)


def answer(source, phrase=None):
    phrase = phrase or source['text'].splitlines()[0]
    return {'summary':[{'text':phrase, 'source_id':source['source_id'], 'quote':phrase}],
            'requirements':[], 'acceptance_criteria':[], 'questions':[]}


class Source(FixtureSource):
    denied = None
    checks = 0

    def __init__(self):
        self.blocks = [block for key, title in [('ENG-1', 'Use qwen3:1.7b for local chat'),
                                                ('ENG-2', 'Encrypt billing receipts')]
                      for block in issue_blocks('https://fixture.atlassian.net', {
                          'key':key, 'fields':{'summary':title, 'description':'Requested: '+title,
                                              'comment':{'comments':[], 'total':0}}})]

    async def jira_begin_read(self):
        return {'project':'ENG', 'issues':2, 'blocks':len(self.blocks), 'coverage':{'state':'complete'}}

    async def jira_issues(self, cursor=0):
        return {'blocks':self.blocks, 'next_cursor':None}

    async def jira_check_issues_access(self, issue_keys, snapshots=None):
        self.checks += 1
        if self.denied:
            raise self.denied
        return {'checked':len(issue_keys)}

    async def slack_check_channel_access(self, channel_id):
        raise AssertionError('A Jira-only view must not need Slack access')


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_EMBED_MODEL', '')
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(credentials, 'ENV_PATH', tmp_path/'unused.env')
    for name in ('JIRA_SITE', 'JIRA_EMAIL', 'JIRA_API_TOKEN', 'SLACK_USER_TOKEN'):
        monkeypatch.setenv(name, 'fixture-only')
    source = Source()
    @asynccontextmanager
    async def factory(settings, demo=False):
        yield source
    index = Index(tmp_path/'index.sqlite3')
    index.configure({'repo':'acme/shop', 'branch':'main'})
    svc = Service(index, connector_factory=factory)
    run(svc.scan())
    index.configure_source('jira', {'project':'ENG'})
    run(svc.read_jira('ENG'))
    async def model(sources, part, total):
        return answer(sources[0])
    svc.jira_generator = model
    return svc, source, factory


@pytest.mark.parametrize('fault', ['foreign_id', 'foreign_quote', 'whitespace', 'bad_shape', 'empty_text'])
def test_rejects_unverifiable_or_malformed_points(fault):
    source = {'source_id':'J1','path':'jira/ENG-1','text':'Use qwen3:1.7b for local chat'}
    raw = answer(source)
    if fault == 'foreign_id': raw['summary'][0]['source_id'] = 'J9'
    elif fault == 'foreign_quote': raw['summary'][0]['quote'] = 'Encrypt billing receipts'
    elif fault == 'whitespace': raw['summary'][0]['quote'] = '    '
    elif fault == 'empty_text': raw['summary'][0]['text'] = '    '
    else: raw['extra'] = 'unrequested field'
    with pytest.raises(SourceError): jira_tasks.checked_points(raw, [source])


def test_preserves_names_and_exposes_exact_supporting_quote():
    source = {'source_id':'J1','path':'jira/ENG-1','text':'Use qwen3:1.7b for local chat'}
    result = jira_tasks.checked_points(answer(source), [source])
    assert result['summary'][0]['text'] == source['text']
    assert result['summary'][0]['quote'] == source['text']
    assert result['summary'][0]['source_ids'] == ['J1']


@pytest.mark.parametrize('quote', ['Reported by Engineer on 2026-10-22.', 'Rank:\n0|i0000x:',
                                  'Type Feature, status In Progress, priority Medium, assigned to nobody.',
                                  'Labels: sprint-one.'])
def test_jira_bookkeeping_is_not_a_requirement_or_acceptance_check(quote):
    source = {'source_id':'J1', 'path':'jira/ENG-9', 'text':'ENG-9: Work\n'+quote}
    raw = answer(source)
    point = {'text':quote, 'quote':quote, 'source_id':'J1'}
    raw['requirements'] = [point]
    raw['acceptance_criteria'] = [point]
    result = jira_tasks.checked_points(raw, [source], metadata=jira_tasks.metadata_text([source]))
    assert result['summary'] and result['requirements'] == result['acceptance_criteria'] == []


def test_metadata_classification_survives_excerpt_boundaries_and_keeps_real_requirements():
    sources = [{'source_id':'J1','path':'jira/ENG-1','text':'ENG-1: Work\nRank:\n0|i00'},
               {'source_id':'J2','path':'jira/ENG-1','text':'00x:\nDescription:\nUse qwen3:1.7b for local chat.'}]
    metadata = jira_tasks.metadata_text(sources)
    assert 'Rank: 0|i0000x:' in metadata
    raw = answer(sources[1], 'Use qwen3:1.7b for local chat.')
    raw['requirements'] = raw['summary']
    assert jira_tasks.checked_points(raw, [sources[1]], metadata=metadata)['requirements']


@pytest.mark.parametrize('quote,values', [
    ('Use qwen3:1.7b for chat and bge-small-en-v1.5 for embeddings.', ['qwen3:1.7b','bge-small-en-v1.5']),
    ('A different user receives HTTP 403; the owner receives HTTP 200.', ['403','200']),
    ('Run `process_queue` with a 30 second timeout.', ['process_queue','30']),
])
def test_omitted_literal_details_remain_visible_as_verified_source_wording(quote, values):
    source = {'source_id':'J1', 'path':'jira/ENG-1', 'text':quote}
    raw = answer(source)
    raw['summary'][0]['text'] = 'Use the specified configuration.'
    result = jira_tasks.checked_points(raw, [source])['summary'][0]
    assert all(value in result['text'] for value in values)
    assert 'Source wording:' in result['text'] and result['quote'] == quote


@pytest.mark.parametrize('quote', ['Allow receipt downloads only for the receipt owner.',
                                 'The service must use a 30 second timeout.'])
def test_explicit_request_in_summary_is_not_lost_from_requested_work(quote):
    source = {'source_id':'J1','path':'jira/ENG-1','text':'ENG-1: Task\nDescription:\n'+quote}
    result = jira_tasks.checked_points(answer(source, quote), [source])
    assert result['requirements'][0]['text'] == quote


def test_fallback_never_turns_current_behavior_or_comment_proposals_into_requests():
    for quote, prefix in [('The service currently runs locally.', 'Description:\n'),
                          ('Use a different model.', 'Description:\nExisting setup.\nComment by Engineer: ')]:
        source = {'source_id':'J1','path':'jira/ENG-1','text':'ENG-1: Task\n'+prefix+quote}
        assert jira_tasks.checked_points(answer(source, quote), [source])['requirements'] == []


def test_batches_read_all_text_including_oversized_legacy_excerpt():
    sources = [{'source_id':'J1','text':'a'*(LIMITS.context_chars*2+37)},
               {'source_id':'J2','text':'tail completion requirement'}]
    groups = jira_tasks.batches(sources)
    assert len(groups) == 3
    assert all(sum(len(s['text']) for s in group) <= LIMITS.context_chars for group in groups)
    assert ''.join(s['text'] for group in groups for s in group) == ''.join(s['text'] for s in sources)


def test_quote_choices_are_bounded_verbatim_and_include_late_conditions():
    text = 'Request '+('requirements '*100)+'\nAcceptance requires HTTP 403.\nRank:\n0|i0000x:'
    quotes = jira_tasks.quote_choices([{'text':text}])
    assert all(4 <= len(quote) <= 500 and quote in text for quote in quotes)
    assert 'Acceptance requires HTTP 403.' in quotes


def test_selected_issue_only_is_explained_and_cached_across_restart(state):
    svc, source, factory = state
    seen = []
    async def model(sources, part, total):
        seen.extend(sources)
        assert all(s['path'] == 'jira/ENG-1' for s in sources)
        assert 'billing' not in json.dumps(sources)
        return answer(sources[0])
    svc.jira_generator = model
    result = run(svc.explain_jira_task('eng-1'))
    assert result['issue_key'] == 'ENG-1' and seen
    assert result['model'] and result['generated_at'] and result['excerpts_read'] == len(seen)
    assert source.checks == 2, 'Check access before and after the model request'
    other = Service(Index(svc.index.path), connector_factory=factory)
    detail = run(other.jira_task_detail('ENG-1'))
    assert detail['explanation'] == result and source.checks == 3
    assert run(other.jira_task_detail('ENG-2'))['explanation'] is None


@pytest.mark.parametrize('action', ['refresh', 'project', 'credentials', 'revoke'])
def test_changes_invalidate_saved_explanations(state, monkeypatch, action):
    svc, source, _ = state
    run(svc.explain_jira_task('ENG-1'))
    if action == 'refresh': run(svc.read_jira('ENG'))
    elif action == 'project': svc.index.configure({'repo':'acme/other','branch':'main'})
    elif action == 'credentials':
        monkeypatch.setenv('JIRA_API_TOKEN', 'changed-reader')
        svc.sync_source_credentials()
    else:
        source.denied = SourceError('access_denied', 'Task was revoked')
        with pytest.raises(SourceError): run(svc.jira_task_detail('ENG-1'))
    assert svc.index.jira_explanation('ENG-1') is None


@pytest.mark.parametrize('endpoint', ['list', 'detail'])
def test_transient_access_failure_withholds_content_but_retains_cache(state, endpoint):
    svc, source, _ = state
    saved = run(svc.explain_jira_task('ENG-1'))
    source.denied = SourceError('network', 'Jira is unavailable')
    with pytest.raises(SourceError):
        run(svc.jira_task_list() if endpoint == 'list' else svc.jira_task_detail('ENG-1'))
    assert svc.index.jira_explanation('ENG-1') == saved


@pytest.mark.parametrize('fault', ['revoke', 'refresh', 'credentials'])
def test_changed_information_while_model_runs_never_publishes(state, monkeypatch, fault):
    svc, source, _ = state
    async def model(sources, part, total):
        if fault == 'revoke': source.denied = SourceError('access_denied', 'Task revoked')
        elif fault == 'refresh': svc.index.discard_source('jira')
        else: monkeypatch.setenv('JIRA_API_TOKEN', 'changed-reader')
        return answer(sources[0])
    svc.jira_generator = model
    with pytest.raises(SourceError): run(svc.explain_jira_task('ENG-1'))
    assert svc.index.jira_explanation('ENG-1') is None


def test_all_batches_contribute_and_do_not_claim_details_absent_from_other_parts(state):
    svc, source, _ = state
    source.blocks = issue_blocks('https://fixture.atlassian.net', {'key':'ENG-1', 'fields':{
        'summary':'Long requirements', 'description':'Review requirements. '*800 + '\nLate acceptance requires cobaltqueue.'}})
    run(svc.read_jira('ENG'))
    seen = []
    async def model(sources, part, total):
        seen.extend(sources)
        phrase = 'Late acceptance requires cobaltqueue.'
        chosen = next((s for s in sources if phrase in s['text']), sources[0])
        result = answer(chosen, phrase if phrase in chosen['text'] else chosen['text'].splitlines()[0][:100])
        result['questions'] = [{'text':'Which requirements are missing?', 'source_id':chosen['source_id'],
                                'quote':result['summary'][0]['quote']}]
        return result
    svc.jira_generator = model
    result = run(svc.explain_jira_task('ENG-1'))
    assert result['parts'] > 1 and result['questions'] == []
    assert 'cobaltqueue' in json.dumps(result['summary'])
    assert len(seen) == len(source.blocks) == result['excerpts_read']


def test_cancel_retry_keeps_target_and_never_publishes_cancelled_result(state):
    svc, _, _ = state
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def model(sources, part, total):
            entered.set()
            await release.wait()
            return answer(sources[0])
        svc.jira_generator = model
        first = svc.start_job('jira_task', target='ENG-2')
        await entered.wait()
        svc.cancel_job(first)
        release.set()
        await svc.task
        assert svc.job_status()['state'] == 'cancelled'
        assert svc.index.jira_explanation('ENG-2') is None
        svc.start_job('jira_task', retry_id=first)
        await svc.task
        assert svc.job_status()['state'] == 'succeeded' and svc.job['target'] == 'ENG-2'
        assert svc.job['attempt'] == 2 and svc.index.jira_explanation('ENG-2')
        assert svc.index.jira_explanation('ENG-1') is None
    run(scenario())


def test_interrupted_job_requires_retry_and_refresh_disables_stale_retry(state):
    svc, _, factory = state
    svc._new_job('jira_task', target='ENG-1')
    reopened = Index(svc.index.path)
    reopened.recover()
    other = Service(reopened, connector_factory=factory)
    assert other.job_status()['state'] == 'interrupted' and other.job_status()['can_retry']
    assert other.task is None
    run(other.read_jira('ENG'))
    assert not other.job_status()['can_retry']


def test_failed_refresh_retains_previous_successful_explanation(state):
    svc, _, _ = state
    saved = run(svc.explain_jira_task('ENG-1'))
    async def model(*args): raise SourceError('ollama', 'Model unavailable')
    svc.jira_generator = model
    async def scenario():
        svc.start_job('jira_task', target='ENG-1')
        await svc.task
        assert svc.job_status()['state'] == 'failed' and svc.job_status()['can_retry']
    run(scenario())
    assert svc.index.jira_explanation('ENG-1') == saved


def test_api_selection_boundary_background_lifecycle_and_no_automatic_generation(state):
    original, _, factory = state
    app = create_app(False, original.index.path, connector_factory=factory)
    svc = app.state.service
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def model(sources, part, total):
            entered.set()
            await release.wait()
            return answer(sources[0])
        svc.jira_generator = model
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), cookies=auth_cookies(app), base_url='http://localhost:8000',
                                     headers={'X-PKA-Request':'1'}) as client:
            assert (await client.get('/api/jira/tasks')).json()['issues'] == []
            assert (await client.get('/api/jira/tasks/ENG-1')).status_code == 409
            await client.post('/api/config', json={'repo':'acme/shop','branch':'main'})
            listing = await client.get('/api/jira/tasks')
            assert len(listing.json()['issues']) == 2
            assert 'no-store' in listing.headers['cache-control']
            for key in ('OPS-1','ENG-999','ENG-1?injection'):
                assert (await client.post('/api/jira/tasks/'+key+'/explain')).status_code in (404,405,409)
            assert (await client.get('/api/jira/tasks/ENG-1')).json()['explanation'] is None
            assert not entered.is_set()
            started = await client.post('/api/jira/tasks/ENG-1/explain')
            assert started.status_code == 200
            await entered.wait()
            assert (await client.post('/api/jira/tasks/ENG-2/explain')).status_code == 409
            assert (await client.get('/architecture')).status_code == 200
            status = (await client.get('/api/status')).json()
            assert status['job']['id'] == started.json()['job_id']
            assert status['job']['target'] == 'ENG-1' and status['job']['state'] == 'running'
            assert (await client.get('/api/jira/tasks/ENG-2')).json()['explanation'] is None
            release.set()
            await svc.task
            assert (await client.get('/api/jira/tasks/ENG-1')).json()['explanation']['issue_key'] == 'ENG-1'
            assert (await client.get('/api/status')).json()['job']['state'] == 'succeeded'
    run(scenario())


def test_ollama_prompt_and_schema_restrict_citations_and_request_all_parts(monkeypatch):
    captured = []
    async def request(payload, started):
        captured.append(payload)
        return httpx.Response(200, json={'message':{'content':json.dumps(answer({'text':'Selected task text', 'source_id':'J7'}))}})
    monkeypatch.setattr('pka.service._ask_ollama', request)
    sources = [{'source_id':'J7','text':'Selected task text'}]
    run(jira_tasks.generate(sources, 2, 3))
    payload = captured[0]
    assert payload['format']['$defs']['Point']['properties']['source_id']['enum'] == ['J7']
    assert payload['format']['$defs']['Point']['properties']['quote']['enum'] == ['Selected task text']
    assert payload['format']['properties']['questions']['maxItems'] == 0
    assert json.loads(payload['messages'][1]['content'])['part'] == 2
    assert 'untrusted DATA' in payload['messages'][0]['content']
