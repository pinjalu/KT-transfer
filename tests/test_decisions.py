from auth_helpers import auth_cookies
import asyncio
from contextlib import asynccontextmanager
import json

import httpx
import pytest

from pka import credentials, decisions
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource
from pka.index import Index
from pka.service import Service
from pka.web import create_app


def run(coro): return asyncio.run(coro)


def row(text, rid=1):
    return {'id':rid,'path':'slack/team','start':rid,'end':rid,'text':text,
            'url':'https://acme.slack.com/archives/C1/p1700000000000000'}


def passage(text, **extra):
    return {**decisions.passages([row('[2026-10-22 10:00] U1: '+text)])[0], **extra}


def answer(sources):
    return {'items':[{'text':decisions.body(s), 'kind':decisions.recorded_kind(s),
                      'evidence_ids':[s['source_id']], 'quotes':[s['text'][:500]]} for s in sources[:8]]}


@pytest.mark.parametrize('text,kind', [
    ('We decided to use PostgreSQL for storage.','decision'),
    ('Decision: Use PostgreSQL for storage.','decision'),
    ('**Decision:** Use PostgreSQL for storage.','decision'),
    ('Agreed: Use Redis for the cache.','decision'),
    ('We decided not to use MongoDB.','decision'),
    ('I propose Redis for the cache.','proposal'),
    ('We should use Redis for the cache.','proposal'),
    ('Previously we decided to use Redis.','historical'),
    ('We decided to use Redis, but this was superseded.','historical'),
    ('We have not decided to use Redis.','unclear'),
    ("We haven't yet agreed on Redis.",'unclear'),
    ('Decision: No approval has been given.','unclear'),
    ('If we decided to use Redis, would it work?','unclear'),
    ('We decided to use Redis if the benchmark passes.','unclear'),
    ('We decided to use Redis?','unclear'),
    ('Agreed.','unclear'),
    ('Agreed, thanks everyone.','unclear'),
    ('The runtime imports redis.','unclear'),
])
def test_recorded_status_is_derived_conservatively_from_full_message(text,kind):
    assert decisions.recorded_kind(passage(text))==kind


def test_passages_keep_all_messages_headers_multiline_text_and_mark_long_messages():
    text='[2026-10-22 10:00] U1: We decided to use Redis.\nDetails remain here.\n    reply [2026-10-22 10:01] U2: I propose Memcached.'
    sources=decisions.passages([row(text)])
    assert ''.join(s['text'] for s in sources)==text and len(sources)==2
    assert 'U1' in sources[0]['text'] and 'U2' in sources[1]['text']
    long='[2026-10-22 10:00] U1: '+('x'*13000)+' trailing condition'
    sources=decisions.passages([row(long)])
    groups=decisions.batches(sources)
    assert ''.join(s['text'] for group in groups for s in group)==long
    assert all(sum(len(s['text']) for s in g)<=decisions.CONTEXT_CHARS for g in groups)
    assert all(s['partial'] and decisions.recorded_kind(s)=='unclear' for s in sources)
    assert len({s['message_id'] for s in sources})==1


@pytest.mark.parametrize('url', ['javascript:alert(1)','https://evil.test/message','https://[broken',None])
def test_unsafe_or_missing_links_are_not_presented_as_slack_permalinks(url):
    assert decisions.passages([{**row('text'),'url':url}])[0]['url']==''


@pytest.mark.parametrize('fault', ['unknown','empty','missing','extra','kind'])
def test_bad_schema_and_foreign_evidence_are_rejected(fault):
    sources=[passage('We decided to use Redis.')]; raw=answer(sources)
    if fault=='unknown':raw['items'][0]['evidence_ids']=['S999']
    elif fault=='empty':raw['items'][0]['text']='   '
    elif fault=='missing':raw['items'][0]['evidence_ids']=[]
    elif fault=='extra':raw['items'][0]['invented']='actor'
    else:raw['items'][0]['kind']='agreed'
    with pytest.raises(SourceError):decisions.checked_points(raw,sources)


