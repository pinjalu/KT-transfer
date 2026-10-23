"""Route by the authenticated numeric account ID, never a browser-supplied workspace."""
from pathlib import Path
from fastapi import Request
from starlette.concurrency import run_in_threadpool
from pka import auth_web, credentials
from pka.config import workspace_directory
from pka.vault import Vault


class WorkspaceDispatch:
    def __init__(self, app, store, root_path, owner_vault, children, factory):
        self.app, self.store = app, store
        self.root = Path(root_path)
        self.owner_vault, self.children, self.factory = owner_vault, children, factory

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        session = await run_in_threadpool(self.store.session, auth_web.token(request, self.store), auth_web.origin(request))
        user_id = session['id'] if session else 1
        # Authentication/admin endpoints share the account store, but never expose a member's
        # source workspace. Every other route, including guessed IDs and logs, uses their index.
        shared = request.url.path.startswith(('/api/auth/', '/api/admin/', '/static/'))
        if user_id != 1 and not shared:
            if user_id not in self.children:
                folder = self.root.parent / (self.root.stem + '.users') / str(user_id)
                folder.mkdir(parents=True, exist_ok=True)
                vault = Vault(folder / 'credentials.dpapi')
                self.children[user_id] = (self.factory(folder / 'index.sqlite3', vault), vault, folder)
            app, vault, folder = self.children[user_id]
        else:
            app, vault, folder = self.app, self.owner_vault, None
        marker = workspace_directory.set(folder)
        try:
            with credentials.using(vault):
                await app(scope, receive, send)
        finally:
            workspace_directory.reset(marker)
