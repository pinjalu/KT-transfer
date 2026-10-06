"""Built-in example data. Never imports or executes the example source."""
from pka.connectors.base import SourceError

FILES = {
    'README.md': '# Example Shop\n\nA demonstration shop API used only for local testing.\n\n## Login\nUsers sign in with an email address and password. The API checks the stored password hash, then returns a session token.\n\n## Startup\nInstall the requirements, then run python app.py. This is example documentation, not a command executed by the assistant.\n',
    'app/auth.py': '"""Authentication for the example shop."""\n\ndef login(email, password, users, sessions):\n    """Check credentials and return a session token. A session identifies a signed-in user."""\n    user = users.find_by_email(email)\n    if user is None or not user.verify_password(password):\n        raise ValueError("Invalid credentials")\n    return sessions.create(user.id)\n',
    'docs/payments.md': '# Payments\n\nPayment processing is not implemented in this example. No provider or refund rules have been chosen.\n',
}
COMMIT = 'a' * 40

class FixtureSource:
    async def check_access(self, commit: str = '') -> dict:
        return {'head':COMMIT,'repo':'demo/example-shop','branch':'main'}
    async def begin_snapshot(self) -> dict:
        return {'commit':COMMIT,'entries':len(FILES)+1,'tree_incomplete':False}
    async def list_files(self, cursor: int = 0) -> dict:
        return {'files':[{'path':p,'size':len(t.encode()),'sha':'b'*40,'skip':''} for p,t in FILES.items()]
                       + [{'path':'.env','size':20,'sha':'c'*40,'skip':'potential_secret_file'}], 'next_cursor':None}
    async def read_file(self, path: str) -> dict:
        if path not in FILES:
            raise SourceError('scope','File is outside the example snapshot.')
        return {'text':FILES[path], 'bytes':len(FILES[path].encode()),'sha':'b'*40}