def test_unsupported_agreement_is_downgraded_and_false_paraphrase_replaced():
    source=passage('I propose qwen3:1.7b for local chat.')
    raw={'items':[{'text':'The team agreed on another model.','kind':'decision','evidence_ids':['S1'], 'quotes':[source['text'][:500]]}]}
    point=decisions.checked_points(raw,[source])[0]
    assert point['kind']=='proposal' and point['text']==decisions.body(source) and point['source_wording']


def test_named_values_are_preserved_without_invented_author_or_timestamp_fields():
    source=passage('We decided to use qwen3:1.7b with a 30 second timeout.')
    raw=answer([source]);raw['items'][0]['text']='Use the local model.'
    point=decisions.checked_points(raw,[source])[0]
    assert 'qwen3:1.7b' in point['text'] and '30' in point['text']
    assert 'author' not in point and 'timestamp' not in point


@pytest.mark.parametrize('quotes', [[], ['Made up source wording.'], ['   '], ['Use Redis.','Extra quote']])
def test_supporting_quotes_must_match_their_cited_passages(quotes):
    source=passage('We decided to use Redis.');raw=answer([source]);raw['items'][0]['quotes']=quotes
    with pytest.raises(SourceError):decisions.checked_points(raw,[source])


def test_a_summary_need_not_repeat_unrelated_values_elsewhere_in_long_passage():
    source=passage('The team is recovering missing tournaments.\nUnrelated models: qwen3:1.7b, llama3.2.',partial=True)
    raw={'items':[{'text':'Missing tournaments are being recovered.','kind':'unclear','evidence_ids':['S1'],
                   'quotes':['The team is recovering missing tournaments.']}]}
    point=decisions.checked_points(raw,[source])[0]
    assert point['text']=='Missing tournaments are being recovered.' and not point['source_wording']
    assert point['quotes'][0]['source_id']=='S1'


def test_greeting_only_points_are_omitted_without_hiding_original_evidence():
    source=passage('Hello')
    assert decisions.greeting(source) and decisions.checked_points(answer([source]),[source])==[]
    assert source['text'].endswith('Hello')


def test_possible_conflict_requires_two_distinct_complete_messages_and_keeps_both():
    one=passage('We decided to use Redis.')
    two=passage('We decided not to use Redis.',source_id='S2',message_id='2:0')
    raw={'items':[{'text':'These statements disagree on Redis.','kind':'conflict','evidence_ids':['S1','S2'], 'quotes':[one['text'],two['text']]}]}
    assert decisions.checked_points(raw,[one,two])[0]['kind']=='conflict'
    same={'items':[{**raw['items'][0], 'quotes':[one['text'],one['text']]}]}
    assert decisions.checked_points(same,[one,{**two,'text':one['text']}])[0]['kind']!='conflict'
    assert decisions.checked_points(raw,[one,{**two,'message_id':one['message_id']}])[0]['kind']!='conflict'
    assert decisions.checked_points(raw,[one,{**two,'partial':True}])[0]['kind']=='unclear'


class Source(FixtureSource):
    denied=None
    def __init__(self):self.checks=[];self.changed=False
    async def slack_messages(self,channel_id):
        content=('We decided to use PostgreSQL for receipts.' if channel_id=='C1' else 'I propose a billing audit.')
        return [{'ts':'1700000000.000000','user':'U1','text':'Different message.' if self.changed else content}]
    async def slack_check_channel_access(self,channel_id,snapshot_digest=''):
        self.checks.append(channel_id)
        if self.denied:raise self.denied
        return {'readable':True,'channel':channel_id,'snapshot':snapshot_digest}
    async def jira_check_issues_access(self,*args,**kwargs):raise AssertionError('Slack summaries must not need Jira')


