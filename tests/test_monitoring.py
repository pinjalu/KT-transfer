import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from auth_helpers import OwnerClient
from pka import monitoring
from pka.connectors.base import SourceError
from pka.llm.config import Target
from pka.llm.types import Reply, ProviderError
from pka.web import create_app
from test_llm_router import setup, Adapter, MemoryVault, enable, generate

TARGET = Target(provider='groq',model='openai/gpt-oss-120b')


def records(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def test_content_free_log_rotation_and_concurrent_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(monitoring,'MAX_BYTES',700)
    index = tmp_path/'index.sqlite3'
    def write(n):
        assert monitoring.event('test.event',index_path=index,count=n,provider='groq',
            key='SECRET_KEY',prompt='PRIVATE_PROMPT',msg='SECRET_EXCEPTION',
            path='/secret/repo.py',code='multiline\ninjection',elapsed_seconds=float('nan'))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write,range(100)))
    files=list((tmp_path/'logs').glob('activity.jsonl*'))
    assert 2 <= len(files) <= monitoring.BACKUPS+1
    for file in files:
        assert file.stat().st_size <= 700
        text=file.read_text()
        assert not any(secret in text for secret in ('SECRET','PRIVATE','injection','repo.py','NaN'))
        assert all(row['event']=='test.event' for row in records(file))


def test_workspace_scopes_and_correlation_are_isolated(tmp_path):
    first=tmp_path/'first'/'index.sqlite3'; second=tmp_path/'second'/'index.sqlite3'
    with monitoring.request_scope(first):
        monitoring.event('first.start')
        with monitoring.request_scope(second): monitoring.event('second.start')
        monitoring.event('first.end')
    one=records(monitoring.path(first)); two=records(monitoring.path(second))
    assert len(one)==2 and len(two)==1
    assert one[0]['request_id']==one[1]['request_id']!=two[0]['request_id']


def test_unwritable_log_does_not_break_operation(tmp_path,monkeypatch):
    def unavailable(*args,**kwargs): raise PermissionError('sensitive disk detail')
    monkeypatch.setattr(Path,'mkdir',unavailable)
    assert monitoring.event('test.event',index_path=tmp_path/'index.sqlite3') is False


def test_restart_migration_preserves_saved_and_cleared_credentials(tmp_path,monkeypatch):
    from pka.vault import Vault
    monkeypatch.setattr('pka.vault.protect',lambda data,decrypt=False:data)
    vault=Vault(tmp_path/'fixture.dpapi')
    vault.save({'GEMINI_API_KEY':'user-saved-key','GROQ_API_KEY':''})
    monkeypatch.setenv('GEMINI_API_KEY','stale-parent-key')
    monkeypatch.setenv('GROQ_API_KEY','must-not-resurrect')
    env=tmp_path/'.env'
    env.write_text('GEMINI_API_KEY=stale-file-key\nGITHUB_TOKEN=first-import\nOTHER=keep\n')
    vault.migrate(env,{'GEMINI_API_KEY','GROQ_API_KEY','GITHUB_TOKEN'})
    assert vault.read()=={'GEMINI_API_KEY':'user-saved-key','GROQ_API_KEY':'','GITHUB_TOKEN':'first-import'}
    assert env.read_text()=='OTHER=keep\n'
    import os
    assert not os.getenv('GEMINI_API_KEY') and not os.getenv('GROQ_API_KEY')


def test_probe_disabled_provider_is_fixed_synthetic_and_never_enables_project(setup):
    router,adapters,_=setup
    router.store.confirm('groq',router.key_reader('groq'),True)
    async def capture(request,target,key,timeout):
        assert not request.sources and not request.has_history
        assert 'Synthetic connection test' in request.messages[0]['content']
        return Reply('{"status":"ok","sum":5}',30,12)
    adapters['groq'].generate=capture
    value=asyncio.run(router.probe(TARGET))
    assert value.generation['provider']=='groq'
    assert not router.store.config().providers['groq'].enabled
    assert router.store.permission('sample/public')['providers']==[]
    events=records(monitoring.path(router.index.path))
    assert events[-1]['status']=='succeeded' and events[-1]['diagnostic']
    assert all(e['synthetic'] for e in events)


