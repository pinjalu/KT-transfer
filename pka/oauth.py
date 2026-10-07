"""Click-to-connect for platforms that support OAuth, so nobody has to copy a token by hand.

The user presses Connect, approves the scopes on the platform's own page, and the platform
sends a short lived code back here. This exchanges that code for a token and stores it the same
way a typed credential is stored: in the local .env file, never shown again, never logged.

The scopes are fixed in the registry rather than chosen at request time, so a connect link can
only ever ask for the reading permissions this application declares. The browser cannot widen
them by changing the request.

One request is handled without the usual same-origin header, because it is a redirect arriving
from the platform. A single use random state, created here and checked on return, is what
proves that redirect belongs to a connect the user actually started.
"""
import base64
from dataclasses import dataclass
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx

from pka.connectors import registry
from pka.connectors.base import SourceError

STATE_SECONDS = 600
MAX_PENDING = 8


@dataclass
class Pending:
    platform: str
    redirect_uri: str
    created: float
    verifier: str = ''


_pending: dict = {}


def _sweep() -> None:
    cutoff = time.time() - STATE_SECONDS
    for key in [k for k, v in _pending.items() if v.created < cutoff]:
        _pending.pop(key, None)


def canonical_redirect(base_url: str, path: str) -> str:
    """Always hand the platform the loopback name it accepts.

    Slack accepts localhost and refuses 127.0.0.1, and it matches the address as exact text, so
    a browser sitting on 127.0.0.1 would otherwise send an address that can never be registered.
    """
    base = base_url.rstrip('/')
    for host in ('//127.0.0.1', '//[::1]', '//0.0.0.0'):
        if host in base:
            base = base.replace(host, '//localhost', 1)
            break
    return base + path


def begin(platform_key: str, base_url: str, env) -> str:
    """Return the platform's approval URL for this connect attempt."""
    platform = registry.BY_KEY.get(platform_key)
    oauth = (platform or {}).get('oauth')
    if not oauth:
        raise SourceError('oauth', 'That platform does not support connecting from the browser.')
    missing = [name for name in platform['credentials'] if not env(name, '')]
    if missing:
        raise SourceError('oauth', 'Add ' + ' and '.join(missing) + ' first, then press Connect.')
    _sweep()
    if len(_pending) >= MAX_PENDING:
        _pending.clear()
    state = secrets.token_urlsafe(24)
    redirect_uri = canonical_redirect(base_url, oauth['redirect_path'])
    verifier = secrets.token_urlsafe(64)[:96] if oauth.get('pkce') else ''
    _pending[state] = Pending(platform_key, redirect_uri, time.time(), verifier)
    query = {
        'client_id': env(platform['credentials'][0], ''),
        'user_scope': ','.join(oauth['user_scopes']),
        'redirect_uri': redirect_uri,
        'state': state,
    }
    if verifier:
        digest = hashlib.sha256(verifier.encode()).digest()
        query['code_challenge'] = base64.urlsafe_b64encode(digest).decode().rstrip('=')
        query['code_challenge_method'] = 'S256'
    return oauth['authorize'] + '?' + urlencode(query)


async def complete(state: str, code: str, env, transport=None) -> tuple:
    """Exchange the returned code for a token. Returns the platform key and the token name."""
    _sweep()
    waiting = _pending.pop(state, None)
    if not waiting:
        # Either someone replayed an old link or this redirect was not started here.
        raise SourceError('oauth', 'This connect link has expired or was not started here. Press Connect again.')
    platform = registry.BY_KEY[waiting.platform]
    oauth = platform['oauth']
    data = {
        'client_id': env(platform['credentials'][0], ''),
        'client_secret': env(platform['credentials'][1], ''),
        'code': code,
        'redirect_uri': waiting.redirect_uri,
    }
    if waiting.verifier:
        data['code_verifier'] = waiting.verifier
    async with httpx.AsyncClient(transport=transport, timeout=30, trust_env=False) as client:
        try:
            response = await client.post(oauth['exchange'], data=data)
        except httpx.RequestError:
            raise SourceError('oauth', 'Could not reach the platform to finish connecting.') from None
    try:
        body = response.json()
    except ValueError:
        raise SourceError('oauth', 'The platform returned an unreadable response.') from None
    if not body.get('ok'):
        # Slack puts a short machine readable reason here. It never contains the token.
        raise SourceError('oauth', 'The platform refused the connection: ' + str(body.get('error', 'unknown')) + '.')
    token = (body.get('authed_user') or {}).get('access_token') or body.get('access_token')
    if not token:
        raise SourceError('oauth', 'The platform did not return a token for your account.')
    granted = (body.get('authed_user') or {}).get('scope', '')
    return waiting.platform, oauth['token_name'], token, granted