@pytest.fixture
def state(tmp_path,monkeypatch):
    monkeypatch.setenv('PKA_DATA_DIR',str(tmp_path));monkeypatch.setenv('PKA_EMBED_MODEL','')
    monkeypatch.setenv('SLACK_USER_TOKEN','fixture-only');monkeypatch.setattr(credentials,'ENV_PATH',tmp_path/'unused.env')
    source=Source()
    @asynccontextmanager
    async def factory(settings,demo=False):yield source
    index=Index(tmp_path/'index.sqlite3');index.configure({'repo':'acme/shop','branch':'main'})
    svc=Service(index,connector_factory=factory);run(svc.scan())
    index.configure_slack({'workspace':'acme','channels':[{'id':'C1','name':'team'},{'id':'C2','name':'billing'}]})
    run(svc.read_slack('acme',index.settings()['slack']['channels']))
    async def model(sources,part,total):return answer(sources)
    svc.decision_generator=model
    return svc,source,factory


def test_channel_summary_uses_only_selected_channel_and_persists_across_restart(state):
    svc,source,factory=state
    async def model(sources,part,total):
        assert all(s['path']=='slack/team' for s in sources)
        assert 'billing' not in json.dumps(sources)
        return answer(sources)
    svc.decision_generator=model
    result=run(svc.summarize_decisions('C1'))
    assert result['items'][0]['kind']=='decision' and result['passages_read']==1
    assert sorted(source.checks)==['C1','C1','C2','C2']
    other=Service(Index(svc.index.path),connector_factory=factory)
    assert run(other.decision_detail('C1'))['summary']==result
    assert run(other.decision_detail('C2'))['summary'] is None
    assert len(run(other.decision_channel_list())['channels'])==2


@pytest.mark.parametrize('action',['refresh','project','channels','credentials','revoke','invalidate'])
def test_changed_sources_and_access_invalidate_saved_summary(state,monkeypatch,action):
    svc,source,_=state;run(svc.summarize_decisions('C1'))
    if action=='refresh':run(svc.read_slack('acme',svc.index.settings()['slack']['channels']))
    elif action=='project':svc.index.configure({'repo':'acme/other','branch':'main'})
    elif action=='channels':svc.index.configure_slack({'workspace':'acme','channels':[]})
    elif action=='credentials':monkeypatch.setenv('SLACK_USER_TOKEN','changed');svc.sync_source_credentials()
    elif action=='invalidate':svc.index.invalidate()
    else:
        source.denied=SourceError('access_denied','Revoked')
        with pytest.raises(SourceError):run(svc.decision_detail('C1'))
    assert svc.index.decision_summary('C1') is None


@pytest.mark.parametrize('fault',['refresh','credentials','revoke'])
def test_inflight_source_changes_prevent_publication(state,monkeypatch,fault):
    svc,source,_=state
    async def model(sources,part,total):
        if fault=='refresh':svc.index.discard_source('slack')
        elif fault=='credentials':monkeypatch.setenv('SLACK_USER_TOKEN','changed')
        else:source.denied=SourceError('access_denied','Revoked')
        return answer(sources)
    svc.decision_generator=model
    with pytest.raises(SourceError):run(svc.summarize_decisions('C1'))
    assert svc.index.decision_summary('C1') is None


def test_transient_failure_withholds_content_and_failed_generation_keeps_prior_result(state):
    svc,source,_=state;saved=run(svc.summarize_decisions('C1'))
    source.denied=SourceError('network','Unavailable')
    with pytest.raises(SourceError):run(svc.decision_detail('C1'))
    assert svc.index.decision_summary('C1')==saved
    source.denied=None
    async def model(*args):raise SourceError('ollama','Unavailable')
    svc.decision_generator=model
    async def scenario():
        svc.start_job('decisions',target='C1');await svc.task
        assert svc.job_status()['state']=='failed' and svc.job_status()['can_retry']
    run(scenario())
    assert svc.index.decision_summary('C1')==saved


