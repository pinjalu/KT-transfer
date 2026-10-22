"""Relationships require explicit evidence; text similarity must stay visibly uncertain."""
import asyncio
from contextlib import asynccontextmanager
import json

import httpx
import pytest

from pka import credentials, jira_links
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource, COMMIT
from pka.connectors.jira import issue_blocks
from pka.index import Index
from pka.service import Service
from pka.web import create_app

SCAN = {'id':1, 'repo':'acme/shop', 'branch':'main', 'commit':COMMIT, 'status':'complete'}
JIRA = 'https://acme.atlassian.net/browse/ENG-1'


def run(coro): return asyncio.run(coro)


def issue(text='Protect receipt downloads'):
    return [{'source_id':'J1','path':'jira/ENG-1','start':1,'end':4,
             'text':'ENG-1: '+text, 'url':JIRA}]


def row(text, path='app/receipts.py', rid=1, start=10, url=''):
    return {'id':rid,'path':path,'start':start,'end':start+text.count('\n'), 'text':text,'url':url}


def links(sources, rows, kind='files', **kwargs):
    return jira_links.related('ENG-1', sources, rows, SCAN, kind, **kwargs)


@pytest.mark.parametrize('text', ['# ENG-1: restrict receipt downloads', '# See '+JIRA,
                                 '# See <'+JIRA+'|task>', '# See [task]('+JIRA+')'])
def test_explicit_issue_key_or_correct_jira_url_confirms_link(text):
    result = links(issue(), [row(text)])
    item = result['items'][0]
    assert item['confidence'] == 'confirmed' and item['reason']
    assert text in item['text'] and '/blob/'+COMMIT+'/app/receipts.py#L10' in item['url']


@pytest.mark.parametrize('text', ['ENG-10', 'XENG-1', 'ENG-1_extra', 'OPS-1',
    'https://other.atlassian.net/browse/ENG-1', '[ENG-1](https://other.atlassian.net/browse/ENG-1)',
    '<https://other.atlassian.net/browse/ENG-1|ENG-1>'])
def test_other_keys_and_foreign_site_urls_never_confirm_selected_issue(text):
    assert links(issue('Work'), [row(text)])['items'] == []


@pytest.mark.parametrize('reference', ['app/receipts.py', '`./app/receipts.py`',
    'https://github.com/acme/shop/blob/main/app/receipts.py#L10',
    'https://github.com/acme/shop/blob/'+COMMIT+'/app/receipts.py'])
def test_task_names_existing_file_and_preserves_both_sides_of_reference(reference):
    result = links(issue('Change '+reference), [row('def download():\n    pass')])
    item = result['items'][0]
    assert item['confidence'] == 'confirmed' and reference in item['evidence']['text']
    assert item['evidence']['url'] == JIRA
    assert 'def download' in item['text'] and COMMIT in item['url']


@pytest.mark.parametrize('reference', ['app/receipts.py.bak', 'other/app/receipts.py', 'app/Receipts.py',
    'https://github.com/other/shop/blob/main/app/receipts.py',
    'https://github.com/acme/shop/blob/old-revision/app/receipts.py'])
def test_unread_case_mismatched_and_out_of_scope_file_references_are_not_confirmed(reference):
    assert links(issue('Change '+reference), [row('pass')])['items'] == []


def test_lexical_overlap_is_possible_and_admin_fields_cannot_create_matches():
    result = links(issue(), [row('def receipt_downloads():\n    return download_receipt()')])
    assert result['items'][0]['confidence'] == 'possible'
    assert set(result['items'][0]['shared_words']) >= {'receipt','downloads'}
    sparse = issue('Today work\nType Feature, status In Progress, priority Medium, assigned to nobody.\nReported by Engineer on 2026-10-22.\nRank:\n0|i0000x:')
    assert links(sparse, [row('engineer priority medium rank progress today work')])['items'] == []
    assert links(issue('receipt'), [row('receipt')])['items'] == [], 'One common word is insufficient'


@pytest.mark.parametrize('description,code', [
    ('Complete all work under our own permissions. Hand off version.', 'all under own off version'),
    ('Change the function in the existing application', 'def function(): # change application'),
    ('Ensure receipt downloads work for everyone', 'everyone work ensure receipt'),
])
def test_common_language_and_code_scaffolding_cannot_create_possible_links(description,code):
    assert links(issue(description),[row(code)])['items']==[]
    assert links(issue(description),[row('# ENG-1 '+code)])['confirmed']==1


