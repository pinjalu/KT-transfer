"""Synthetic-only provider, quota, privacy, persistence and API regression checks."""
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import replace
import httpx
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from auth_helpers import OwnerClient
from pka import credentials
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource
from pka.index import Index
from pka.llm.config import Limits, Routing, Target, FEATURES
from pka.llm.router import Router, secret
from pka.llm.store import Store
from pka.llm.types import ProviderError, Reply, Request
from pka.llm.http import delay, http_error
from pka.llm.gemini import Gemini
from pka.llm.groq import Groq, strict_schema
from pka.service import Service
from pka.web import create_app

class Shape(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer: str

def validate(raw): return Shape.model_validate(raw).model_dump()
async def guard(): pass
async def public(repo): return True

class Adapter:
    def __init__(self, result=None): self.calls=[]; self.result=result or Reply('{"answer":"synthetic"}',20,10)
    async def generate(self, request, target, key, timeout):
        self.calls.append((target,key,timeout))
        if isinstance(self.result,Exception): raise self.result
        if callable(self.result): return await self.result()
        return self.result

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr('pka.llm.router.catalog_current',lambda:True)
    index=Index(tmp_path/'index.sqlite3'); index.configure({'repo':'sample/public','branch':'main'})
    adapters={p:Adapter() for p in ('gemini','groq','ollama')}
    router=Router(index,adapters=adapters,key_reader=lambda p:'fixture-key-'+p,public_check=public)
    return router,adapters,Request([{'role':'user','content':'Synthetic question'}],Shape.model_json_schema(),[{'path':'app.py'}],100)

def enable(router):
    config=router.store.config()
    for p in config.providers:
        config.providers[p].enabled=True
        router.store.confirm(p,router.key_reader(p),True)
    router.store.save_config(config.model_dump()); router.store.permit('sample/public',['groq','gemini'])

def generate(router,request,feature='ask',**kwargs):
    return asyncio.run(router.generate(request,validate,feature,guard,**kwargs))

def test_model_token_count_admits_valid_groq_request_without_changing_sources(setup):
    from copy import deepcopy
    router,adapters,request=setup;enable(router)
    request.messages=[{'role':'user','content':'synthetic source '*1500}]
    request.max_output_tokens=2000
    original=deepcopy(request)
    result=generate(router,request)
    assert result.generation['provider']=='groq'
    assert result.generation['estimation_method']=='o200k_with_margin'
    assert result.generation['estimated_reserved_tokens']<=8000
    assert request==original and adapters['groq'].calls[0][0].model=='openai/gpt-oss-120b'
    config=router.store.config();config.providers['groq'].limits.tpm=500
    config.providers['gemini'].enabled=False;config.local_enabled=False
    router.store.save_config(config.model_dump())
    with pytest.raises(SourceError) as error: generate(router,request)
    assert error.value.generation['attempts'][0]['error']=='provider_limit'
    assert len(adapters['groq'].calls)==1


def test_default_is_local_and_never_checks_cloud(setup):
    router,adapters,request=setup
    async def forbidden(repo): pytest.fail('Disabled cloud must not perform network checks')
    router.public_check=forbidden
    result=generate(router,request)
    assert result.generation['provider']=='ollama'
    assert not adapters['groq'].calls and not adapters['gemini'].calls
    assert dict(result)=={'answer':'synthetic'} and 'generation' not in result

@pytest.mark.parametrize('feature,primary',[('overview','gemini'),('ask','groq'),('jira','groq'),('business_logic','gemini'),('tests','groq'),('slack','gemini')])
def test_function_routes_actual_metadata(setup,feature,primary):
    router,adapters,request=setup; enable(router)
    value=generate(router,request,feature)
    assert value.generation['provider']==primary and value.generation['function']==feature
    assert value.generation['input_tokens']==20 and value.generation['usage_source']=='provider'
    assert len(adapters[primary].calls)==1

@pytest.mark.parametrize('failure',[ProviderError('quota',status=429,retry_after=90),ProviderError('temporary',status=503,retry_after=10),ProviderError('timeout',retry_after=10),Reply('not json',1,2),Reply('{"wrong":"shape"}',1,2),RuntimeError('secret provider error')])
def test_fallback_errors_are_bounded_and_sanitized(setup,failure):
    router,adapters,request=setup; enable(router); adapters['groq'].result=failure
    result=generate(router,request)
    assert result.generation['provider']=='gemini'
    assert len(adapters['groq'].calls)==len(adapters['gemini'].calls)==1
    serialized=json.dumps(router.ledger.dashboard(router.workspace))
    assert 'secret provider error' not in serialized and 'fixture-key' not in serialized and 'Synthetic question' not in serialized
    if isinstance(failure,ProviderError) and failure.retry_after:
        generate(router,request)
        assert len(adapters['groq'].calls)==1

def test_invalid_evidence_falls_back_without_claiming_verification(setup):
    router,adapters,request=setup; enable(router)
    adapters['groq'].result=Reply('{"answer":"unsupported"}')
    def evidence(raw):
        if raw.get('answer')=='unsupported': raise SourceError('citations','Unknown source')
        return validate(raw)
    result=asyncio.run(router.generate(request,evidence,'ask',guard))
    assert result.generation['provider']=='gemini' and result.generation['attempts'][0]['error']=='invalid_response'
    assert 'verified' not in result

@pytest.mark.parametrize('reason',['not_approved','private_repo','jira','slack','local','history','expired_confirmation','rotated_key','expired_catalog','missing_key'])
def test_privacy_and_free_gates_before_cloud_egress(setup,monkeypatch,reason):
    router,adapters,request=setup; enable(router)
    if reason=='not_approved': router.store.permit('sample/public',[])
    if reason=='private_repo':
        async def private(repo): return False
        router.public_check=private
    if reason in ('jira','slack','local'): request.sources=[{'path':{'jira':'jira/KEY-1','slack':'slack/C1','local':'local://folder/app.py'}[reason]}]
    if reason=='history': request.has_history=True
    if reason=='expired_confirmation':
        with router.store.db() as db: db.execute('UPDATE ai_confirmations SET checked=?',(time.time()-8*86400,))
    if reason=='rotated_key': router.key_reader=lambda p:'another-key'
    if reason=='missing_key': router.key_reader=lambda p:''
    if reason=='expired_catalog': monkeypatch.setattr('pka.llm.router.catalog_current',lambda:False)
    assert generate(router,request).generation['provider']=='ollama'
    assert not adapters['groq'].calls and not adapters['gemini'].calls

def test_manual_pinned_model_does_not_hide_failure(setup):
    router,adapters,request=setup; enable(router)
    config=router.store.config(); config.mode='manual'; config.manual=Target(provider='groq',model='openai/gpt-oss-20b')
    router.store.save_config(config.model_dump()); adapters['groq'].result=ProviderError('timeout')
    with pytest.raises(SourceError) as e: generate(router,request)
    assert e.value.code=='llm_unavailable' and e.value.generation['attempts'][0]['model']=='openai/gpt-oss-20b'
    assert not adapters['gemini'].calls and not adapters['ollama'].calls


def test_explicit_github_approval_supports_private_repository_with_access_checks(setup):
    router,adapters,request=setup; enable(router)
    router.store.permit('sample/public',['groq','gemini'],classification='github')
    checks=[]
    async def connected(repo): checks.append(repo); return True
    async def public_forbidden(repo): pytest.fail('Private approval must use authenticated access checks')
    router.repository_check=connected;router.public_check=public_forbidden
    assert generate(router,request).generation['provider']=='groq'
    assert checks==['sample/public']


@pytest.mark.parametrize('source,approved,cloud',[
    ('jira/K-1',['jira'],True),('slack/C1',['slack'],True),
    ('jira/K-1',['slack'],False),('slack/C1',['jira'],False),
    ('local:app.py',['jira','slack'],False),
])
def test_explicit_source_scopes_control_cloud_egress(setup,source,approved,cloud):
    router,adapters,request=setup;enable(router)
    router.store.permit('sample/public',['groq'],classification='github',source_types=['github',*approved])
    router.repository_check=public
    request.sources=[{'path':source}]
    result=generate(router,request)
    assert result.generation['provider']==('groq' if cloud else 'ollama')
    assert bool(adapters['groq'].calls)==cloud
    assert not adapters['gemini'].calls


def test_legacy_permissions_do_not_implicitly_approve_other_sources(setup):
    router,_,_=setup
    with router.store.db() as db:
        db.execute('INSERT INTO ai_permissions VALUES(?,?)',('sample/public',json.dumps({'providers':['groq'],'classification':'github'})))
    assert router.store.permission('sample/public')['source_types']==['github']
    assert router.store.permission('another/project')['source_types']==[]


def test_source_approval_cannot_bypass_access_and_revocation_withholds_output(setup):
    router,adapters,request=setup;enable(router)
    router.store.permit('sample/public',['groq','gemini'],source_types=['github','jira','slack'])
    request.sources=[{'path':'jira/K-1'},{'path':'slack/C1'}]
    async def denied(): raise SourceError('access_denied','Access revoked')
    with pytest.raises(SourceError,match='Access revoked'):
        asyncio.run(router.generate(request,validate,'ask',denied))
    assert not any(a.calls for a in adapters.values())
    async def revoke():
        router.store.permit('sample/public',['groq','gemini'])
        return Reply('{"answer":"must not publish"}',20,10)
    adapters['groq'].result=revoke
    with pytest.raises(SourceError,match='withheld'): generate(router,request)
    assert not adapters['gemini'].calls and not adapters['ollama'].calls
    assert router.ledger.dashboard(router.workspace)['recent'][0]['status']=='withheld'


@pytest.mark.parametrize('reason',['access_missing','access_denied','other_project','jira','slack','local','history'])
def test_private_github_approval_does_not_bypass_access_or_source_isolation(setup,reason):
    router,adapters,request=setup;enable(router)
    router.store.permit('sample/public',['groq','gemini'],classification='github')
    async def connected(repo): return reason!='access_denied'
    router.repository_check=None if reason=='access_missing' else connected
    if reason=='other_project': router.index.configure({'repo':'other/private','branch':'main'})
    if reason in ('jira','slack','local'): request.sources=[{'path':{'jira':'jira/K-1','slack':'slack/C','local':'local:app.py'}[reason]}]
    if reason=='history': request.has_history=True
    assert generate(router,request).generation['provider']=='ollama'
    assert not adapters['gemini'].calls and not adapters['groq'].calls

@pytest.mark.parametrize('change',['permission','config','access'])
def test_midflight_change_withholds_result_without_fallback(setup,change):
    router,adapters,request=setup; enable(router)
    async def mutate():
        if change=='permission': router.store.permit('sample/public',[])
        if change=='config':
            config=router.store.config(); config.local_enabled=False; router.store.save_config(config.model_dump())
        return Reply('{"answer":"should not publish"}',20,10)
    adapters['groq'].result=mutate
    calls=[]
    async def check():
        calls.append(1)
        if len(calls)==2 and change=='access': raise SourceError('access_denied','Permission revoked')
    with pytest.raises(SourceError): asyncio.run(router.generate(request,validate,'ask',check))
    assert not adapters['gemini'].calls and router.ledger.dashboard(router.workspace)['recent'][0]['status']=='withheld'

def test_shared_quota_atomic_and_persistent_across_models_and_workspaces(tmp_path):
    path=tmp_path/'ledger.sqlite3'; Store(path)
    cap=Limits(rpm=1,rpd=10,tpm=1000,tpd=2000)
    def reserve(n):
        return Store(path).reserve('workspace-'+str(n),'project','ask',Target(provider='groq',model='openai/gpt-oss-'+('20b' if n%2 else '120b')),200,cap,cap)
    with ThreadPoolExecutor(max_workers=6) as pool: results=list(pool.map(reserve,range(6)))
    assert sum(bool(identifier) for identifier,_ in results)==1
    assert all(error=='provider_limit' for identifier,error in results if not identifier)
    assert not reserve(7)[0]

def test_project_caps_cross_provider_and_unknown_usage_remains_reserved(tmp_path):
    store=Store(tmp_path/'ledger.sqlite3'); provider=Limits(rpm=10,rpd=10,tpm=10000,tpd=10000); project=Limits(rpm=10,rpd=10,tpm=500,tpd=1000)
    first,error=store.reserve('w','p','ask',Target(provider='groq',model='openai/gpt-oss-120b'),400,provider,project)
    store.finish(first,1,status='cancelled')
    second,error=store.reserve('another-member','p','ask',Target(provider='gemini',model='gemini-3.8-flash'),200,provider,project)
    assert second is None and error=='project_limit'
    assert store.dashboard('w')['last_24_hours'][0]['estimated_unreported_tokens']==400


def test_reported_exhaustion_prevents_next_request_even_before_local_cap(setup):
    router,adapters,request=setup; enable(router)
    adapters['groq'].result=Reply('{"answer":"ok"}',10,5,{'remaining-tokens':0,'reset-tokens-seconds':60})
    assert generate(router,request).generation['provider']=='groq'
    assert generate(router,request).generation['provider']=='gemini'
    assert len(adapters['groq'].calls)==1
    assert router.ledger.dashboard(router.workspace)['cooldowns'][0]['reason']=='reported_quota_exhausted'


def test_synthetic_benchmark_cannot_enable_disabled_providers(setup):
    from pka.llm.benchmark import run,CASES
    router,adapters,_=setup
    result=asyncio.run(run(router,[Target(provider='groq',model='openai/gpt-oss-120b')]))
    assert len(result['results'])==len(CASES)==6
    assert all(r['status']=='unavailable' and r['human_review'] is None for r in result['results'])
    assert not any(adapter.calls for adapter in adapters.values())


def test_quality_comparison_rejects_changed_sources_or_unpinned_runs():
    from copy import deepcopy
    from pka.quality import comparison
    report={'id':1,'dataset_hash':'a','repo':'x/y','commit':'c','scan_id':1,'knowledge_revision':0,
        'prompt_version':'v1','run_complete':True,'routing_config':{'mode':'manual','manual_fallback':False},
        'results':[{'case_id':'case','source_digest':'d'}],'summary':{'human_reviewed':0}}
    assert comparison(report,deepcopy(report))['comparable']
    changed=deepcopy(report); changed['results'][0]['source_digest']='changed'
    assert not comparison(report,changed)['comparable']
    changed=deepcopy(report); changed['routing_config']['manual_fallback']=True
    assert not comparison(report,changed)['comparable']
    changed=deepcopy(report); changed.pop('prompt_version')
    assert not comparison(report,changed)['comparable']

@pytest.mark.parametrize('provider,model',[('groq','paid-model'),('gemini','gemini-pro'),('ollama','qwen:cloud'),('ollama','https://somewhere')])
def test_paid_or_remote_models_rejected(provider,model):
    with pytest.raises(ValidationError): Target(provider=provider,model=model)

@pytest.mark.parametrize('value,expected',[('2m3s',123),('17',17),('1h',3600)])
def test_retry_after_formats(value,expected): assert delay(value)==expected

def test_quota_daily_and_structured_retry_info():
    assert http_error(429,{},b'{"error":{"message":"per day quota"}}').retry_after>=86400
    assert http_error(429,{},b'{"error":{"details":[{"retryDelay":"120s"}]}}').retry_after==120
    assert http_error(503,{'retry-after':'80'},b'secret').retry_after==80
    assert http_error(400,{},b'synthetic schema rejection').retry_after is None
    assert http_error(400,{'retry-after':'30'},b'synthetic schema rejection').retry_after==30

@pytest.mark.parametrize('provider',[Gemini,Groq])
def test_adapter_payload_fixed_origin_and_reported_usage(provider):
    sent=[]
    def handler(request):
        sent.append(request); payload=json.loads(request.content)
        assert 'fixture-key' not in str(request.url) and 'fixture-key' not in request.content.decode()
        if provider is Gemini:
            assert payload['generationConfig']['responseFormat']['text']['schema']==Shape.model_json_schema()
            assert request.headers['x-goog-api-key']=='fixture-key'
            return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"answer":"ok"}'}]}}],
                'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':5,'thoughtsTokenCount':2}})
        assert payload['response_format']['json_schema']['strict'] is True and payload['max_completion_tokens']==100
        assert request.headers['authorization']=='Bearer fixture-key'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"answer":"ok"}'}}],
            'usage':{'prompt_tokens':10,'completion_tokens':7}},headers={'x-ratelimit-remaining-requests':'999'})
    adapter=provider(httpx.MockTransport(handler)); p='gemini' if provider is Gemini else 'groq'
    target=Target(provider=p,model='gemini-3.8-flash' if p=='gemini' else 'openai/gpt-oss-120b')
    reply=asyncio.run(adapter.generate(Request([{'role':'user','content':'Synthetic'}],Shape.model_json_schema(),[],100),target,'fixture-key',5))
    assert reply.input_tokens==10 and reply.output_tokens==7 and len(sent)==1

