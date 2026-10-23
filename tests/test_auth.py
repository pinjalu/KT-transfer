"""Security boundaries use the raw client, never the preauthenticated feature helper."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import httpx
import pytest

from pka import auth, auth_web, oauth
from pka.web import create_app

PASSWORD = 'A long private fixture passphrase!'
NEXT = 'A different private fixture passphrase!'
BASE = 'http://localhost:8000'
HEADERS = {'x-pka-request':'1'}


@pytest.fixture
def state(tmp_path):
    app = create_app(True, tmp_path/'demo.sqlite3')
    with TestClient(app, base_url=BASE, headers=HEADERS) as client:
        yield app, app.state.auth, client


def setup(store, client):
    response = client.post('/api/auth/setup', json={'code':store.setup_path.read_text(),
                           'username':'Owner', 'password':PASSWORD})
    assert response.status_code == 200, response.text
    return response


def session_token(store, client):
    return client.cookies.get(auth_web.cookie_name(store))


def test_fresh_and_existing_project_data_are_private_until_setup(state):
    app, store, client = state
    index = app.state.service.index
    before = Path(index.path).read_bytes()
    response = client.get('/api/auth/status')
    assert response.json()['setup_required'] and response.json()['user'] is None
    assert store.setup_path.read_text() not in response.text
    for path in ['/api/status','/api/platforms','/api/import-history','/api/overview',
                 '/api/jira/tasks','/api/decisions/channels','/api/features','/api/slack/channels']:
        response = client.get(path)
        assert response.status_code == 401 and 'demo/example-shop' not in response.text
        assert response.headers['cache-control'] == 'no-store'
    for path in ['/api/config','/api/ask','/api/credentials','/api/scan','/api/jobs/1/cancel']:
        assert client.post(path,json={}).status_code == 401
    assert client.get('/legacy', follow_redirects=False).headers['location'] == '/login'
    assert client.get('/login').status_code == 200
    assert Path(index.path).read_bytes() == before


def test_every_registered_data_endpoint_defaults_to_authentication(state):
    app, _, client = state
    for route in app.routes:
        path = getattr(route, 'path', '')
        if path.startswith('/api/') and path not in auth_web.PUBLIC_API and path != '/api/slack/callback':
            for method in getattr(route, 'methods', set()) - {'HEAD', 'OPTIONS'}:
                response = client.request(method, path.replace('{job_id}','1').replace('{name}','file'), json={})
                assert response.status_code == 401, (method,path,response.text)


def test_setup_is_single_use_and_hashes_secrets(state):
    _, store, client = state
    code = store.setup_path.read_text()
    response = setup(store, client)
    value = session_token(store, client)
    assert not store.setup_path.exists()
    assert client.get('/api/status').status_code == 200
    assert client.get('/api/auth/status').json()['user']['username'] == 'owner'
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=lax' in cookie and 'path=/' in cookie
    assert 'domain=' not in cookie and 'expires=' not in cookie
    raw = store.path.read_bytes()
    for secret in (code, PASSWORD, value):
        assert secret.encode() not in raw
    assert 'scrypt:131072:8:1:' in raw.decode('latin1')
    assert client.post('/api/auth/setup',json={'code':code,'username':'other','password':PASSWORD}).status_code == 401
    assert store.configured()


def test_setup_rejects_wrong_code_and_weak_password(state):
    _, store, client = state
    assert client.post('/api/auth/setup',json={'code':'wrong','username':'owner','password':PASSWORD}).status_code == 401
    assert client.post('/api/auth/setup',json={'code':store.setup_path.read_text(),'username':'owner','password':'short'}).status_code == 422
    assert not store.configured()


@pytest.mark.parametrize('payload', [None, [], {'password':'sensitive-value'},
    {'username':'owner','password':{'leak':'sensitive-value'}},
    {'username':'owner','password':'sensitive-value'*20},
    {'username':'owner','password':'sensitive-value','extra':'secret'}])
def test_invalid_auth_input_never_echoes_values(state,payload):
    _, _, client = state
    response = client.post('/api/auth/login',json=payload)
    assert response.status_code == 422
    assert 'sensitive-value' not in response.text and 'secret' not in response.text


def test_streamed_and_declared_large_requests_are_refused(state):
    _,_,client = state
    assert client.post('/api/auth/login',content='x'*8193).status_code == 413
    assert client.post('/api/auth/login',content=iter([b'x'*5000,b'x'*5000])).status_code == 413


@pytest.mark.parametrize('extra', [{'origin':'https://evil.test'}, {'origin':'http://localhost:9000'},
    {'sec-fetch-site':'cross-site'}, {'host':'evil.test'}, {'x-pka-request':''}])
def test_csrf_origin_host_and_header_protect_login_and_logout(state, extra):
    _,store,client = state
    setup(store,client)
    for path in ['/api/auth/login','/api/auth/logout','/api/auth/password','/api/auth/setup']:
        response = client.post(path, headers=extra,json={'password':PASSWORD})
        assert response.status_code == 403
        assert response.headers['cache-control'] == 'no-store'
        assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert client.get('/api/status').status_code == 200


def test_login_errors_are_generic_and_unicode_is_safe(state):
    _,store,client = state
    setup(store,client)
    client.post('/api/auth/logout')
    responses = [client.post('/api/auth/login',json={'username':u,'password':p}) for u,p in
                 [('owner','wrong'), ('unknown',PASSWORD), ('未知',PASSWORD)]]
    assert {r.status_code for r in responses} == {401}
    assert len({r.text for r in responses}) == 1


def test_throttle_persists_across_restart_and_cannot_bypass_by_username(state, monkeypatch):
    _,store,client=state
    setup(store,client)
    client.post('/api/auth/logout')
    for i in range(auth.ATTEMPTS):
        assert client.post('/api/auth/login',json={'username':str(i),'password':'bad'}).status_code == 401
    store2 = auth.AuthStore(store.path.with_suffix('.sqlite3').with_name('demo.sqlite3'))
    with pytest.raises(auth.AuthError) as error:
        store2.login('owner',PASSWORD,BASE)
    assert error.value.status == 429 and error.value.retry_after > 0
    with store.db() as db:
        db.execute('UPDATE throttle SET started=started-?', (auth.RETRY_SECONDS+1,))
    assert client.post('/api/auth/login',json={'username':'owner','password':PASSWORD}).status_code == 200


def test_tampering_logout_and_session_fixation(state):
    _,store,client=state
    setup(store,client)
    old=session_token(store,client)
    assert client.post('/api/auth/login',json={'username':'owner','password':PASSWORD}).status_code == 200
    new=session_token(store,client)
    assert old != new and store.session(old,BASE) is None
    assert store.session(new+'x',BASE) is None
    assert store.session(new,'http://localhost:9000') is None
    assert store.session(new,'http://127.0.0.1:8000') is None
    assert client.post('/api/auth/logout').status_code == 200
    assert store.session(new,BASE) is None
    client.cookies.set(auth_web.cookie_name(store),new)
    assert client.get('/api/status').status_code == 401


def test_password_change_revokes_every_old_session_and_rotates_current(state):
    _,store,client=state
    setup(store,client)
    old=session_token(store,client)
    other=store.login('owner',PASSWORD,BASE)
    response=client.post('/api/auth/password',json={'current_password':PASSWORD,'new_password':NEXT})
    assert response.status_code == 200
    assert session_token(store,client) not in {old,other}
    assert store.session(old,BASE) is None and store.session(other,BASE) is None
    assert client.get('/api/status').status_code == 200
    with pytest.raises(auth.AuthError):store.login('owner',PASSWORD,BASE)
    assert store.login('owner',NEXT,BASE)


def test_wrong_current_password_does_not_change_owner(state):
    _,store,client=state
    setup(store,client)
    response=client.post('/api/auth/password',json={'current_password':'wrong','new_password':NEXT})
    assert response.status_code == 403 and NEXT not in response.text
    assert store.login('owner',PASSWORD,BASE)


def test_all_sessions_logout_and_local_recovery(state):
    _,store,client=state
    setup(store,client)
    other=store.login('owner',PASSWORD,BASE)
    assert client.post('/api/auth/logout-all').status_code == 200
    assert store.session(other,BASE) is None
    current=store.login('owner',PASSWORD,BASE)
    assert store.reset_password(NEXT) == 'owner'
    assert store.session(current,BASE) is None
    with pytest.raises(auth.AuthError):store.login('owner',PASSWORD,BASE)
    assert store.login('owner',NEXT,BASE)


@pytest.mark.parametrize('field,seconds', [('active',auth.IDLE_SECONDS),('created',auth.ABSOLUTE_SECONDS)])
def test_expiry_is_server_enforced_and_polling_does_not_renew(state, field, seconds):
    _,store,client=state
    setup(store,client)
    with store.db() as db:
        active=db.execute('SELECT active FROM sessions').fetchone()[0]
    for _ in range(3):
        assert client.get('/api/status').status_code == 200
        assert client.get('/api/auth/status').json()['authenticated']
    with store.db() as db:
        assert db.execute('SELECT active FROM sessions').fetchone()[0] == active
        db.execute(f'UPDATE sessions SET {field}={field}-?', (seconds+1,))
    assert client.post('/api/auth/activity').status_code == 401
    assert client.get('/api/status').status_code == 401


def test_activity_renews_idle_but_not_absolute_timeout(state):
    _,store,client=state
    setup(store,client)
    with store.db() as db:
        db.execute('UPDATE sessions SET active=active-100')
        before=dict(db.execute('SELECT * FROM sessions').fetchone())
    assert client.post('/api/auth/activity').status_code == 200
    with store.db() as db:
        after=dict(db.execute('SELECT * FROM sessions').fetchone())
    assert after['active'] > before['active'] and after['created'] == before['created']


def test_sessions_survive_restart_and_are_bounded(state):
    _,store,client=state
    setup(store,client)
    value=session_token(store,client)
    restarted=auth.AuthStore(store.path.with_name('demo.sqlite3'))
    assert restarted.session(value,BASE)
    with store.db() as db:
        for _ in range(auth.MAX_SESSIONS+1):store._session(db,BASE,1)
        assert db.execute('SELECT count(*) FROM sessions').fetchone()[0] == auth.MAX_SESSIONS
    assert not restarted.session(value,BASE)


def test_concurrent_first_setup_creates_only_one_owner(state):
    _,store,_=state
    code=store.setup_path.read_text()
    def attempt(name):
        try:return store.setup(code,name,PASSWORD,BASE)
        except auth.AuthError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,['first','second']))
    assert sum(bool(result) for result in results) == 1
    assert store.configured() and not store.setup_path.exists()


def test_https_cookie_is_secure(state):
    app,store,_=state
    with TestClient(app,base_url='https://localhost:8000',headers=HEADERS) as secure:
        response=setup(store,secure)
        assert 'Secure' in response.headers['set-cookie']
        assert secure.get('/api/status').status_code == 200


def test_oauth_callback_requires_session_and_binds_state(state, monkeypatch):
    app,store,client=state
    assert client.get('/api/slack/callback?code=secret&state=secret',follow_redirects=False).headers['location'] == '/login'
    setup(store,client)
    monkeypatch.setenv('SLACK_CLIENT_ID','fixture-id')
    monkeypatch.setenv('SLACK_CLIENT_SECRET','fixture-secret')
    session=auth.digest(session_token(store,client))
    url=oauth.begin('slack_user',BASE,lambda name,default='':{'SLACK_CLIENT_ID':'id','SLACK_CLIENT_SECRET':'secret'}.get(name,default),session_id=session)
    state_value=parse_qs(urlsplit(url).query)['state'][0]
    transport=httpx.MockTransport(lambda request: pytest.fail('Mismatched session must not exchange a code'))
    with pytest.raises(Exception,match='another sign-in session'):
        asyncio.run(oauth.complete(state_value,'code',lambda name,default='':'fixture',transport,session_id='wrong'))


def test_slow_response_is_withheld_after_logout(state):
    app,store,client=state
    setup(store,client)
    @app.get('/api/auth-fixture-slow')
    async def slow():
        store.logout(session_token(store,client))
        return {'private':'should never escape'}
    app.router.routes.insert(-1, app.router.routes.pop())
    response=client.get('/api/auth-fixture-slow')
    assert response.status_code == 401 and 'should never escape' not in response.text


def test_password_hash_is_salted_and_verifiable():
    first,second=auth.password_hash(PASSWORD),auth.password_hash(PASSWORD)
    assert first != second
    assert auth.password_matches(PASSWORD,first)
    assert not auth.password_matches('wrong',first)
    assert not auth.password_matches(PASSWORD,'malformed')