def test_strongest_file_excerpt_wins_and_pagination_counts_all_matches():
    rows = [row('receipt downloads',rid=1), row('# ENG-1',rid=2,start=50)]
    rows += [row('# ENG-1',f'app/file{i}.py',rid=3+i) for i in range(14)]
    first = links(issue(), rows, limit=10)
    second = links(issue(), rows, offset=10, limit=10)
    assert first['total'] == first['confirmed'] == 15 and first['next_offset'] == 10
    assert second['next_offset'] is None and len(second['items']) == 5
    found = next(item for item in first['items']+second['items'] if item['path']=='app/receipts.py')
    assert found['start'] == 50 and '# ENG-1' in found['text']
    assert len({item['id'] for item in first['items']+second['items']}) == 15


def test_long_line_excerpt_contains_actual_match_and_is_bounded():
    item = links(issue('Work'), [row('x'*5000+' ENG-1 '+'y'*5000)])['items'][0]
    assert len(item['text']) <= 1400 and 'ENG-1' in item['text'] and item['shortened']


def test_slack_key_and_recorded_permalink_link_blocks_without_inventing_decisions():
    permalink = 'https://acme.slack.com/archives/C1/p1700000000000000'
    rows = [row('[2026-10-22 10:00] U1: Proposal for ENG-1: allow receipt downloads',
                'slack/team',url=permalink), row('Unrelated discussion','slack/team',rid=2,start=2)]
    result = links(issue(),rows,'discussions')
    assert result['confirmed'] == 1 and result['items'][0]['url'] == permalink
    assert 'U1' in result['items'][0]['text'] and 'Proposal' in result['items'][0]['text']
    forward = links(issue('See '+permalink),[row('Recorded discussion','slack/team',url=permalink)],'discussions')
    assert forward['confirmed'] == 1 and forward['items'][0]['evidence']['url'] == JIRA
    missing = links(issue(),[row('ENG-1 discussion','slack/team')],'discussions')['items'][0]
    assert missing['url'] == ''


def test_malformed_urls_cannot_break_link_search_or_create_links():
    assert links(issue('Work'), [row('https://[broken')])['items'] == []
    assert links(issue('https://[broken'), [row('pass')])['items'] == []
    item = links(issue(), [row('ENG-1 discussion', 'slack/team', url='https://[broken')], 'discussions')['items'][0]
    assert item['url'] == ''


class Sources(FixtureSource):
    gh_denied = None
    jira_denied = None
    slack_denied = None
    changed_head = False
    after_access = None
    def __init__(self): self.checks=[]
    async def check_access(self,commit=''):
        self.checks.append('github')
        if self.gh_denied: raise self.gh_denied
        if self.after_access: self.after_access()
        return {'head':'b'*40 if self.changed_head else COMMIT}
    async def jira_begin_read(self): return {'issues':1,'blocks':1,'coverage':{'state':'complete'}}
    async def jira_issues(self,cursor=0):
        return {'blocks':issue_blocks('https://acme.atlassian.net',{'key':'ENG-1','fields':{
            'summary':'Check app/auth.py for login password behavior'}}),'next_cursor':None}
    async def jira_check_issues_access(self,issue_keys,snapshots=None):
        self.checks.append('jira')
        if self.jira_denied: raise self.jira_denied
        return {'checked':len(issue_keys)}
    async def slack_messages(self,channel_id):
        return [{'ts':'1700000000.0','user':'U1','text':'ENG-1: proposed login password handling.'}]
    async def slack_check_channel_access(self,channel_id,snapshot_digest=''):
        self.checks.append('slack')
        if self.slack_denied: raise self.slack_denied
        return {'readable':True,'channel':channel_id,'snapshot':snapshot_digest}


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_EMBED_MODEL','')
    monkeypatch.setenv('PKA_DATA_DIR',str(tmp_path))
    monkeypatch.setattr(credentials,'ENV_PATH',tmp_path/'unused.env')
    for name in ('JIRA_SITE','JIRA_EMAIL','JIRA_API_TOKEN','SLACK_USER_TOKEN','GITHUB_TOKEN'):
        monkeypatch.setenv(name,'fixture')
    source=Sources()
    @asynccontextmanager
    async def factory(settings,demo=False): yield source
    index=Index(tmp_path/'index.sqlite3')
    index.configure({'repo':'acme/shop','branch':'main'})
    svc=Service(index,connector_factory=factory)
    run(svc.scan())
    index.configure_source('jira',{'project':'ENG'})
    index.configure_slack({'workspace':'acme','channels':[{'id':'C1','name':'team'}]})
    run(svc.read_jira('ENG'))
    run(svc.read_slack('acme',index.settings()['slack']['channels']))
    source.checks.clear()
    return svc,source,factory