def test_groq_focused_union_keeps_schema_constraints_and_unwraps():
    from copy import deepcopy
    from jsonschema import Draft202012Validator
    from pka.service import answer_schema
    sources=[{'source_id':'S1','path':'auth.py','start':1,'end':2,'text':'def login(): pass'}]
    request=Request([{'role':'user','content':'Which function logs in?'}],answer_schema('Which function logs in?',sources),sources)
    original=deepcopy(request)
    answer={'statements':[{'text':'login handles login.','source_ids':['S1']}],'missing_information':''}
    def handler(sent):
        payload=json.loads(sent.content);schema=payload['response_format']['json_schema']['schema']
        assert schema['type']=='object' and 'anyOf' not in schema
        assert 'anyOf' in schema['properties']['result']
        assert 'Statement' in schema['$defs'] and '$defs' not in schema['properties']['result']
        assert payload['messages'][0]['role']=='system'
        assert sum(message['role']=='system' for message in payload['messages'])==1
        validator=Draft202012Validator(schema)
        variants=schema['properties']['result']['anyOf']
        assert set(variants[0]['properties']).isdisjoint(variants[1]['properties'])
        validator.validate({'result':{'variant_1':answer}})
        validator.validate({'result':{'variant_2':{'statements':[],'missing_information':'Not in supplied sources.'}}})
        assert not validator.is_valid({'result':{'variant_1':{**answer,'missing_information':'Also missing'}}})
        assert not validator.is_valid({'result':{'variant_1':{'statements':[{'text':'wrong','source_ids':['S99']}],'missing_information':''}}})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'result':{'variant_1':answer}})}}]})
    reply=asyncio.run(Groq(httpx.MockTransport(handler)).generate(request,Target(provider='groq',model='openai/gpt-oss-120b'),'fixture-key',5))
    assert json.loads(reply.content)==answer and request==original


