"""Give existing feature tests a real, authenticated disposable owner session."""
from fastapi.testclient import TestClient as RawClient
from pka.auth_web import cookie_name

PASSWORD = 'Fixture owner passphrase 2026!'


def auth_cookies(app, base_url='http://localhost:8000'):
    store = app.state.auth
    if store.configured():
        value = store.login('fixture-owner', PASSWORD, base_url.rstrip('/'))
    else:
        value = store.setup(store.setup_path.read_text(), 'fixture-owner', PASSWORD, base_url.rstrip('/'))
    return {cookie_name(store):value}


class OwnerClient(RawClient):
    def __init__(self, app, *args, **kwargs):
        cookies = auth_cookies(app, kwargs.get('base_url', 'http://testserver'))
        kwargs['cookies'] = {**cookies, **kwargs.get('cookies', {})}
        super().__init__(app, *args, **kwargs)