def test_related_reads_only_current_project_and_required_sources_without_model(state):
    svc,source,_=state
    files=run(svc.jira_task_links('ENG-1'))
    assert source.checks==['github','jira'] and any(i['path']=='app/auth.py' for i in files['items'])
    assert all(not i['path'].startswith(('jira/','slack/')) for i in files['items'])
    source.checks.clear()
    discussions=run(svc.jira_task_links('ENG-1','discussions'))
    assert source.checks==['jira','slack'] and discussions['confirmed']==1
    assert all(i['path'].startswith('slack/') for i in discussions['items'])
    assert svc.job is None and svc.index.jira_explanation('ENG-1') is None
    assert 'identity' not in json.dumps(files)+json.dumps(discussions)


@pytest.mark.parametrize('provider,kind', [('github','files'),('jira','files'),('slack','discussions')])
def test_revoked_access_withholds_relationships_and_discards_affected_source(state,provider,kind):
    svc,source,_=state
    setattr(source, 'gh_denied' if provider=='github' else provider+'_denied',SourceError('access_denied','Revoked'))
    with pytest.raises(SourceError): run(svc.jira_task_links('ENG-1',kind))
    if provider=='github': assert svc.index.active_scan() is None
    else: assert svc.index.source_import(provider) is None


def test_slack_outage_does_not_block_jira_explanation_or_file_links(state):
    svc,source,_=state
    source.slack_denied=SourceError('network','Slack unavailable')
    with pytest.raises(SourceError): run(svc.jira_task_links('ENG-1','discussions'))
    assert svc.index.source_import('slack')
    assert run(svc.jira_task_detail('ENG-1'))['sources']
    assert run(svc.jira_task_links('ENG-1','files'))['items']


@pytest.mark.parametrize('change', ['head','credentials','snapshot'])
def test_changed_repository_or_identity_during_checks_never_returns_files(state,monkeypatch,change):
    svc,source,_=state
    if change=='head': source.changed_head=True
    elif change=='credentials': source.after_access=lambda:monkeypatch.setenv('GITHUB_TOKEN','new-reader')
    else: source.after_access=lambda:svc.index.discard_source('jira')
    with pytest.raises(SourceError): run(svc.jira_task_links('ENG-1'))


def test_unread_slack_and_sparse_task_are_explicit_empty_results(state):
    svc,_,_=state
    svc.index.discard_source('slack')
    result=run(svc.jira_task_links('ENG-1','discussions'))
    assert result['items']==[] and result['coverage']=='not_read' and result['searched']==0


def test_refresh_recomputes_links_without_a_stale_relationship_cache(state):
    svc,source,_=state
    before=run(svc.jira_task_links('ENG-1','discussions'))
    async def messages(channel): return [{'ts':'1700000000.0','text':'Different content with no reference.'}]
    source.slack_messages=messages
    run(svc.read_slack('acme',svc.index.settings()['slack']['channels']))
    after=run(svc.jira_task_links('ENG-1','discussions'))
    assert before['confirmed']==1 and after['items']==[] and after['revision']>before['revision']


def test_api_validates_kind_page_selection_and_private_response_headers(state):
    svc,_,factory=state
    app=create_app(False,svc.index.path,connector_factory=factory)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost:8000',headers={'X-PKA-Request':'1'}) as client:
            assert (await client.get('/api/jira/tasks/ENG-1/links')).status_code==409
            await client.post('/api/config',json={'repo':'acme/shop','branch':'main'})
            reply=await client.get('/api/jira/tasks/ENG-1/links')
            assert reply.status_code==200 and 'no-store' in reply.headers['cache-control']
            assert reply.json()['items']
            for query in ('kind=other','offset=-1','limit=26','limit=0'):
                assert (await client.get('/api/jira/tasks/ENG-1/links?'+query)).status_code==422
            assert (await client.get('/api/jira/tasks/OPS-1/links')).status_code==409
            assert (await client.get('/api/jira/tasks/ENG-999/links')).status_code==409
            await client.post('/api/config',json={'repo':'acme/different','branch':'main'})
            assert (await client.get('/api/jira/tasks/ENG-1/links')).status_code==409
    run(scenario())
