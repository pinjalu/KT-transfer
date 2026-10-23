"""Bounded, non-echoing authentication endpoints and HTTP cookie handling."""
import json
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from pka.auth import AuthError, digest

PUBLIC_API = {'/api/auth/status', '/api/auth/login', '/api/auth/setup'}


def cookie_name(store):
    return 'pka_session_' + digest(str(store.path.resolve()))[:12]


def origin(request):
    return str(request.base_url).rstrip('/')


def token(request, store):
    return request.cookies.get(cookie_name(store), '')


def clear_cookie(response, request, store):
    response.delete_cookie(cookie_name(store), path='/', httponly=True,
                           secure=request.url.scheme == 'https', samesite='lax')


def signed_in(request, store, value):
    response = JSONResponse({'authenticated':True})
    # HTTP is supported ONLY on loopback. HTTPS gets Secure; LAN/proxy deployment is not supported.
    response.set_cookie(cookie_name(store), value, httponly=True, samesite='lax',
                        secure=request.url.scheme == 'https', path='/')
    return response


async def json_body(request):
    content = b''
    async for chunk in request.stream():
        content += chunk
        if len(content) > 8192:
            raise AuthError('Request too large.', 413)
    try:
        return json.loads(content)
    except (ValueError, UnicodeDecodeError):
        raise AuthError('Enter the required sign-in fields.', 422) from None


async def fields(request, expected):
    data = await json_body(request)
    if not isinstance(data, dict) or set(data) != set(expected):
        raise AuthError('Enter the required sign-in fields.', 422)
    if any(not isinstance(data[key], str) or not 1 <= len(data[key]) <= limit
           for key, limit in expected.items()):
        raise AuthError('A sign-in field is empty or too long.', 422)
    return data


def install(app, store):
    @app.exception_handler(AuthError)
    async def auth_error(request, exc):
        # Neither input values nor hashes/session identifiers enter logs or error responses.
        response = JSONResponse({'detail':str(exc), 'code':'authentication'}, status_code=exc.status)
        if exc.retry_after:
            response.headers['Retry-After'] = str(exc.retry_after)
        return response

    @app.get('/api/auth/status')
    async def status(request: Request):
        session = await run_in_threadpool(store.session, token(request, store), origin(request))
        return {'authenticated':bool(session), 'setup_required':not store.configured(),
                'user':session, 'idle_seconds':1800, 'absolute_seconds':28800}

    @app.post('/api/auth/setup')
    async def setup(request: Request):
        data = await fields(request, {'code':100, 'username':80, 'password':128})
        value = await run_in_threadpool(store.setup, data['code'], data['username'], data['password'], origin(request))
        request.state.audit_actor = 1
        return signed_in(request, store, value)

    @app.post('/api/auth/login')
    async def login(request: Request):
        data = await fields(request, {'username':80, 'password':128})
        value = await run_in_threadpool(store.login, data['username'], data['password'],
                                        origin(request), token(request, store))
        request.state.audit_actor = store.session(value, origin(request))['id']
        return signed_in(request, store, value)

    def owner(request):
        if request.state.owner['role'] != 'owner':
            raise AuthError('Owner access is required.', 403)

    @app.get('/api/admin/accounts')
    async def accounts(request: Request):
        owner(request)
        return {'accounts':store.members()}

    @app.post('/api/admin/accounts')
    async def create_member(request: Request):
        owner(request)
        data = await fields(request, {'username':80, 'password':128})
        account = await run_in_threadpool(store.create_member, data['username'], data['password'])
        request.state.audit_target = account['id']
        return account

    @app.post('/api/admin/accounts/{user_id}/enabled')
    async def member_enabled(user_id: int, request: Request):
        owner(request)
        data = await json_body(request)
        if not isinstance(data, dict) or set(data) != {'enabled'} or type(data['enabled']) is not bool:
            raise AuthError('Choose whether this member is enabled.', 422)
        await run_in_threadpool(store.set_member_enabled, user_id, data['enabled'])
        if not data['enabled']:
            workspace = getattr(app.state, 'workspaces', {}).get(user_id)
            if workspace:
                service = workspace[0].state.service
                service.cancel.set()
                if service.task and not service.task.done():
                    service.task.cancel()
        request.state.audit_target = user_id
        return {'saved':True}

    @app.get('/api/admin/audit')
    async def audit(request: Request, before: int = 0):
        owner(request)
        if before < 0:
            raise AuthError('Invalid audit cursor.', 422)
        rows = store.audit_records(before)
        return {'records':rows, 'next_before':rows[-1]['id'] if len(rows) == 100 else None}

    @app.post('/api/auth/activity')
    async def activity(request: Request):
        session = await run_in_threadpool(store.session, token(request, store), origin(request), True)
        if not session:
            raise AuthError('Your session expired. Sign in again.')
        return {'authenticated':True, 'user':session}

    @app.post('/api/auth/logout')
    async def logout(request: Request):
        await run_in_threadpool(store.logout, token(request, store))
        response = JSONResponse({'authenticated':False})
        clear_cookie(response, request, store)
        return response

    @app.post('/api/auth/logout-all')
    async def logout_all(request: Request):
        await run_in_threadpool(store.logout, token(request, store), True)
        response = JSONResponse({'authenticated':False})
        clear_cookie(response, request, store)
        return response

    @app.post('/api/auth/password')
    async def password(request: Request):
        data = await fields(request, {'current_password':128, 'new_password':128})
        value = await run_in_threadpool(store.change_password, token(request, store), origin(request),
                                        data['current_password'], data['new_password'])
        return signed_in(request, store, value)