@pytest.mark.parametrize('body',[{}, {'result':'wrong'}, {'result':{},'unexpected':True},
    {'result':{'variant_1':{},'variant_2':{}}},{'result':{'variant_99':{}}},{'result':{'variant_1':'wrong'}}])
def test_groq_rejects_malformed_union_envelope(body):
    from pka.service import answer_schema
    adapter=Groq(httpx.MockTransport(lambda _:httpx.Response(200,json={
        'choices':[{'finish_reason':'stop','message':{'content':json.dumps(body)}}]})))
    with pytest.raises(ProviderError,match='invalid_response'):
        asyncio.run(adapter.generate(Request([],answer_schema('Which function?'),[]),
            Target(provider='groq',model='openai/gpt-oss-120b'),'fixture-key',5))


def test_groq_union_transport_keeps_local_citation_validation(setup):
    from pka.service import ollama_answer
    from pka.llm.router import using
    router,adapters,_=setup;enable(router)
    invalid={'statements':[{'text':'Unknown function.','source_ids':['S99']}],'missing_information':''}
    router.adapters['groq']=Groq(httpx.MockTransport(lambda _:httpx.Response(200,json={
        'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'result':{'variant_1':invalid}})}}]})))
    config=router.store.config();config.providers['gemini'].enabled=False;router.store.save_config(config.model_dump())
    adapters['ollama'].result=Reply(json.dumps({'statements':[{'text':'login handles login.','source_ids':['S1']}],'missing_information':''}),20,10)
    async def run():
        with using(router,'ask',guard):
            return await ollama_answer('Which function logs in?',[{'source_id':'S1','path':'auth.py','start':1,'end':2,'text':'def login(): pass'}])
    answer=asyncio.run(run())
    assert answer.generation['provider']=='ollama'
    assert answer.generation['attempts'][0]['error']=='invalid_response'
    assert answer['statements'][0]['source_ids']==['S1']


@pytest.mark.parametrize('status',[429,500,401,404,302])
def test_adapter_errors_never_include_upstream_content(status):
    adapter=Groq(httpx.MockTransport(lambda req:httpx.Response(status,text='SENSITIVE_KEY_AND_CONTENT',headers={'retry-after':'30'})))
    with pytest.raises(ProviderError) as e:
        asyncio.run(adapter.generate(Request([],{},[],100),Target(provider='groq',model='openai/gpt-oss-120b'),'test',5))
    assert 'SENSITIVE' not in str(e.value) and e.value.status==status

def test_local_alias_cloud_detection_happens_before_prompt(monkeypatch):
    from pka.llm.ollama import Ollama
    sent=[]; real=httpx.AsyncClient
    def handler(request):
        sent.append(str(request.url))
        assert request.url.path=='/api/show' and 'private code' not in request.content.decode()
        return httpx.Response(200,json={'remote_host':'https://ollama.com','remote_model':'model','model_info':{'x':1},'details':{'format':'gguf'}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(ProviderError,match='local_model_unverified'):
        asyncio.run(Ollama().generate(Request([{'role':'user','content':'private code'}],{},[]),Target(provider='ollama',model='harmless-alias')))
    assert len(sent)==1

class MemoryVault:
    def __init__(self): self.values={}
    def read(self): return dict(self.values)
    def save(self,values): self.values.update(values)

def test_keys_never_read_from_environment_or_saved_without_vault(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY','forbidden-env')
    with credentials.using(None):
        assert secret('groq')==''
        with pytest.raises(ValueError,match='secure'): credentials.save({'GROQ_API_KEY':'secret'})

def test_settings_api_disabled_default_private_and_secrets_redacted(tmp_path):
    vault=MemoryVault(); app=create_app(True,tmp_path/'api.sqlite3',credential_store=vault)
    with OwnerClient(app,base_url='http://localhost:8000',headers={'x-pka-request':'1'}) as client:
        info=client.get('/api/ai').json(); assert not any(p['enabled'] for p in info['config']['providers'].values())
        config=info['config']; config['providers']['groq']['enabled']=True
        assert client.post('/api/ai/config',json=config).status_code==409
        assert client.post('/api/ai/key',json={'provider':'groq','key':'secret-fixture'}).status_code==200
        assert 'secret-fixture' not in client.get('/api/ai').text
        assert client.post('/api/ai/key',json={'provider':'bad','key':{'secret':'not echoed'}}).status_code==422
        assert 'not echoed' not in client.post('/api/ai/key',json={'provider':'bad','key':'not echoed'}).text
        assert client.post('/api/ai/confirmation',json={'provider':'groq','free_plan_without_billing_or_credits':True}).status_code==200
        assert client.post('/api/ai/config',json=config).status_code==200
        async def private(repo): return False
        app.state.service.llm.public_check=private
        assert client.post('/api/ai/permission',json={'providers':['groq'],'approved_public_content':True}).status_code==409
        assert client.get('/api/ai').json()['permission']['providers']==[]
        assert client.post('/api/ai/key',json={'provider':'groq','key':'rotation'}).status_code==200
        assert not client.get('/api/ai').json()['config']['providers']['groq']['enabled']
        assert 'secret-fixture' not in app.state.auth.path.read_bytes().decode('latin1')


def test_private_github_consent_requires_current_access_and_rechecks_selection(tmp_path):
    app=create_app(True,tmp_path/'approval.sqlite3',credential_store=MemoryVault())
    service=app.state.service; router=service.llm
    async def connected(repo): return True
    async def denied(repo): return False
    with OwnerClient(app,base_url='http://localhost:8000',headers={'x-pka-request':'1'}) as client:
        payload={'providers':['groq'],'approved_github_content':True}
        router.repository_check=denied
        assert client.post('/api/ai/permission',json=payload).status_code==409
        router.repository_check=connected
        assert client.post('/api/ai/permission',json={'providers':['groq']}).status_code==409
        reply=client.post('/api/ai/permission',json=payload)
        assert reply.status_code==200 and reply.json()['classification']=='github'
        assert reply.json()['providers']==['groq']
        async def changed(repo):
            service.index.configure({'repo':'another/repo','branch':'main'})
            return True
        router.repository_check=changed
        assert client.post('/api/ai/permission',json=payload).status_code==409
        assert router.store.permission('another/repo')['providers']==[]
        assert client.post('/api/ai/permission',json={'providers':[]}).status_code==200

def test_source_scope_api_checks_access_and_project_before_saving(tmp_path,monkeypatch):
    app=create_app(True,tmp_path/'scopes.sqlite3',credential_store=MemoryVault())
    service=app.state.service;router=service.llm;checks=[]
    router.repository_check=public
    monkeypatch.setattr(service.index,'active_scan',lambda:{'id':1})
    async def check(scan,names): checks.append(names)
    monkeypatch.setattr(service,'check_external_access',check)
    payload={'providers':['groq','gemini'],'approved_github_content':True,
             'approved_jira_content':True,'approved_slack_content':True}
    with OwnerClient(app,base_url='http://localhost:8000',headers={'x-pka-request':'1'}) as client:
        reply=client.post('/api/ai/permission',json=payload)
        assert reply.status_code==200 and reply.json()['source_types']==['github','jira','slack']
        assert checks==[('jira','slack')]
        async def changed(scan,names): service.index.configure({'repo':'other/repo','branch':'main'})
        monkeypatch.setattr(service,'check_external_access',changed)
        assert client.post('/api/ai/permission',json=payload).status_code==409
        assert router.store.permission('other/repo')['providers']==[]
        async def denied(scan,names): raise SourceError('access_denied','Access revoked')
        monkeypatch.setattr(service,'check_external_access',denied)
        assert client.post('/api/ai/permission',json=payload).status_code!=200
        assert router.store.permission('other/repo')['source_types']==[]
        reply=client.post('/api/ai/permission',json={'providers':[]})
        assert reply.status_code==200 and reply.json()['source_types']==[]


def test_all_failure_retains_sources_and_saved_answer_compatibility(tmp_path):
    @asynccontextmanager
    async def factory(settings,demo=False): yield FixtureSource()
    index=Index(tmp_path/'service.sqlite3'); index.configure({'repo':'acme/shop','branch':'main'})
    service=Service(index,connector_factory=factory)
    asyncio.run(service.scan()); service.llm.adapters['ollama']=Adapter(ProviderError('timeout'))
    response=asyncio.run(service.ask('How does login work?'))
    assert response['error'] and response['sources'] and not response['statements']
    assert response['generation']['attempts'][-1]['error']=='timeout'
    with index.db() as db:
        old='{"statements":[],"sources":[],"legacy":true}'
        db.execute('UPDATE answers SET response=? WHERE id=?',(old,response['answer_id']))
    Router(Index(index.path))
    with index.db() as db: assert db.execute('SELECT response FROM answers').fetchone()[0]==old

def test_overview_resumes_only_successful_topics_and_invalidates_changed_routing(tmp_path,monkeypatch):
    from pka import service as module
    @asynccontextmanager
    async def factory(settings,demo=False): yield FixtureSource()
    index=Index(tmp_path/'overview.sqlite3'); index.configure({'repo':'acme/shop','branch':'main'})
    calls=[]; failing=True
    async def writer(question,sources):
        calls.append(question)
        if failing and question==module.TOPICS[1]['ask']: raise SourceError('llm_unavailable','Temporarily unavailable')
        return {'statements':[{'text':'The login function checks passwords.','source_ids':[sources[0]['source_id']]}],'missing_information':''}
    service=Service(index,connector_factory=factory,generator=writer); asyncio.run(service.scan())
    monkeypatch.setattr(module,'topics_for',lambda present:module.TOPICS[:2])
    sources=index.search('login',index.active_scan()); monkeypatch.setattr(index,'search_many',lambda *a,**kw:sources)
    first=asyncio.run(service.build_overview()); assert first['failed_topics']==1 and len(calls)==2
    failing=False
    second=asyncio.run(service.build_overview()); assert second['failed_topics']==0 and len(calls)==3
    assert second['sections'][0]['cache_hit'] and second['sections'][0]['sources']==first['sections'][0]['sources']
    config=service.llm.store.config(); config.local_model='another-local-model'; service.llm.store.save_config(config.model_dump())
    asyncio.run(service.build_overview()); assert len(calls)==5
    index.configure({'repo':'other/project','branch':'main'})
    with index.db() as db: assert db.execute('SELECT count(*) FROM ai_topic_cache').fetchone()[0]==0


@pytest.mark.parametrize('change',['none','revoked','head','project'])
def test_connected_github_cloud_check_reuses_snapshot_access_guards(tmp_path,change):
    source=FixtureSource()
    @asynccontextmanager
    async def factory(settings,demo=False): yield source
    index=Index(tmp_path/'access.sqlite3');index.configure({'repo':'acme/private','branch':'main'})
    service=Service(index,connector_factory=factory)
    assert not asyncio.run(service.cloud_repository_access('acme/private'))
    asyncio.run(service.scan())
    assert not asyncio.run(service.cloud_repository_access('another/repository'))
    if change=='none':
        assert asyncio.run(service.cloud_repository_access('acme/private'))
        service.demo=True
        assert not asyncio.run(service.cloud_repository_access('acme/private'))
        return
    async def changed_access(commit=''):
        if change=='revoked': raise SourceError('access_denied','Access revoked')
        if change=='project': index.configure({'repo':'another/repository','branch':'main'})
        return {'head':('b' if change=='head' else 'a')*40}
    source.check_access=changed_access
    with pytest.raises(SourceError) as error:
        asyncio.run(service.cloud_repository_access('acme/private'))
    assert error.value.code==('access_denied' if change=='revoked' else 'stale')
    assert index.active_scan() is None


def test_overview_pacing_preserves_cache_and_can_be_cancelled(tmp_path,monkeypatch):
    from pka import service as module
    @asynccontextmanager
    async def factory(settings,demo=False): yield FixtureSource()
    index=Index(tmp_path/'paced.sqlite3'); index.configure({'repo':'acme/shop','branch':'main'})
    calls=[]
    async def writer(question,sources):
        calls.append(question)
        if len(calls)==1: asyncio.get_running_loop().call_later(.1,service.cancel.set)
        return {'statements':[{'text':'Login checks passwords.','source_ids':[sources[0]['source_id']]}],'missing_information':''}
    service=Service(index,connector_factory=factory,generator=writer);asyncio.run(service.scan())
    monkeypatch.setattr(module,'topics_for',lambda present:module.TOPICS[:2])
    sources=index.search('login',index.active_scan());monkeypatch.setattr(index,'search_many',lambda *a,**kw:sources)
    config=service.llm.store.config();config.overview_concurrency=1;config.overview_interval_seconds=60
    service.llm.store.save_config(config.model_dump());signature=service.llm.cache_signature()
    with pytest.raises(SourceError,match='cancelled'): asyncio.run(service.build_overview())
    assert len(calls)==1
    with index.db() as db: assert db.execute('SELECT count(*) FROM ai_topic_cache').fetchone()[0]==1
    config.overview_interval_seconds=0;service.llm.store.save_config(config.model_dump())
    assert service.llm.cache_signature()==signature
    service.cancel.clear(); result=asyncio.run(service.build_overview())
    assert len(calls)==2 and result['sections'][0]['cache_hit']


def test_overview_pacing_waits_after_generation_even_with_concurrency(tmp_path,monkeypatch):
    from pka import service as module
    @asynccontextmanager
    async def factory(settings,demo=False): yield FixtureSource()
    index=Index(tmp_path/'paced-completion.sqlite3');index.configure({'repo':'acme/shop','branch':'main'})
    starts=[];ends=[]
    async def writer(question,sources):
        starts.append(time.monotonic())
        await asyncio.sleep(.08)
        ends.append(time.monotonic())
        return {'statements':[{'text':'Login checks passwords.','source_ids':[sources[0]['source_id']]}],'missing_information':''}
    service=Service(index,connector_factory=factory,generator=writer);asyncio.run(service.scan())
    monkeypatch.setattr(module,'topics_for',lambda present:module.TOPICS[:2])
    sources=index.search('login',index.active_scan());monkeypatch.setattr(index,'search_many',lambda *a,**kw:sources)
    config=service.llm.store.config();config.overview_concurrency=2;config.overview_interval_seconds=1
    service.llm.store.save_config(config.model_dump())
    result=asyncio.run(service.build_overview())
    assert len(starts)==2 and starts[1]-ends[0]>=.99
    assert not result['failed_topics']
