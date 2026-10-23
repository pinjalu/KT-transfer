"""Adversarial account isolation using real sessions and controlled source permissions."""
import asyncio
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from pka import credentials
from pka.auth_web import cookie_name
from pka.config import now
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource, COMMIT
from pka.index import chunk_file
from pka.vault import Vault
from pka.web import create_app

PASSWORD = 'Fixture private member password!'
BASE = 'http://localhost:8000'
HEADERS = {'x-pka-request':'1'}


@pytest.fixture
def team(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('PKA_EMBED_MODEL', '')
    monkeypatch.setenv('GITHUB_TOKEN', 'HOST-CREDENTIAL-MUST-NOT-LEAK')
    owner_vault = Vault(tmp_path/'owner.dpapi')
    owner_vault.save({'GITHUB_TOKEN':'owner-permission'})
    calls, denied = [], set()
    class Source(FixtureSource):
        async def check_access(self, commit=''):
            identity = credentials.getenv('GITHUB_TOKEN')
            calls.append(identity)
            if not identity or identity in denied:
                raise SourceError('access_denied', 'Source permission was revoked.')
            return await super().check_access(commit)
    @asynccontextmanager
    async def factory(settings, demo=False):
        yield Source()
    app = create_app(False, tmp_path/'index.sqlite3', factory, credential_store=owner_vault)
    with ExitStack() as stack:
        clients = [stack.enter_context(TestClient(app, base_url=BASE, headers=HEADERS)) for _ in range(3)]
        owner, alice, bob = clients
        assert owner.post('/api/auth/setup',json={'code':app.state.auth.setup_path.read_text(),
                          'username':'owner','password':PASSWORD}).status_code == 200
        for name, client in [('alice',alice),('bob',bob)]:
            assert owner.post('/api/admin/accounts',json={'username':name,'password':PASSWORD}).status_code == 200
            assert client.post('/api/auth/login',json={'username':name,'password':PASSWORD}).status_code == 200
            assert client.get('/api/status').status_code == 200
        yield app, clients, calls, denied


def seed(app, client, user_id, marker):
    assert client.post('/api/credentials',json={'values':{'GITHUB_TOKEN':marker+'-permission'}}).status_code == 200
    assert client.post('/api/config',json={'repo':'acme/'+marker,'branch':'main'}).status_code == 200
    service = app.state.service if user_id == 1 else app.state.workspaces[user_id][0].state.service
    scan = {'id':1,'repo':'acme/'+marker,'branch':'main','commit':COMMIT,'status':'complete','finished':now()}
    scan['id'] = service.index.new_scan(scan)
    service.index.activate(scan['id'], chunk_file('private.md', '# Login\n\n'+(marker+' login verifies a private password. ')*8), scan)
    service.index.save_overview(scan['id'], COMMIT, {'marker':marker})
    async def model(question, sources):
        return {'statements':[{'text':sources[0]['text'],'source_ids':[sources[0]['source_id']]}], 'missing_information':''}
    service.generator = model
    return service


def test_members_start_empty_and_cannot_select_another_workspace(team):
    app, (owner,alice,bob), _, _ = team
    seed(app, owner, 1, 'owner-restricted')
    for client in (alice,bob):
        response = client.get('/api/status?user_id=1&workspace=1',headers={'X-PKA-User':'1'})
        assert 'owner-restricted' not in response.text
        assert not response.json()['ready']
        assert 'owner-restricted' not in client.get('/api/overview').text
        assert client.get('/api/admin/accounts').status_code == 403
        assert client.get('/api/admin/audit').status_code == 403
        assert client.post('/api/admin/accounts',json={'username':'intruder','password':PASSWORD}).status_code == 403
        assert client.post('/api/admin/accounts/1/enabled',json={'enabled':False}).status_code == 403


def test_retrieval_cached_views_feedback_and_credentials_are_private(team):
    app, (owner,alice,bob), calls, _ = team
    seed(app, owner, 1, 'owner-restricted')
    alice_service = seed(app, alice, 2, 'alice-restricted')
    seed(app, bob, 3, 'bob-restricted')
    for user_id, client, marker in [(1,owner,'owner-restricted'),(2,alice,'alice-restricted'),(3,bob,'bob-restricted')]:
        reply = client.post('/api/ask',json={'question':'How does login verify a password?'});
        assert reply.status_code == 200, reply.text
        assert reply.json()['sources'] and marker in reply.text
        for other in {'owner-restricted','alice-restricted','bob-restricted'} - {marker}:
            assert other not in reply.text and other not in client.get('/api/overview').text
        assert calls[-1] == marker+'-permission'
    with alice_service.index.db() as db:
        before = db.execute('SELECT rating FROM answers WHERE id=1').fetchone()[0]
    assert bob.post('/api/feedback',json={'answer_id':1,'rating':'correct','sufficiency':'sufficient'}).status_code == 200
    with alice_service.index.db() as db:
        assert db.execute('SELECT rating FROM answers WHERE id=1').fetchone()[0] == before
    assert alice.post('/api/jobs/999/cancel').status_code == 409


def test_member_does_not_inherit_host_credentials_and_logs(team):
    app, (owner,alice,_), _, _ = team
    assert alice.get('/api/platforms').json()['credentials']['GITHUB_TOKEN'] is False
    root = Path(app.state.service.index.path).parent
    (root/'logs').mkdir(exist_ok=True)
    (root/'logs'/'scan-0001-complete-secret.log').write_text('OWNER-PRIVATE-LOG')
    assert 'OWNER-PRIVATE-LOG' not in alice.get('/api/import-history').text
    assert alice.get('/api/import-history/scan-0001-complete-secret.log').status_code == 404
    assert owner.get('/api/import-history/scan-0001-complete-secret.log').status_code == 200


def test_revoked_upstream_permission_blocks_search_and_cached_code(team):
    app, (_,alice,_), _, denied = team
    service = seed(app, alice, 2, 'alice-restricted')
    denied.add('alice-restricted-permission')
    reply = alice.get('/api/overview')
    assert reply.status_code == 409 and 'alice-restricted' not in reply.text
    assert service.index.active_scan() is None
    assert not alice.post('/api/ask',json={'question':'login'}).json().get('sources')


def test_revocation_during_generation_withholds_answer(team):
    app, (_,alice,_), _, denied = team
    service = seed(app, alice, 2, 'alice-restricted')
    async def model(question, sources):
        denied.add('alice-restricted-permission')
        return {'statements':[{'text':'PRIVATE RESULT','source_ids':[sources[0]['source_id']]}]}
    service.generator = model
    result = alice.post('/api/ask',json={'question':'How does login work?'})
    assert result.status_code == 409 and 'PRIVATE RESULT' not in result.text
    with service.index.db() as db:
        assert db.execute('SELECT count(*) FROM answers').fetchone()[0] == 0


def test_disabling_member_revokes_sessions_without_affecting_others(team):
    app, (owner,alice,bob), _, _ = team
    old = alice.cookies.get(cookie_name(app.state.auth))
    assert owner.post('/api/admin/accounts/2/enabled',json={'enabled':False}).status_code == 200
    assert alice.get('/api/status').status_code == 401
    assert not app.state.auth.session(old, BASE)
    assert bob.get('/api/status').status_code == 200
    assert owner.post('/api/admin/accounts/2/enabled',json={'enabled':True}).status_code == 200
    assert not app.state.auth.session(old, BASE)
    assert alice.post('/api/auth/login',json={'username':'alice','password':PASSWORD}).status_code == 200
    assert alice.post('/api/auth/logout-all').status_code == 200
    assert owner.get('/api/status').status_code == bob.get('/api/status').status_code == 200


def test_member_password_changes_do_not_change_owner_or_other_members(team):
    app, (owner,alice,bob), _, _ = team
    assert alice.post('/api/auth/password',json={'current_password':PASSWORD,'new_password':PASSWORD+' changed'}).status_code == 200
    assert owner.get('/api/status').status_code == bob.get('/api/status').status_code == 200
    assert alice.get('/api/auth/status').json()['user']['id'] == 2


def test_audit_keeps_action_identity_and_omits_secrets(team):
    _, (owner,alice,_), _, _ = team
    secret = 'fixture-value-never-in-audit'
    assert alice.post('/api/credentials',json={'values':{'GITHUB_TOKEN':secret}}).status_code == 200
    assert alice.post('/api/credentials',json={'values':{'GITHUB_TOKEN':{'secret':secret}}}).status_code == 422
    response = owner.get('/api/admin/audit')
    assert secret not in response.text and PASSWORD not in response.text
    assert any(row['actor'] == 2 and row['action'] == 'api.set_credentials' for row in response.json()['records'])


def test_concurrent_credential_contexts_never_mutate_global_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN','HOST')
    first, second = Vault(tmp_path/'first.dpapi'), Vault(tmp_path/'second.dpapi')
    first.save({'GITHUB_TOKEN':'FIRST'}); second.save({'GITHUB_TOKEN':'SECOND'})
    async def request(vault, expected):
        with credentials.using(vault):
            for _ in range(5):
                await asyncio.sleep(0)
                assert credentials.getenv('GITHUB_TOKEN') == expected
    async def scenario():
        await asyncio.gather(request(first,'FIRST'),request(second,'SECOND'))
    asyncio.run(scenario())
    assert credentials.getenv('GITHUB_TOKEN') == 'HOST'