def test_cancel_retry_and_restart_preserve_target_and_never_publish_cancelled_result(state):
    svc,_,factory=state
    async def scenario():
        entered,release=asyncio.Event(),asyncio.Event()
        async def model(sources,part,total):
            entered.set();await release.wait();return answer(sources)
        svc.decision_generator=model
        job=svc.start_job('decisions',target='C2');await entered.wait()
        svc.cancel_job(job);release.set();await svc.task
        assert svc.job_status()['state']=='cancelled' and svc.index.decision_summary('C2') is None
        svc.start_job('decisions',retry_id=job);await svc.task
        assert svc.job_status()['state']=='succeeded' and svc.job['target']=='C2'
        assert svc.index.decision_summary('C1') is None
    run(scenario())
    svc._new_job('decisions',target='C1');svc.index.recover()
    reopened=Service(Index(svc.index.path),connector_factory=factory)
    assert reopened.job_status()['state']=='interrupted' and reopened.job_status()['can_retry']
    run(reopened.read_slack('acme',reopened.index.settings()['slack']['channels']))
    assert not reopened.job_status()['can_retry']


def test_all_parts_contribute_and_duplicate_points_merge_evidence(state):
    svc,source,_=state
    async def messages(channel_id):
        return [{'ts':f'170000000{i}.000000','user':'U1','text':'We decided to use Redis.\n'+('details '*700)} for i in range(3)]
    source.slack_messages=messages;run(svc.read_slack('acme',svc.index.settings()['slack']['channels']))
    seen=[]
    async def model(sources,part,total):
        seen.extend(sources)
        return {'items':[{'text':'We decided to use Redis.','kind':'decision','evidence_ids':[sources[0]['source_id']], 'quotes':['We decided to use Redis.']}]}
    svc.decision_generator=model
    result=run(svc.summarize_decisions('C1'))
    assert result['parts']==3 and result['passages_read']==3 and len(seen)==3
    assert len(result['items'])==1 and len(result['items'][0]['source_ids'])==3


def test_atomic_save_rejects_changed_revision(state):
    svc,_,_=state;revision=svc.index.revision;svc.index.discard_source('slack')
    with pytest.raises(ValueError):svc.index.save_decision_summary('C1',revision,{'items':[]})


def test_api_validates_scope_and_runs_one_background_job_without_auto_generation(state):
    original,_,factory=state;app=create_app(False,original.index.path,connector_factory=factory);svc=app.state.service
    async def scenario():
        entered,release=asyncio.Event(),asyncio.Event()
        async def model(sources,part,total):entered.set();await release.wait();return answer(sources)
        svc.decision_generator=model
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), cookies=auth_cookies(app),base_url='http://localhost:8000',headers={'X-PKA-Request':'1'}) as client:
            assert (await client.get('/api/decisions/channels')).json()['channels']==[]
            assert (await client.get('/api/decisions/channels/C1')).status_code==409
            await client.post('/api/config',json={'repo':'acme/shop','branch':'main'})
            response=await client.get('/api/decisions/channels/C1')
            assert response.json()['summary'] is None and 'no-store' in response.headers['cache-control']
            assert not entered.is_set()
            assert (await client.post('/api/decisions/channels/C999/summarize')).status_code==409
            started=await client.post('/api/decisions/channels/C1/summarize');await entered.wait()
            assert (await client.post('/api/decisions/channels/C2/summarize')).status_code==409
            assert (await client.get('/decisions')).status_code==200
            assert (await client.get('/api/status')).json()['job']['id']==started.json()['job_id']
            release.set();await svc.task
            assert (await client.get('/api/decisions/channels/C1')).json()['summary']['items']
            assert (await client.get('/api/decisions/channels/C2')).json()['summary'] is None
    run(scenario())


def test_model_schema_restricts_evidence_and_treats_source_as_untrusted(monkeypatch):
    captured=[];sources=[passage('I propose Redis.')]
    async def request(payload,started):
        captured.append(payload);return httpx.Response(200,json={'message':{'content':json.dumps(answer(sources))}})
    monkeypatch.setattr('pka.service._ask_ollama',request)
    run(decisions.generate(sources,2,3));payload=captured[0]
    assert payload['format']['$defs']['Point']['properties']['evidence_ids']['items']['enum']==['S1']
    assert 'untrusted DATA' in payload['messages'][0]['content']
    assert json.loads(payload['messages'][1]['content'])['total_parts']==3