@pytest.mark.parametrize('block',['unconfirmed','missing_key','catalog','cooldown','limit','changed_key','invalid','failed'])
def test_probe_retains_free_quota_and_validation_gates_no_fallback(setup,monkeypatch,block):
    router,adapters,_=setup
    if block!='unconfirmed': router.store.confirm('groq',router.key_reader('groq'),True)
    if block=='missing_key': router.key_reader=lambda p:''
    if block=='catalog': monkeypatch.setattr('pka.llm.router.catalog_current',lambda:False)
    if block=='cooldown':
        adapters['groq'].result=ProviderError('quota',status=429,retry_after=60)
        with pytest.raises(SourceError): asyncio.run(router.probe(TARGET))
    if block=='limit':
        config=router.store.config(); config.project_limits.tpd=100
        router.store.save_config(config.model_dump())
    if block=='changed_key':
        async def rotate():
            router.key_reader=lambda p:'new-key'
            return Reply('{"status":"ok","sum":5}')
        adapters['groq'].result=rotate
    if block=='invalid': adapters['groq'].result=Reply('{"status":"ok","sum":999}')
    if block=='failed': adapters['groq'].result=RuntimeError('SECRET_KEY PRIVATE_PROMPT')
    before=len(adapters['groq'].calls)
    with pytest.raises(SourceError): asyncio.run(router.probe(TARGET))
    assert not adapters['gemini'].calls and not adapters['ollama'].calls
    if block in ('unconfirmed','missing_key','catalog','cooldown','limit'):
        assert len(adapters['groq'].calls)==before
    log=monitoring.path(router.index.path).read_text()
    assert 'SECRET_KEY' not in log and 'PRIVATE_PROMPT' not in log and 'fixture-key' not in log


def test_router_logs_fallback_and_provider_error_without_content(setup):
    router,adapters,request=setup; enable(router)
    adapters['groq'].result=ProviderError('quota',status=429,retry_after=120)
    assert generate(router,request).generation['provider']=='gemini'
    rows=records(monitoring.path(router.index.path))
    assert len({row['generation_id'] for row in rows})==1
    failure=next(row for row in rows if row['event']=='llm.failed')
    assert failure['http_status']==429 and failure['retry_after_seconds']==120
    assert next(row for row in rows if row['event']=='llm.fallback')['provider']=='gemini'
    assert 'Synthetic question' not in json.dumps(rows)


def test_probe_api_auth_strict_input_and_content_free_http_log(tmp_path):
    vault=MemoryVault(); app=create_app(True,tmp_path/'api.sqlite3',credential_store=vault)
    router=app.state.service.llm
    router.adapters['groq']=Adapter(Reply('{"status":"ok","sum":5}',20,10))
    headers={'x-pka-request':'1'}
    with TestClient(app,base_url='http://localhost:8000',headers=headers) as anonymous:
        assert anonymous.post('/api/ai/test',json=TARGET.model_dump()).status_code==401
    with OwnerClient(app,base_url='http://localhost:8000',headers=headers) as client:
        assert not client.post('/api/ai/test',json=TARGET.model_dump()).json()['ok']
        client.post('/api/ai/key',json={'provider':'groq','key':'SECRET_TEST_KEY'})
        client.post('/api/ai/confirmation',json={'provider':'groq','free_plan_without_billing_or_credits':True})
        value=client.post('/api/ai/test',json=TARGET.model_dump()).json()
        assert value['ok'] and value['generation']['provider']=='groq'
        bad=client.post('/api/ai/test',json={**TARGET.model_dump(),'prompt':'PRIVATE_PROMPT'})
        assert bad.status_code==422 and 'PRIVATE_PROMPT' not in bad.text
        assert client.post('/api/ai/test',json=TARGET.model_dump(),headers={'origin':'http://evil.test'}).status_code==403
        client.get('/api/status?key=SECRET_QUERY')
        info=client.get('/api/ai').json()
        assert not info['config']['providers']['groq']['enabled'] and not info['permission']['providers']
        assert info['monitoring']['file']=='logs/activity.jsonl'
    log=monitoring.path(router.index.path).read_text()
    assert not any(secret in log for secret in ('SECRET_TEST_KEY','PRIVATE_PROMPT','SECRET_QUERY'))
    http=[r for r in records(monitoring.path(router.index.path)) if r['event']=='http.completed']
    assert {200,401,403,422} <= {r['http_status'] for r in http}
