"""Coverage reflects bounded reads, including gaps that used to look like success."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from pka import coverage, credentials
from pka.config import LIMITS
from pka.connectors import jira, slack
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource
from pka.index import Index
from pka.service import Service
from pka.web import create_app


def run(work):
    return asyncio.run(work)


def message(ts='1700000000.0', **kwargs):
    return {'ts':ts, 'user':'U1', 'text':'Authentication requires a password', **kwargs}


def issue(key='ENG-1', **fields):
    return {'key':key, 'fields':{'summary':'Authenticate users', 'comment':{'comments':[], 'total':0}, **fields}}


def slack_reader(history, replies=None):
    def handler(request):
        assert request.method == 'GET'
        if request.url.path.endswith('conversations.history'):
            return httpx.Response(200, json=history(request) if callable(history) else history)
        assert request.url.path.endswith('conversations.replies')
        return httpx.Response(200, json=replies or {'ok':False, 'error':'missing_scope'})
    return slack.SlackSource('fixture', httpx.MockTransport(handler))


@pytest.mark.parametrize('gap', ['message_limit', 'page_limit', 'missing_cursor', 'repeated_cursor'])
def test_slack_history_gaps_are_partial(monkeypatch, gap):
    monkeypatch.setattr(slack, 'LIMITS', replace(LIMITS, slack_max_messages=1 if gap == 'message_limit' else 10,
                                               slack_max_pages=1 if gap == 'page_limit' else 10))
    reader = slack_reader({'ok':True, 'messages':[message()], 'has_more':True,
                          'response_metadata':{'next_cursor':'' if gap == 'missing_cursor' else 'again'}})
    result = run(reader.read_channel('C1'))
    assert result['coverage']['state'] == 'partial'
    assert any('history is incomplete' in n for n in result['coverage']['notes'])
    assert result['coverage']['pages'] <= 2


@pytest.mark.parametrize('count', [0, 1])
def test_slack_complete_empty_or_exact_limit_is_not_reported_as_truncated(monkeypatch, count):
    monkeypatch.setattr(slack, 'LIMITS', replace(LIMITS, slack_max_messages=1))
    reader = slack_reader({'ok':True, 'messages':[message()]*count, 'has_more':False})
    result = run(reader.read_channel('C1'))
    assert result['coverage']['state'] == 'complete'
    assert result['coverage']['history_messages'] == count


@pytest.mark.parametrize('gap', ['failed', 'thread_limit', 'reply_page', 'reply_count'])
def test_slack_thread_gaps_are_not_silently_successful(monkeypatch, gap):
    monkeypatch.setattr(slack, 'LIMITS', replace(LIMITS, slack_max_threads=0 if gap == 'thread_limit' else 40))
    replies = None if gap == 'failed' else {'ok':True, 'messages':[message(), message('1700000001.0')],
                                          'has_more':gap == 'reply_page'}
    reader = slack_reader({'ok':True, 'messages':[message(reply_count=2 if gap == 'reply_count' else 1)],
                           'has_more':False}, replies)
    result = run(reader.read_channel('C1'))
    assert result['coverage']['state'] == 'partial'
    assert result['coverage']['notes']
    assert 'Authentication requires a password' not in json.dumps(result['coverage'])


def test_slack_replies_count_is_separate_from_messages():
    reader = slack_reader({'ok':True, 'messages':[message(reply_count=1)], 'has_more':False},
                          {'ok':True, 'messages':[message(), message('1700000001.0')]})
    result = run(reader.read_channel('C1'))
    assert len(result['messages']) == 2
    assert result['coverage']['history_messages'] == result['coverage']['replies'] == 1
    assert result['coverage']['state'] == 'complete'


def jira_reader(handler):
    return jira.JiraSource('https://fixture.atlassian.net', 'fixture@example.com', 'fixture',
                           httpx.MockTransport(handler))


@pytest.mark.parametrize('gap', ['issue_limit', 'page_limit', 'missing_token', 'repeated_token'])
def test_jira_issue_limits_and_pagination_gaps_are_reported(monkeypatch, gap):
    monkeypatch.setattr(jira, 'LIMITS', replace(LIMITS, jira_max_issues=1 if gap == 'issue_limit' else 10,
                                              jira_max_pages=1 if gap == 'page_limit' else 10))
    reader = jira_reader(lambda r: httpx.Response(200, json={'issues':[issue()], 'isLast':False,
        'nextPageToken':'' if gap == 'missing_token' else 'again'}))
    run(reader.issues('ENG'))
    assert reader.last_coverage['state'] == 'partial'
    assert any('More issues' in n for n in reader.last_coverage['notes'])
    assert reader.last_coverage['pages'] <= 2


@pytest.mark.parametrize('legacy', [False, True])
def test_jira_follows_pages_and_completes_at_exact_limit(monkeypatch, legacy):
    monkeypatch.setattr(jira, 'LIMITS', replace(LIMITS, jira_max_issues=2))
    calls = []
    def handler(request):
        calls.append(request)
        if legacy and request.url.path.endswith('/search/jql'):
            return httpx.Response(410)
        second = request.url.params.get('startAt') == '1' if legacy else request.url.params.get('nextPageToken') == 'page2'
        body = {'issues':[issue('ENG-2' if second else 'ENG-1')]}
        body.update({'total':2} if legacy else {'isLast':second, 'nextPageToken':'' if second else 'page2'})
        return httpx.Response(200, json=body)
    reader = jira_reader(handler)
    assert len(run(reader.issues('ENG'))) == 2
    assert reader.last_coverage['state'] == 'complete'
    assert len(calls) == (3 if legacy else 2)


@pytest.mark.parametrize('gap', ['comments', 'comment_limit', 'text_limit', 'unknown_comments'])
def test_jira_comment_and_text_gaps_are_visible(monkeypatch, gap):
    monkeypatch.setattr(jira, 'LIMITS', replace(LIMITS, jira_max_comments=1))
    comment = {'body':'A comment', 'author':{'displayName':'Someone'}}
    fields = {'comment':{'comments':[comment]*(2 if gap == 'comment_limit' else 1),
                         'total':2 if gap in {'comments','comment_limit'} else 1}}
    if gap == 'unknown_comments': fields['comment'].pop('total')
    if gap == 'text_limit': fields['description'] = 'Long description. ' * 400
    reader = jira_reader(lambda r: httpx.Response(200, json={'isLast':True, 'issues':[issue(**fields)]}))
    run(reader.issues('ENG'))
    assert reader.last_coverage['state'] == ('unknown' if gap == 'unknown_comments' else 'partial')
    assert reader.last_coverage['notes']


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('PKA_EMBED_MODEL', '')
    monkeypatch.setattr(credentials, 'ENV_PATH', tmp_path/'unused.env')
    class Source(FixtureSource):
        partial = True
        async def slack_read(self, channel_id):
            if channel_id == 'C2': raise SourceError('network', 'Channel temporarily unavailable.')
            return {'messages':[message()], 'coverage':{'state':'partial' if self.partial else 'complete',
                    'notes':['Additional replies not read.'] if self.partial else []}}
        async def jira_begin_read(self):
            return {'issues':1, 'blocks':1, 'coverage':{'state':'partial' if self.partial else 'complete',
                    'notes':['Some comments were not read.'] if self.partial else []}}
        async def jira_issues(self, cursor=0):
            return {'blocks':[jira.issue_block('https://fixture.atlassian.net', issue())], 'next_cursor':None}
    source = Source()
    @asynccontextmanager
    async def factory(settings, demo=False): yield source
    index = Index(tmp_path/'index.sqlite3')
    index.configure({'repo':'demo/example-shop','branch':'main'})
    svc = Service(index, demo=True, connector_factory=factory)
    run(svc.scan())
    index.configure_source('jira', {'project':'ENG'})
    index.configure_slack({'workspace':'fixture','channels':[{'id':'C1','name':'engineering'}]})
    return svc, source, factory


@pytest.mark.parametrize('kind', ['jira','slack'])
def test_partial_coverage_survives_restart_and_sets_partial_job(state, kind):
    svc, source, factory = state
    async def work():
        svc.start_job(kind)
        await svc.task
        assert svc.job_status()['state'] == 'partial'
        assert svc.job_status()['can_retry']
    run(work())
    fresh = Service(Index(svc.index.path), demo=True, connector_factory=factory)
    report = coverage.describe(fresh)['sources'][kind]
    assert report['state'] == 'partial' and report['read_at'] and report['available']
    assert 'Authentication requires a password' not in json.dumps(report)
    source.partial = False
    async def retry():
        fresh.start_job(kind, retry_id=fresh.job['id'])
        await fresh.task
    run(retry())
    assert coverage.describe(fresh)['sources'][kind]['state'] == 'complete'


def test_failed_channels_are_distinct_from_empty_success_and_old_imports(state):
    svc, _, _ = state
    svc.index.configure_slack({'workspace':'fixture','channels':[{'id':'C1','name':'engineering'},{'id':'C2','name':'ops'}]})
    run(svc.read_slack('fixture', svc.index.settings()['slack']['channels']))
    report = coverage.describe(svc)['sources']['slack']
    assert report['state'] == 'partial' and report['summary'] == '1 of 2 selected channels read.'
    assert report['details'][1]['summary'] == 'Failed to read'
    assert report['details'][1]['notes'] == ['Channel temporarily unavailable.']
    meta = svc.index.source_import('slack')
    meta['report'].pop('coverage_state')
    for channel in meta['report']['channels']:
        channel['error'] = ''; channel.pop('coverage', None)
    svc.index.replace_source(svc.index.active_scan()['id'], 'slack/', [], meta)
    assert coverage.describe(svc)['sources']['slack']['state'] == 'unknown'


def test_no_import_and_successful_empty_import_are_distinct(state):
    svc, _, _ = state
    assert coverage.describe(svc)['sources']['jira']['state'] == 'not_read'
    svc.index.replace_source(svc.index.active_scan()['id'], 'jira/', [],
        {'report':{'project':'ENG','read_at':'2026-10-22','issues':0,'blocks':0,'coverage':{'state':'complete','notes':[]}}})
    assert coverage.describe(svc)['sources']['jira']['state'] == 'complete'
    svc.index.configure_source('jira', {'project':'OTHER'})
    assert coverage.describe(svc)['sources']['jira']['state'] == 'not_read'


def test_failed_refresh_shows_previous_saved_read_separately(state):
    svc, source, _ = state
    run(svc.read_jira('ENG'))
    saved_at = svc.index.source_import('jira')['report']['read_at']
    async def fail(): raise SourceError('network','Jira temporarily unavailable.')
    source.jira_begin_read = fail
    async def work():
        svc.start_job('jira'); await svc.task
    run(work())
    report = coverage.describe(svc)['sources']['jira']
    assert report['read_at'] == saved_at and report['available']
    assert report['attempt']['state'] == 'failed'
    assert report['state'] == 'partial'


def test_repository_coverage_preserves_policy_exclusions_and_unknown_tree_size():
    result = coverage.repository({'status':'partial','read':3,'skipped':1,'failed':1,'total':7,'processed':5,
        'tree_incomplete':True,'files':[{'state':'skipped','reason':'potential_secret_file'},
                                      {'state':'failed','reason':'Unreadable file'}]}, True)
    assert any('unknown' in n for n in result['notes'])
    assert metric_value(result, 'Not processed') == 2
    assert any(d['name'] == 'potential secret file' for d in result['details'])


def metric_value(report, label):
    return next(c['value'] for c in report['counts'] if c['label'] == label)


def test_api_coverage_hides_previous_project_until_reconnected(state, tmp_path):
    svc, _, factory = state
    app = create_app(False, svc.index.path, connector_factory=factory)
    client = TestClient(app, base_url='http://localhost:8000')
    headers = {'x-pka-request':'1'}
    assert client.get('/api/import-coverage', headers=headers).json() == {'sources':{}}
    assert client.get('/api/import-coverage').status_code == 403
    client.post('/api/config', headers=headers, json={'repo':'demo/example-shop','branch':'main'})
    response = client.get('/api/import-coverage', headers=headers)
    assert response.status_code == 200
    assert response.json()['sources']['github']['state'] == 'complete'


def test_mcp_transports_coverage_without_changing_legacy_list_contract(monkeypatch):
    from pka import mcp_server as server
    reader = slack_reader({'ok':True,'has_more':False,'messages':[message()]})
    monkeypatch.setattr(server, 'SLACK_CHANNELS', {'C1'})
    monkeypatch.setattr(server, 'slack', lambda: reader)
    assert isinstance(run(server.slack_read_channel('C1'))['data'], list)
    assert run(server.slack_read_channel('C1', include_coverage=True))['data']['coverage']['state'] == 'complete'
    assert not run(server.slack_read_channel('C2', include_coverage=True))['ok']
