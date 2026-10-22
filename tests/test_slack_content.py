"""Task 6.5: real reader behavior against controlled Slack HTTP responses."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from pka import credentials, decisions
from pka.config import LIMITS
from pka.connectors import slack
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource, COMMIT
from pka.index import Index
from pka.service import Service
from pka.web import create_app


def run(work): return asyncio.run(work)


def msg(ts='1700000000.000001', text='We decided to use PostgreSQL for receipts.', **extra):
    return {'ts':ts,'user':'U1','text':text,**extra}


ROOT='1700000000.000001'
REPLY='1700000001.000001'


def page(messages, cursor='', **extra):
    return {'ok':True,'messages':messages,'has_more':bool(cursor),
            'response_metadata':{'next_cursor':cursor},**extra}


class SlackHTTP:
    def __init__(self):
        self.history={'':page([msg()])}
        self.replies={}
        self.calls=[]
        self.error=None
    def request(self, request):
        assert request.method=='GET'
        assert request.url.host=='slack.com'
        method=request.url.path.rsplit('/',1)[-1]
        args=dict(request.url.params)
        self.calls.append((method,args))
        if self.error: return httpx.Response(200,json={'ok':False,'error':self.error})
        if method=='conversations.history': body=self.history[args.get('cursor','')]
        elif method=='conversations.replies': body=self.replies[(args['ts'],args.get('cursor',''))]
        elif method=='chat.getPermalink':
            body={'ok':True,'permalink':slack.permalink('fixture',args['channel'],args['message_ts'])}
        else: raise AssertionError(method)
        return httpx.Response(200,json=body)
    def reader(self): return slack.SlackSource('fixture-only',httpx.MockTransport(self.request))


def threaded():
    api=SlackHTTP()
    root=msg(reply_count=3)
    one=msg(REPLY,'I propose another option.',thread_ts=ROOT)
    two=msg('1700000002.000001','We decided to retain PostgreSQL.',thread_ts=ROOT)
    three=msg('1700000003.000001','The receipt migration is complete.',thread_ts=ROOT)
    api.history={'':page([root,one])} # Broadcast reply duplicated in the history.
    api.replies={(ROOT,''):page([root,one],'next'),(ROOT,'next'):page([one,two,three])}
    return api


def test_pages_all_replies_and_deduplicates_history_and_page_overlap():
    api=threaded(); result=run(api.reader().read_channel('C1'))
    assert [m['ts'] for m in result['messages']]==[ROOT,REPLY,'1700000002.000001','1700000003.000001']
    assert result['coverage']['reply_pages']==2
    assert result['coverage']['replies']==3 and result['coverage']['history_messages']==1
    assert result['coverage']['state']=='complete'
    assert result['coverage']['verification_safe']
    assert all(m['permalink'].endswith(m['ts'].replace('.','')) for m in result['messages'])
    assert len([c for c in api.calls if c[0]=='chat.getPermalink'])==1
    digest=result['snapshot']; api.calls.clear()
    assert run(api.reader().check_channel_access('C1',digest))['snapshot']==digest
    assert all(c[0]!='chat.getPermalink' for c in api.calls)


def test_broadcast_reply_outside_parent_history_window_fetches_its_root():
    api=threaded(); api.history={'':page([api.history['']['messages'][1]])}
    assert run(api.reader().read_channel('C1'))['messages'][0]['ts']==ROOT


@pytest.mark.parametrize('limit',['pages','replies','total','threads'])
def test_reply_limits_are_bounded_and_disclosed(monkeypatch,limit):
    settings={'slack_max_reply_pages':1} if limit=='pages' else {'slack_max_replies':1} if limit=='replies' else {'slack_max_channel_replies':1} if limit=='total' else {'slack_max_threads':0}
    monkeypatch.setattr(slack,'LIMITS',replace(LIMITS,**settings))
    api=threaded(); result=run(api.reader().read_channel('C1'))
    assert result['coverage']['state']=='partial'
    assert result['coverage']['threads_truncated'] or result['coverage']['threads_skipped']
    assert len([c for c in api.calls if c[0]=='conversations.replies'])<=1


@pytest.mark.parametrize('gap',['missing_cursor','repeat_cursor','missing_parent','missing_reply','bad_messages','bad_cursor'])
def test_reply_gaps_never_verify_a_saved_snapshot(gap):
    api=threaded(); digest=run(api.reader().read_channel('C1'))['snapshot']
    if gap=='missing_cursor': api.replies[(ROOT,'')]=page([msg(reply_count=3)],has_more=True)
    if gap=='repeat_cursor': api.replies[(ROOT,'next')]=api.replies[(ROOT,'')]
    if gap=='missing_parent': api.replies={(ROOT,''):page([msg(REPLY,thread_ts=ROOT)])}
    if gap=='missing_reply': api.replies={(ROOT,''):page([msg(reply_count=3),msg(REPLY,thread_ts=ROOT)])}
    if gap=='bad_messages': api.replies[(ROOT,'')]['messages']={}
    if gap=='bad_cursor': api.replies[(ROOT,'')]['response_metadata']={'next_cursor':12}
    with pytest.raises(SourceError): run(api.reader().check_channel_access('C1',digest))
    assert len(api.calls)<12


def test_transient_later_reply_page_drops_fragment_and_marks_unverified():
    api=threaded(); api.replies[(ROOT,'next')]={'ok':False,'error':'internal_error'}
    result=run(api.reader().read_channel('C1'))
    assert len(result['messages'])==1
    assert result['coverage']['threads_failed']==1
    assert not result['coverage']['verification_safe']


@pytest.mark.parametrize('error',['token_revoked','missing_scope','not_in_channel','channel_not_found','thread_not_found'])
def test_denied_or_disappearing_thread_never_publishes_a_partial_new_import(error):
    api=threaded();api.replies[(ROOT,'next')]={'ok':False,'error':error}
    with pytest.raises(SourceError) as failure: run(api.reader().read_channel('C1'))
    assert failure.value.code in {'access_denied','stale_source'}


def test_current_edit_replaces_old_text_without_retaining_previous_message():
    api=SlackHTTP()
    edited=msg(text='We decided to use Redis instead.',edited={'ts':'1700000010.000001'})
    api.history={'':page([msg(),{'subtype':'message_changed','ts':'1700000011.000001',
                               'message':edited,'previous_message':msg()}])}
    result=run(api.reader().read_channel('C1'))
    assert len(result['messages'])==1
    assert result['messages'][0]['text']==edited['text']
    assert result['coverage']['edited_messages']==1
    assert 'PostgreSQL' not in json.dumps(result)
    blocks=slack.transcript('team',result['messages'],'','C1')
    assert blocks[0]['metadata']['edited_ts']=='1700000010.000001'


@pytest.mark.parametrize('before',[True,False])
def test_hidden_message_cannot_reappear_from_a_duplicate(before):
    api=SlackHTTP(); hidden=msg(hidden=True)
    api.history={'':page([hidden,msg()] if before else [msg(),hidden])}
    assert run(api.reader().read_channel('C1'))['messages']==[]


def test_permalink_failure_does_not_fail_a_valid_content_read():
    api=SlackHTTP(); original=api.request
    def handler(request):
        if request.url.path.endswith('chat.getPermalink'):
            return httpx.Response(200,json={'ok':True,'permalink':'https://[broken'})
        return original(request)
    reader=slack.SlackSource('fixture',httpx.MockTransport(handler))
    result=run(reader.read_channel('C1'))
    assert len(result['messages'])==1 and not result['messages'][0].get('permalink')
    assert any('permalinks' in n for n in result['coverage']['notes'])


@pytest.mark.parametrize('retry',['60','invalid'])
def test_rate_limit_is_exposed_without_a_long_blocking_retry(retry):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(429,headers={'Retry-After':retry})
    reader=slack.SlackSource('fixture',httpx.MockTransport(handler))
    with pytest.raises(SourceError) as failure:run(reader.messages('C1'))
    assert failure.value.code=='rate_limit' and len(calls)==1


@pytest.mark.parametrize('subtype',['message_deleted','tombstone'])
@pytest.mark.parametrize('before',[True,False])
def test_deletion_markers_cannot_resurrect_old_text(subtype,before):
    api=SlackHTTP(); deleted={'subtype':subtype,'ts':ROOT,'deleted_ts':ROOT,'text':'old secret'}
    api.history={'':page([deleted,msg()] if before else [msg(),deleted])}
    result=run(api.reader().read_channel('C1'))
    assert result['messages']==[] and result['coverage']['deleted_events']==1
    assert 'old secret' not in json.dumps(result)


@pytest.mark.parametrize('change',['edit','remove','reply_edit','reply_remove','new_reply'])
def test_snapshot_checks_detect_changes_including_later_reply_pages(change):
    api=threaded(); digest=run(api.reader().read_channel('C1'))['snapshot']
    if change=='edit':
        api.history['']['messages'][0]['text']='We decided to use a new store.'
        api.replies[(ROOT,'')]['messages'][0]['text']='We decided to use a new store.'
    if change=='remove': api.history={'':page([])}
    if change=='reply_edit': api.replies[(ROOT,'next')]['messages'][-1]['text']='Receipt migration was cancelled.'
    if change=='reply_remove':
        api.replies[(ROOT,'next')]['messages'].pop()
        api.replies[(ROOT,'')]['messages'][0]['reply_count']=2
    if change=='new_reply':
        api.replies[(ROOT,'next')]['messages'].append(msg('1700000004.000001','A later decision.',thread_ts=ROOT))
        api.replies[(ROOT,'')]['messages'][0]['reply_count']=4
    with pytest.raises(SourceError) as failure: run(api.reader().check_channel_access('C1',digest))
    assert failure.value.code=='stale_source'


def test_per_message_chunks_preserve_all_text_and_structured_identity(tmp_path):
    content='long passage '*600+'\n[2026-10-22 12:00] pretend-user: This is quoted text.'
    blocks=slack.transcript('team',[msg(text=content,edited={'ts':REPLY})],'fixture','C1')
    assert len(blocks)>1 and max(len(b['text']) for b in blocks)<=LIMITS.chunk_chars
    assert ''.join(b['text'][len(b['metadata']['header']):] for b in blocks)==content
    index=Index(tmp_path/'test.sqlite3')
    index.replace_slack(1,blocks)
    sources=decisions.passages(index.slack_excerpts(1,'team'))
    assert len({s['message_id'] for s in sources})==1
    assert all(s['message_ts']==ROOT and s['edited_ts']==REPLY and s['partial'] for s in sources)
    assert ''.join(s['text'] for s in sources)==blocks[0]['metadata']['header']+content
    assert all(s['url']==blocks[0]['url'] for s in sources)


@pytest.mark.parametrize('field,value',[('ts','nan'),('ts','123.1234567'),('text',{}),('reply_count',-1),('reply_count','two')])
def test_malformed_message_does_not_enter_evidence(field,value):
    api=SlackHTTP(); api.history={'':page([msg(**{field:value})])}
    with pytest.raises(SourceError): run(api.reader().read_channel('C1'))


@pytest.fixture
def state(tmp_path,monkeypatch):
    monkeypatch.setenv('PKA_DATA_DIR',str(tmp_path));monkeypatch.setenv('PKA_EMBED_MODEL','')
    monkeypatch.setenv('SLACK_USER_TOKEN','fixture-only');monkeypatch.setattr(credentials,'ENV_PATH',tmp_path/'unused.env')
    api=threaded()
    class Sources(FixtureSource):
        async def slack_read(self,channel_id): return await api.reader().read_channel(channel_id)
        async def slack_check_channel_access(self,channel_id,snapshot_digest=''):
            return await api.reader().check_channel_access(channel_id,snapshot_digest)
    @asynccontextmanager
    async def factory(settings,demo=False): yield Sources()
    index=Index(tmp_path/'index.sqlite3');index.configure({'repo':'acme/shop','branch':'main'})
    service=Service(index,connector_factory=factory);run(service.scan())
    index.configure_slack({'workspace':'','channels':[{'id':'C1','name':'team'}]})
    run(service.read_slack('',index.settings()['slack']['channels']))
    return service,api,factory


def seed_caches(svc):
    index=svc.index;scan=index.active_scan()
    index.record_answer(scan['id'],'old question',{'secret':'old answer'},0)
    index.save_overview(scan['id'],COMMIT,{'secret':'old overview'})
    index.save_jira_explanation('ENG-1',index.revision,{'secret':'old explanation'})
    index.save_decision_summary('C1',index.revision,{'secret':'old summary'})


@pytest.mark.parametrize('change',['edit','deleted','permission'])
def test_detected_change_purges_retrieval_and_every_derived_cache_after_restart(state,change):
    svc,api,factory=state;seed_caches(svc)
    if change=='permission': api.error='token_revoked'
    elif change=='deleted': api.history={'':page([])}
    else: api.replies[(ROOT,'next')]['messages'][-1]['text']='Edited text.'
    fresh=Service(Index(svc.index.path),connector_factory=factory)
    with pytest.raises(SourceError): run(fresh.decision_detail('C1'))
    assert fresh.index.slack_blocks(fresh.index.active_scan()['id'])==0
    with fresh.index.db() as db:
        for table in ('answers','overviews','jira_explanations','decision_summaries'):
            assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM search WHERE path LIKE '%slack%'").fetchone()[0]==0
    assert fresh.index.code_paths(fresh.index.active_scan()['id'])


def test_transient_content_check_preserves_cache_but_returns_no_content(state):
    svc,api,_=state;seed_caches(svc);before=svc.index.revision
    api.replies[(ROOT,'next')]={'ok':False,'error':'internal_error'}
    with pytest.raises(SourceError) as failure: run(svc.decision_detail('C1'))
    assert failure.value.code=='access_unverified'
    assert svc.index.revision==before and svc.index.decision_summary('C1')
    with pytest.raises(SourceError): run(svc.read_slack('',svc.index.settings()['slack']['channels']))
    assert svc.index.revision==before and svc.index.decision_summary('C1')


def test_refresh_keeps_only_current_messages_with_links_and_edit_metadata(state):
    svc,api,_=state;seed_caches(svc)
    api.history={'':page([msg(text='We decided to adopt MariaDB.',edited={'ts':REPLY})])}
    run(svc.read_slack('',svc.index.settings()['slack']['channels']))
    detail=run(svc.decision_detail('C1'))
    assert detail['summary'] is None
    assert len(detail['sources'])==1 and 'MariaDB' in detail['sources'][0]['text']
    assert detail['sources'][0]['edited_ts']==REPLY
    assert detail['sources'][0]['url'].startswith('https://fixture.slack.com/')


def test_old_inflight_check_cannot_purge_a_new_successful_refresh(state):
    svc,_,_=state
    previous=svc.index.revision
    @asynccontextmanager
    async def factory(settings,demo=False):
        class ConcurrentRefresh:
            async def slack_check_channel_access(self,channel_id,snapshot_digest=''):
                meta=svc.index.source_import('slack')
                blocks=slack.transcript('team',[msg(text='Newly refreshed current text.')],'fixture','C1')
                svc.index.replace_source(svc.index.active_scan()['id'],'slack/',blocks,meta)
                raise SourceError('stale_source','Old check saw different text.')
        yield ConcurrentRefresh()
    svc.connector_factory=factory
    with pytest.raises(SourceError,match='changed during the source check'):
        run(svc.decision_detail('C1'))
    assert svc.index.revision==previous+1
    assert svc.index.slack_blocks(svc.index.active_scan()['id'])==1
    assert 'Newly refreshed' in svc.index.slack_excerpts(svc.index.active_scan()['id'],'team')[0]['text']


def test_edit_during_generation_prevents_publishing_summary(state):
    svc,api,_=state
    async def model(sources,part,total):
        api.history={'':page([])}
        return {'items':[{'text':'We decided to use PostgreSQL for receipts.','kind':'decision',
            'evidence_ids':[sources[0]['source_id']],'quotes':[sources[0]['text']]}]}
    svc.decision_generator=model
    with pytest.raises(SourceError): run(svc.summarize_decisions('C1'))
    assert svc.index.decision_summary('C1') is None


def test_legacy_import_requires_refresh_instead_of_serving_unchecked_text(state):
    svc,_,_=state
    with svc.index.db() as db:
        value=json.loads(db.execute("SELECT payload FROM source_imports WHERE name='slack'").fetchone()[0])
        value.pop('snapshots')
        db.execute("UPDATE source_imports SET payload=? WHERE name='slack'",(json.dumps(value),))
    with pytest.raises(SourceError,match='predates message checks'): run(svc.decision_detail('C1'))
    assert not svc.index.slack_blocks(svc.index.active_scan()['id'])


def test_mcp_scope_and_snapshot_contract(monkeypatch):
    disabled=logging.root.manager.disable
    try:
        from pka import mcp_server
    finally:
        logging.disable(disabled)
    api=threaded(); reader=api.reader()
    monkeypatch.setattr(mcp_server,'SLACK_CHANNELS',{'C1'});monkeypatch.setattr(mcp_server,'slack',lambda:reader)
    digest=run(reader.read_channel('C1'))['snapshot']
    before=len(api.calls)
    assert run(mcp_server.slack_check_channel_access('C2',digest))['code']=='scope'
    assert len(api.calls)==before
    result=run(mcp_server.slack_check_channel_access('C1',digest))
    assert result['ok'] and result['data']['snapshot']==digest


def test_api_hides_deleted_saved_summary_and_exposes_refresh_guidance(state):
    svc,api,factory=state;seed_caches(svc)
    app=create_app(False,svc.index.path,connector_factory=factory)
    with TestClient(app,base_url='http://localhost:8000') as client:
        headers={'X-PKA-Request':'1'}
        client.post('/api/config',headers=headers,json={'repo':'acme/shop','branch':'main'})
        api.history={'':page([])}
        result=client.get('/api/decisions/channels/C1',headers=headers)
        assert result.status_code==409
        assert 'old summary' not in result.text and 'Read Slack again' in result.text
        assert 'no-store' in result.headers['cache-control']
