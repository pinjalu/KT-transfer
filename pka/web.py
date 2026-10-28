import asyncio
from contextlib import asynccontextmanager
import time
from dataclasses import asdict
import os
import re
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from pka import applog, monitoring, zip_projects, embed
from pka.plain_language import STYLE_VERSION
from pka.config import ROOT, KEEP_LOGS, LIMITS, data_dir, log_dir, validate_selection, project_name, selected_source
from pka import credentials, oauth
from pka.auth import AuthStore, digest
from pka import auth_web
from pka.connectors import registry
from pka.connectors.base import SourceError
from pka.connectors.local import is_local, local_selection
from pka import facts, features, coverage, quality, existing_tests, feature_kt, architecture
from pka.index import Index
from pka.overview import reading_order, topics_for
from pka.overview_scope import selected_local, current_local_payload
from pka.service import Service
from pka.conversation import Conversation
from pka.deployment import Hosting

class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    repo: str = Field(default='', max_length=400)
    branch: str = Field(default='main', max_length=200)
    source_kind: Literal['github', 'local'] = 'github'
    local_path: str = Field(default='', max_length=1000)
    add_to_project: bool = False
    platforms: list[str] = Field(default_factory=list, max_length=20)
class SearchMode(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['basic', 'semantic']

class CredentialUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    values: dict[str, str] = Field(max_length=10)
class JiraChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project: str = Field(default='', max_length=40)
class SlackChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    workspace: str = Field(default='', max_length=100)
    channels: list[dict] = Field(default_factory=list, max_length=20)
class Question(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # One character, not three. The old floor existed to stop an empty box being sent, and the
    # handler already refuses whitespace, but it also caught "hi" and "hy" and answered them
    # with a field validation error instead of the greeting the small talk guard exists to
    # give. A short question is not a malformed one.
    question: str = Field(min_length=1,max_length=600)
    conversation: Conversation | None = None
class Feedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer_id: int
    rating: Literal['correct','partially correct','incorrect','not assessed']
    sufficiency: Literal['sufficient','partly sufficient','insufficient','not assessed']

class EvaluationStart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    set_id: str = Field(min_length=1, max_length=80)

class EvaluationCompare(BaseModel):
    model_config = ConfigDict(extra='forbid')
    left: int = Field(gt=0)
    right: int = Field(gt=0)

class EvaluationReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    response_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    correctness: Literal['correct', 'partially correct', 'incorrect']
    source_sufficiency: Literal['sufficient', 'partly sufficient', 'insufficient']


def create_app(demo=False, db_path=None, connector_factory=None, *, auth_store=None,
               credential_store=None, _workspace_id=1, hosting=None):
    hosting = hosting or Hosting()
    # A listing is fetched from the platform and then reused for a short while. Without this the
    # browser's status poll asks Slack and Jira for the same list every few seconds, which earns
    # a rate limit and makes the page look broken.
    listings = {}
    LISTING_SECONDS = 120

    def cached(key):
        found = listings.get(key)
        if found and time.time() - found[0] < LISTING_SECONDS:
            return found[1]
        return None

    def remember(key, value):
        listings[key] = (time.time(), value)
        return value

    async def via_connector(method, **kwargs):
        """Ask the MCP server, so a credential never has to be handled in the request path.

        A listing runs before a repository or a scope has been chosen, so only what the server
        needs to start is passed; the repository reader is built on demand and is not touched.
        """
        cfg = index.settings() or {}
        scope = {'repo':cfg.get('repo',''), 'branch':cfg.get('branch','main')}
        async with service.connector_factory(scope, demo) as source:
            return await getattr(source, method)(**kwargs)

    index = Index(db_path or data_dir()/('demo.sqlite3' if demo else 'index.sqlite3'))
    index.recover()
    if not index.settings():
        repo = 'demo/example-shop' if demo else os.getenv('GITHUB_REPOSITORY','') if _workspace_id == 1 else ''
        branch = 'main' if demo else os.getenv('GITHUB_BRANCH','main')
        if repo and repo != 'OWNER/REPOSITORY':
            try:
                repo, branch = validate_selection(repo,branch)
                index.configure({'repo':repo,'branch':branch})
            except ValueError:
                pass
    service = (Service(index,demo,connector_factory=connector_factory) if connector_factory
               else Service(index,demo))

    # Whether a project has been chosen in this run of the application.
    #
    # The selection and everything collected under it stay on disk between runs, and nothing
    # here deletes any of that. What changed is that a new run no longer adopts the last run's
    # project silently: starting up on a repository someone scanned days ago, with its name in
    # the sidebar and its scan behind every screen, reads as the application knowing something
    # about today when it does not. Typing the same repository back in costs one save and
    # reconnects to the snapshot already stored, because configure() only clears what it
    # collected when the repository or the branch actually changes.
    #
    # Example mode is exempt. It exists to be opened and looked at, and it has one fixed
    # fixture repository that it would be perverse to make anybody type.
    chosen = {'this_run': bool(demo)}
    children = {}
    @asynccontextmanager
    async def lifespan(app):
        yield
        for running in [service] + [item[0].state.service for item in children.values()]:
            if running.task and not running.task.done():
                running.cancel.set()
                running.task.cancel()
                try:
                    await running.task
                except asyncio.CancelledError:
                    pass
    app = FastAPI(title='Project Knowledge Assistant',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.service = service
    auth = auth_store or AuthStore(index.path)
    from pka.llm.store import Store as LLMStore
    service.llm.ledger = LLMStore(auth.path)
    from pka.llm.api import install as install_ai
    install_ai(app, service)
    app.state.auth = auth
    app.state.hosting = hosting
    auth_web.install(app, auth)
    if credential_store is None and db_path is None and not demo:
        from pka.vault import Vault
        credential_store = Vault(Path(index.path).with_suffix('.credentials.dpapi'))
        credential_store.migrate(credentials.ENV_PATH, credentials.writable())

    callbacks = {p['oauth']['redirect_path'] for p in registry.PLATFORMS if p.get('oauth')}

    async def local_only(request: Request, call_next):
        origin = request.headers.get('origin')
        if len(request.headers.getlist('host')) != 1 or not hosting.allows(str(request.base_url)):
            return JSONResponse({'detail':'Configured host and transport required.'},status_code=403)
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'Same-origin requests only.'},status_code=403)
        # An OAuth redirect comes back from the platform, so it is cross-site by nature and
        # cannot carry the application header. The single use state checked inside the handler
        # is what proves it belongs to a connect the user started here.
        returning = request.url.path in callbacks and request.method == 'GET'
        # These checks guard the data endpoints. They must not guard the page itself: arriving
        # back from a platform's approval screen is a cross-site navigation, and refusing it
        # left the user staring at an error instead of the application.
        if request.url.path.startswith('/api/') and not returning:
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail':'Cross-site requests refused.'},status_code=403)
            if request.headers.get('x-pka-request') != '1':
                return JSONResponse({'detail':'Application request header required.'},status_code=403)
        if request.method not in {'GET','HEAD'}:
            try:
                limit = zip_projects.MAX_UPLOAD_BYTES if request.url.path == '/api/zip/upload' and request.method == 'POST' else 8192
                if int(request.headers.get('content-length','0')) > limit:
                    return JSONResponse({'detail':'Request too large.'},status_code=413)
            except ValueError:
                return JSONResponse({'detail':'Invalid request size.'},status_code=400)
        protected = (request.url.path.startswith('/api/') and request.url.path not in auth_web.PUBLIC_API
                     or request.url.path == '/legacy')
        if protected:
            session = await run_in_threadpool(auth.session, auth_web.token(request, auth), auth_web.origin(request))
            if not session:
                if returning or request.url.path == '/legacy':
                    return RedirectResponse('/login', status_code=303)
                response = JSONResponse({'detail':'Sign in to continue.', 'code':'session_required'}, status_code=401)
                auth_web.clear_cookie(response, request, auth)
                return response
            request.state.owner = session
        result = await call_next(request)
        # A logout or password reset while a slow read runs must withhold that read's result.
        if protected and request.url.path.startswith('/api/') and not request.url.path.startswith('/api/auth/'):
            if not await run_in_threadpool(auth.session, auth_web.token(request, auth), auth_web.origin(request)):
                return JSONResponse({'detail':'Your session ended. Sign in again.', 'code':'session_required'}, status_code=401)
        return result

    async def security_headers(request: Request, call_next):
        result = await local_only(request, call_next)
        if request.url.path.startswith('/api/') and (
                request.method == 'POST' and request.url.path != '/api/auth/activity'
                or request.url.path.startswith('/api/connect/')):
            actor = getattr(request.state, 'audit_actor', None)
            if actor is None:
                actor = (getattr(request.state, 'owner', None) or {}).get('id')
            route = request.scope.get('route')
            await run_in_threadpool(auth.audit, 'api.' + (getattr(route, 'name', '') or 'denied'),
                                    actor, result.status_code, getattr(request.state, 'audit_target', None))
        result.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        result.headers['X-Content-Type-Options'] = 'nosniff'
        result.headers['Referrer-Policy'] = 'no-referrer'
        result.headers['Cache-Control'] = 'no-store'
        if request.url.scheme == 'https':
            result.headers['Strict-Transport-Security'] = 'max-age=86400'
        return result

    @app.middleware('http')
    async def monitored_request(request: Request, call_next):
        started, status = time.perf_counter(), 500
        with monitoring.request_scope(index.path):
            try:
                result = await security_headers(request, call_next)
                status = result.status_code
                return result
            finally:
                # Route names come from application code, never the URL/query/body.
                route = getattr(request.scope.get('route'), 'name', None) or 'unmatched_or_denied'
                actor = (getattr(request.state, 'owner', None) or {}).get('id')
                monitoring.event('http.completed', method=request.method, route=route,
                    http_status=status, actor_id=actor,
                    elapsed_seconds=round(time.perf_counter()-started, 3))

    @app.get('/healthz')
    async def health():
        # Reachability and local storage readiness only. No account, source,
        # job or model details are disclosed to an unauthenticated monitor.
        try:
            with index.db() as db:
                db.execute('SELECT revision FROM knowledge_state WHERE id=1').fetchone()
            with auth.db() as db:
                db.execute('SELECT count(*) FROM owner').fetchone()
        except Exception:
            return JSONResponse({'status': 'unavailable'}, status_code=503)
        return {'status': 'ok'}

    @app.exception_handler(SourceError)
    async def source_error(request, exc):
        applog.failure('api.source_error', path=request.url.path, code=exc.code, msg=exc)
        return JSONResponse({'detail':str(exc),'code':exc.code},status_code=409)

    def idle():
        if service.busy() or (service.task and not service.task.done()):
            raise HTTPException(409,'Another task is running. Wait for it to finish or cancel the current job.')

    # The built React interface, if it has been built. `npm run build` in frontend/ writes it.
    # The bundle is committed, so normal installs do not need Node. A missing login bundle
    # must not silently fall back to an interface with no account setup flow.
    UI = ROOT/'pka/static/ui/index.html'
    LEGACY = ROOT/'pka/static/index.html'

    @app.get('/')
    async def home():
        if not UI.exists():
            return JSONResponse({'detail':'Login interface is missing. Run npm ci and npm run build in frontend.'}, status_code=503)
        return FileResponse(UI)

    @app.get('/legacy')
    async def legacy():
        return FileResponse(LEGACY)

    @app.get('/api/status')
    async def status():
        service.sync_source_credentials()
        scan = service.progress or index.latest()
        if scan:
            scan = {k:v for k,v in scan.items() if k != 'files'}
        if not chosen['this_run']:
            # Nothing is reported until a project is picked, so no screen can quietly answer
            # from a snapshot this run never asked for. `stored_project` is the one thing that
            # leaks through, and it is a name for the Connections page to offer, not a
            # selection: until it is saved, nothing is read and nothing is answered.
            previous = index.settings() or {}
            return {'settings':None,'scan':None,'last_successful_scan':None,'ready':False,
                    'search_mode':service.search_mode(), 'semantic_available':embed.enabled() and not demo,
                    'knowledge_revision':index.revision,
                    'busy':False,'demo':demo,'limits':asdict(LIMITS),
                    'model':os.getenv('OLLAMA_MODEL','qwen3:1.7b'),
                    'token_configured':bool(credentials.getenv('GITHUB_TOKEN','')) and not demo,
                    'warning':'','job_error':'','job_name':'','job':None,
                    'jira_reading':False,'jira_progress':None,
                    'slack_reading':False,'slack_progress':None,
                    'overview_building':False,'overview_progress':None,
                    'awaiting_project':True,
                    'stored_project':{'project_name':project_name(previous), 'source_kind':selected_source(previous),
                                      **({'local_path':(previous.get('local') or {}).get('path') or previous.get('local_path') or previous.get('repo','')[6:]}
                                        if selected_source(previous) == 'local' else {}), 'repo':previous.get('repo',''),
                                      'branch':previous.get('branch','')} if previous.get('repo') else None}
        settings = index.settings()
        return {'settings':{**settings, 'project_name':project_name(settings), 'selected_source':selected_source(settings)} if settings else None,
                'search_mode':service.search_mode(), 'semantic_available':embed.enabled() and not demo,
                'scan':scan,'last_successful_scan':index.last_successful(),
                'knowledge_revision':index.revision,
                'busy':service.busy() or bool(service.task and not service.task.done()),'demo':demo,
                'limits':asdict(LIMITS),'model':os.getenv('OLLAMA_MODEL','qwen3:1.7b'),
                'token_configured':bool(credentials.getenv('GITHUB_TOKEN','')) and not demo,
                'warning':service.access_warning,'ready':index.active_scan() is not None,
                'job_error':service.job_error,'job_name':service.job_name,
                'job':service.job_status(),
                'jira_reading':service.jira_progress is not None,
                'jira_progress':service.jira_progress,
                'slack_reading':service.slack_progress is not None,
                'slack_progress':service.slack_progress,
                'overview_building':service.overview_progress is not None,
                'overview_progress':service.overview_progress}

    @app.get('/api/import-coverage')
    async def import_coverage():
        if not chosen['this_run']:
            return {'sources':{}}
        service.sync_source_credentials()
        return coverage.describe(service)

    @app.get('/api/scan-files')
    async def scan_files(offset: int = 0):
        if offset < 0:
            raise HTTPException(400,'Offset must be non-negative.')
        scan = service.progress or index.latest() or {}
        if index.active_scan():
            await service.check_external_access(index.active_scan(), names=('github',))
        files = scan.get('files',[])
        return {'files':files[offset:offset+100],'next_offset':offset+100 if len(files)>offset+100 else None}

    @app.post('/api/config')
    async def config(selection: Selection, request: Request):
        idle()
        if demo:
            raise HTTPException(409,'Example mode uses a fixed fixture repository. Restart without --demo for your repository.')
        if selection.source_kind == 'local' and request.state.owner['role'] != 'owner':
            raise HTTPException(403, 'Only the app owner can select folders from this computer.')
        try:
            repo, branch = (await run_in_threadpool(local_selection, selection.local_path)
                            if selection.source_kind == 'local' else validate_selection(selection.repo,selection.branch))
        except ValueError as exc:
            applog.warn('config.rejected', chars=len(selection.repo), reason=exc)
            raise HTTPException(422,str(exc)) from None
        try:
            platforms = registry.validate(selection.platforms or [selection.source_kind])
            if selection.source_kind == 'local':
                platforms = [p for p in platforms if p not in {'github', 'local'}] + ['local']
            elif 'local' in platforms:
                platforms = [p for p in platforms if p not in {'github', 'local'}] + ['github']
        except ValueError as exc:
            applog.warn('config.rejected', reason=exc)
            raise HTTPException(422,str(exc)) from None
        applog.event('config.saved', repo=repo, branch=branch, platforms=','.join(platforms),
                     typed_chars=len(selection.repo))
        async with service.lock:
            previous = index.settings() or {}
            # Combining projects must be explicit. A normal folder selection starts
            # its own project instead of renaming an old GitHub snapshot.
            if selection.add_to_project:
                if (selection.source_kind != 'local' or not chosen['this_run']
                        or not previous.get('repo') or is_local(previous['repo'])
                        or not index.active_scan()):
                    raise HTTPException(409, 'Read a GitHub project first before adding a folder to it.')
                index.configure_source('local', {'repo':repo, 'path':repo[6:]})
                index.configure({'platforms':list(dict.fromkeys([*(previous.get('platforms') or []), 'local'])),
                                 'project_name':project_name({'repo':previous['repo']}), 'selected_source':'github'})
                chosen['this_run'] = True
                return {'ok':True, 'additional_local':True, 'reconnected':False}
            changed = (previous.get('repo'), previous.get('branch')) != (repo, branch)
            if previous.get('repo') != repo:
                platforms = [selection.source_kind]
            elif previous.get('local') and 'local' not in platforms:
                platforms.append('local')
            label = project_name({'repo':repo})
            index.configure({'repo':repo,'branch':branch,'platforms':platforms,'project_name':label,
                'source_kind':selection.source_kind, 'selected_source':selection.source_kind,
                'local_path':repo[6:] if is_local(repo) else '', 'archive':None})
            service.access_warning = ''
            if changed:
                service.job = None
                service.job_error = service.job_name = ''
            chosen['this_run'] = True
            if is_local(repo) and index.active_scan():
                try:
                    await service.check_external_access(index.active_scan(), names=('github',))
                except SourceError as exc:
                    if exc.code != 'stale':
                        raise
        # Saying whether this reconnected to a stored snapshot or starts empty, because the
        # difference decides whether the next thing to do is ask a question or run a scan.
        return {'ok':True,'reconnected':index.active_scan() is not None}

    @app.post('/api/zip/upload')
    async def upload_zip(request: Request, filename: str = Query(max_length=200)):
        idle()
        if demo:
            raise HTTPException(409, 'Restart without --demo to upload a project ZIP.')
        if request.headers.get('content-type', '').split(';')[0] not in {'application/zip', 'application/octet-stream'}:
            raise HTTPException(415, 'Upload the project ZIP file as binary content.')
        prepared = None
        async with service.lock:
            try:
                with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as stream:
                    size = 0
                    async for block in request.stream():
                        size += len(block)
                        if size > zip_projects.MAX_UPLOAD_BYTES:
                            raise HTTPException(413, 'ZIP uploads must be 25 MB or smaller.')
                        await run_in_threadpool(stream.write, block)
                    stream.seek(0)
                    prepared = await run_in_threadpool(zip_projects.prepare, stream, filename, index.path)
                if not await run_in_threadpool(auth.session, auth_web.token(request, auth), auth_web.origin(request)):
                    raise HTTPException(401, 'Your session ended. Sign in again before uploading.')
                previous = index.settings() or {}
                index.configure({'repo':prepared['repo'], 'branch':'uploaded-snapshot',
                    'source_kind':'zip', 'selected_source':'zip', 'project_name':filename[:-4],
                    'platforms':['local'], 'local_path':'', 'local':{},
                    'archive':{k:v for k,v in prepared.items() if k not in {'repo', 'root'}}})
                chosen['this_run'] = True
                service.access_warning = ''
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            finally:
                if prepared and (index.settings() or {}).get('repo') != prepared['repo']:
                    await run_in_threadpool(zip_projects.discard, index.path, prepared['root'])
        job_id = service.start_job('scan')
        # Replacing a ZIP releases its previous managed snapshot after the new one is selected.
        if previous.get('repo', '').startswith('zip:'):
            try:
                await run_in_threadpool(zip_projects.discard, index.path, Path(previous['repo'][4:]).parent)
            except (ValueError, OSError):
                pass
        return {'ok':True, 'job_id':job_id, 'project_name':filename[:-4], 'archive':index.settings()['archive']}

    @app.post('/api/zip/resume')
    async def resume_zip():
        idle()
        saved = index.settings() or {}
        if not saved.get('repo', '').startswith('zip:'):
            raise HTTPException(409, 'No saved ZIP project. Upload a project ZIP first.')
        folder = Path(saved['repo'][4:])
        if not folder.is_dir() or folder.resolve().parent.parent != zip_projects.storage(index.path):
            raise HTTPException(409, 'The saved ZIP files are unavailable. Upload the ZIP again.')
        chosen['this_run'] = True
        if index.active_scan():
            await service.check_external_access(index.active_scan(), names=('github',))
            return {'ok':True, 'reconnected':True}
        return {'ok':True, 'job_id':service.start_job('scan'), 'reconnected':False}

    @app.get('/api/local-source')
    async def local_source(request: Request, path: str = Query(max_length=1000), snapshot: str = Query(max_length=64)):
        zip_source = (index.settings() or {}).get('repo', '').startswith('zip:') and not path.startswith('local://')
        if request.state.owner['role'] != 'owner' and not zip_source:
            raise HTTPException(403, 'Local source files are available only to the app owner.')
        scan = index.active_scan() if chosen['this_run'] else None
        saved = index.source_import('local')
        primary = scan and is_local(scan['repo']) and scan['commit'] == snapshot and not path.startswith('local://')
        additional = scan and saved and saved.get('snapshot') == snapshot and path.startswith('local://'+snapshot+'/')
        if not (primary or additional):
            raise HTTPException(409, 'This local snapshot is no longer selected. Open a citation from the current overview or answer.')
        checked = await service.check_external_access(scan, names=('github',))
        if path not in index.code_paths(scan['id']):
            raise HTTPException(404, 'This file was not indexed in the selected folder.')
        lines = index.file_lines(scan['id'], path)
        service.ensure_current(checked)
        return {'path':path.split('/', 3)[-1] if additional else path, 'snapshot':snapshot, 'source_kind':'zip' if zip_source else 'local', 'lines':[{'number':n, 'text':text} for n, text in lines],
                'note':'Saved indexed lines. Blank lines and content not indexed may be absent.'}

    @app.post('/api/local/read')
    async def read_local(request: Request):
        if request.state.owner['role'] != 'owner':
            raise HTTPException(403, 'Only the app owner can read local folders.')
        idle()
        if not chosen['this_run']:
            raise HTTPException(409, 'Choose your saved project first.')
        return {'started':True, 'job_id':service.start_job('local')}

    @app.post('/api/scan')
    async def scan():
        idle()
        if not index.settings():
            raise HTTPException(409,'Save a repository and branch first.')
        return {'started':True, 'job_id':service.start_job('scan')}

    @app.post('/api/scan/cancel')
    async def cancel():
        # Compatibility for the original interface; all new controls bind to a specific job ID.
        job = service.job_status()
        if not job or job['kind'] != 'scan':
            raise HTTPException(409, 'No repository scan is running.')
        return service.cancel_job(job['id'])

    @app.post('/api/search-mode')
    async def search_mode(selection: SearchMode):
        idle()
        service.set_search_mode(selection.mode)
        return {'ok':True, 'search_mode':service.search_mode()}

    @app.post('/api/jobs/{job_id}/basic-search')
    async def basic_search(job_id: int):
        return service.use_basic_search(job_id)

    @app.post('/api/jobs/{job_id}/cancel')
    async def cancel_job(job_id: int):
        return service.cancel_job(job_id)

    @app.post('/api/jobs/{job_id}/retry')
    async def retry_job(job_id: int):
        job = service.job_status()
        if not job or job['id'] != job_id:
            raise HTTPException(409, 'This is no longer the current job. Refresh its status.')
        return {'started':True, 'job_id':service.start_job(job['kind'], retry_id=job_id)}

    def _scope(key, cfg, scan):
        """What this platform is actually set to read, in the reader's own words."""
        if key == 'local' and (cfg.get('local') or {}).get('repo'):
            return cfg['local']['path']
        if key in {'github', 'local'}:
            if (key == 'local') != is_local(cfg.get('repo')):
                return ''
            repo = cfg.get('repo')
            if not repo:
                return ''
            branch = cfg.get('branch') or 'main'
            files = (scan or {}).get('read')
            return f"{repo} ({branch})" + (f", {files} files read" if files else '')
        if key == 'jira':
            return (cfg.get('jira') or {}).get('project', '')
        if key == 'slack_user':
            names = [c['name'] for c in (cfg.get('slack') or {}).get('channels', [])]
            if not names:
                return ''
            return ', '.join('#' + n for n in names[:3]) + ('' if len(names) <= 3 else f' and {len(names)-3} more')
        return ''

    def _readiness(row, cfg, scan):
        """Whether this platform is finished, and what is still missing if it is not.

        Credentials alone are not a connection. A platform is only finished when it also has the
        one thing it is allowed to read: a repository, a project key, a list of channels.
        """
        key = row['key']
        if row['status'] != registry.AVAILABLE:
            return False, 'Reading is not built for this platform yet.'
        if key == 'local' and (cfg.get('local') or {}).get('repo'):
            return (True, '') if scan and index.source_import('local') else (False, 'Read the local folder.')
        if key in {'github', 'local'}:
            if (key == 'local') != is_local(cfg.get('repo')):
                return False, 'Choose this source in Connections.'
            if not cfg.get('repo'):
                return False, 'Choose a repository and branch.'
            if not scan:
                return False, 'Scan the repository.'
            return True, ''
        # Its own setup comes first, because that is what the reader can act on here. Only once
        # that is done does the missing index become the thing in the way.
        if key == 'jira':
            if not row['credentials_present']:
                return False, 'Add the site address, email and API token.'
            if not (cfg.get('jira') or {}).get('project'):
                return False, 'Choose a project to read.'
            if not scan:
                return False, 'Scan a GitHub repository or local folder before adding issues.'
            return True, ''
        if key == 'slack_user':
            if not row.get('connected'):
                return False, 'Add the client id and secret, then press Connect.'
            if not (cfg.get('slack') or {}).get('channels'):
                return False, 'Choose the channels to read.'
            if not scan:
                return False, 'Scan a GitHub repository or local folder before adding messages.'
            return True, ''
        return bool(row['credentials_present']), 'Add the credentials for this platform.'

    @app.get('/api/platforms')
    async def platforms(request: Request):
        credentials.refresh()   # before describing, so an edit in the file is reflected at once
        cfg = index.settings() or {}
        rows = registry.describe(cfg.get('platforms') or [])
        # Show the exact address this browser will send, so it can be registered without guessing.
        base = str(request.base_url).rstrip('/')
        scan = index.active_scan()
        for row in rows:
            if row.get('oauth'):
                row['redirect_uri'] = base + registry.BY_KEY[row['key']]['oauth']['redirect_path']
            row['ready'], row['pending'] = _readiness(row, cfg, scan)
            row['scope'] = _scope(row['key'], cfg, scan)
        if request.state.owner['role'] != 'owner':
            rows = [row for row in rows if row['key'] != 'local']
        return {'platforms':rows,
                'credentials':credentials.status(),
                'note':'Selecting a platform records that this project uses it. It never grants access. '
                       'Access uses your account’s source credentials and the scope you select.'}

    @app.get('/api/connect/{platform}')
    async def connect(platform: str, request: Request):
        if demo:
            raise HTTPException(409,'Example mode does not connect to anything.')
        credentials.refresh()   # pick up an edit made in the file since startup
        if request.url.hostname != 'localhost':
            raise HTTPException(409, 'Slack browser approval requires localhost. Open http://localhost:'
                                + str(request.url.port or 80) + '/connections and sign in there first.')
        url = oauth.begin(platform, str(request.base_url), credentials.getenv,
                          session_id=digest(auth_web.token(request, auth)))
        applog.event('oauth.begin', platform=platform)
        return {'url':url}

    @app.get('/api/slack/callback')
    async def slack_callback(request: Request, code: str = '', state: str = '', error: str = ''):
        if error:
            applog.warn('oauth.refused', platform='slack_user', reason=error)
            return RedirectResponse('/?connect=refused', status_code=303)
        if not code or not state:
            return RedirectResponse('/?connect=incomplete', status_code=303)
        try:
            credentials.refresh()
            platform, name, token, granted = await oauth.complete(state, code, credentials.getenv,
                session_id=digest(auth_web.token(request, auth)))
            if not auth.session(auth_web.token(request, auth), auth_web.origin(request)):
                return RedirectResponse('/login', status_code=303)
            credentials.save({name:token})
        except SourceError as exc:
            applog.failure('oauth.failed', platform='slack_user', msg=exc)
            reason = str(exc).rsplit(': ',1)[-1].strip('. ')[:60]
            return RedirectResponse('/?connect=failed&reason='+quote(reason), status_code=303)
        # names and granted scopes only; the token itself must never reach a log
        applog.event('oauth.connected', platform=platform, stored=name, scopes=granted)
        return RedirectResponse('/?connect=ok', status_code=303)

    @app.post('/api/credentials')
    async def set_credentials(request: Request):
        idle()
        if demo:
            raise HTTPException(409,'Example mode does not connect to anything.')
        data = await auth_web.json_body(request)
        values = data.get('values') if isinstance(data, dict) and set(data) == {'values'} else None
        if (not isinstance(values, dict) or len(values) > 10 or
                any(not isinstance(v, str) for v in values.values())):
            raise HTTPException(422, 'Enter valid credential fields.')
        try:
            saved = credentials.save(values)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from None
        # Names only. A credential value must never reach a log.
        listings.clear()   # new credentials may see a different set of channels or projects
        service.sync_source_credentials()
        applog.event('credentials.saved', names=','.join(saved) or 'none')
        return {'saved':saved,'status':credentials.status()}

    @app.get('/api/slack/channels')
    async def slack_channels():
        credentials.refresh()
        token = credentials.getenv('SLACK_USER_TOKEN','')
        if not token:
            return {'connected':False,'channels':[],'chosen':[],'workspace':'',
                    'reason':'Connect Slack first.'}
        cfg = index.settings() or {}
        saved = cfg.get('slack') or {}
        found = cached('slack')
        if found is None:
            try:
                found = remember('slack', await via_connector('slack_channels'))
            except SourceError as exc:
                return {'connected':True,'channels':[],'chosen':saved.get('channels',[]),
                        'workspace':saved.get('workspace',''),'reason':str(exc)}
        chosen = {c['id'] for c in saved.get('channels',[])}
        for channel in found:
            channel['chosen'] = channel['id'] in chosen
        return {'connected':True,'channels':found,'chosen':saved.get('channels',[]),
                'workspace':saved.get('workspace',''),'reason':'',
                'read_at':saved.get('read_at',''),'blocks':index.slack_blocks((index.active_scan() or {}).get('id',0)),
                'limits':{'channels':LIMITS.slack_max_channels,'messages':LIMITS.slack_max_messages}}

    @app.post('/api/slack/channels')
    async def save_slack_choice(choice: SlackChoice):
        idle()
        cfg = index.settings()
        if not cfg:
            raise HTTPException(409,'Save a repository first.')
        clean = []
        for channel in choice.channels[:LIMITS.slack_max_channels]:
            cid, name = str(channel.get('id',''))[:30], str(channel.get('name',''))[:80]
            if not re.fullmatch(r'[A-Z0-9]+', cid) or not name:
                raise HTTPException(422,'That channel could not be recognised.')
            clean.append({'id':cid,'name':name})
        workspace = choice.workspace.strip().lower()
        if workspace and not re.fullmatch(r'[a-z0-9-]{1,100}', workspace):
            raise HTTPException(422,'The workspace name may only contain letters, numbers and hyphens.')
        slack = {**(cfg.get('slack') or {}),'channels':clean,'workspace':workspace}
        index.configure_slack(slack)
        applog.event('slack.selection', channels=','.join(c['name'] for c in clean) or 'none')
        return {'saved':len(clean)}

    @app.post('/api/slack/read')
    async def read_slack():
        idle()
        credentials.refresh()
        token = credentials.getenv('SLACK_USER_TOKEN','')
        if not token:
            raise HTTPException(409,'Connect Slack first.')
        cfg = index.settings() or {}
        saved = cfg.get('slack') or {}
        # The token is not passed on. It is handed to the MCP server at launch instead.
        return {'started':True, 'job_id':service.start_job('slack'), 'channels':len(saved.get('channels',[]))}

    @app.get('/api/decisions/channels')
    async def decision_channels():
        if not chosen['this_run']:
            return {'channels':[], 'reason':'Choose a project in Connections first.', 'awaiting_project':True}
        return await service.decision_channel_list()

    @app.get('/api/decisions/channels/{channel_id}')
    async def decision_detail(channel_id: str):
        if not chosen['this_run']:
            raise HTTPException(409, 'Choose a project in Connections first.')
        return await service.decision_detail(channel_id)

    @app.post('/api/decisions/channels/{channel_id}/summarize')
    async def summarize_decisions(channel_id: str):
        if not chosen['this_run']:
            raise HTTPException(409, 'Choose a project in Connections first.')
        idle()
        return {'started':True, 'job_id':service.start_job('decisions', target=channel_id)}

    def jira_credentials():
        credentials.refresh()
        return (credentials.getenv('JIRA_SITE',''), credentials.getenv('JIRA_EMAIL',''), credentials.getenv('JIRA_API_TOKEN',''))

    @app.get('/api/jira/projects')
    async def jira_projects():
        site, email, token = jira_credentials()
        cfg = index.settings() or {}
        saved = (cfg.get('jira') or {}).get('project','')
        if not (site and email and token):
            return {'connected':False,'projects':[],'chosen':saved,
                    'reason':'Add the Jira site, email and API token first.'}
        found = cached('jira')
        if found is None:
            try:
                found = remember('jira', await via_connector('jira_projects'))
            except SourceError as exc:
                return {'connected':True,'projects':[],'chosen':saved,'reason':str(exc)}
        return {'connected':True,'projects':found,'chosen':saved,'reason':'',
                'read_at':(cfg.get('jira') or {}).get('read_at',''),
                'blocks':index.source_blocks((index.active_scan() or {}).get('id',0),'jira/')}

    @app.get('/api/jira/tasks')
    async def jira_tasks():
        if not chosen['this_run']:
            return {'issues':[], 'reason':'Choose a project in Connections first.', 'awaiting_project':True}
        return await service.jira_task_list()

    @app.get('/api/jira/tasks/{issue_key}')
    async def jira_task(issue_key: str):
        if not chosen['this_run']:
            raise HTTPException(409, 'Choose a project in Connections first.')
        return await service.jira_task_detail(issue_key)

    @app.post('/api/jira/tasks/{issue_key}/explain')
    async def explain_jira_task(issue_key: str):
        if not chosen['this_run']:
            raise HTTPException(409, 'Choose a project in Connections first.')
        idle()
        return {'started':True, 'job_id':service.start_job('jira_task', target=issue_key)}

    @app.get('/api/jira/tasks/{issue_key}/links')
    async def jira_task_links(issue_key: str, kind: Literal['files', 'discussions'] = 'files',
                              offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=25)):
        if not chosen['this_run']:
            raise HTTPException(409, 'Choose a project in Connections first.')
        return await service.jira_task_links(issue_key, kind, offset, limit)

    @app.post('/api/jira/project')
    async def save_jira_project(choice: JiraChoice):
        idle()
        cfg = index.settings()
        if not cfg:
            raise HTTPException(409,'Save a repository first.')
        key = choice.project.strip()
        if key and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,40}', key):
            raise HTTPException(422,'That project key could not be recognised.')
        index.configure_source('jira',{**(cfg.get('jira') or {}),'project':key})
        applog.event('jira.selection', project=key or 'none')
        return {'saved':key}

    @app.post('/api/jira/read')
    async def read_jira():
        idle()
        site, email, token = jira_credentials()
        if not (site and email and token):
            raise HTTPException(409,'Add the Jira site, email and API token first.')
        cfg = index.settings() or {}
        key = (cfg.get('jira') or {}).get('project','')
        if not key:
            raise HTTPException(409,'Choose a Jira project first.')
        # Only the key travels. The site, email and token go to the MCP server at launch.
        return {'started':True, 'job_id':service.start_job('jira'), 'project':key}

    @app.get('/api/overview')
    async def overview():
        scan = index.active_scan()
        if not scan:
            return {'available':False,'reason':'Run a successful scan first.'}
        selection = selected_local(index, scan)
        checked = await service.check_external_access(scan, names=() if selection else ('github', 'jira', 'slack'))
        service.ensure_current(checked)
        cached = index.overview(scan['commit'])
        if selection:
            valid = cached and cached.get('overview_scope') == selection['id']
            cached = await asyncio.to_thread(current_local_payload, index, scan, selection, cached if valid else None)
            service.ensure_current(checked)
        elif cached and cached.get('overview_scope', 'workspace') != 'workspace':
            cached = None
        if cached:
            # The reading order is derived from the indexed paths and no model touches it, so
            # there is no reason for a reader to be shown an old one. It was cached inside a
            # payload that only a model rebuild replaces, which meant a correction to it could
            # not reach anybody without paying for that rebuild: after a fix stopped Jira issues
            # being offered as files to read, the stale list kept offering them. Derived at the
            # moment it is asked for instead, which is one query and a sort.
            cached = {**cached,
                      'plain_language_update_available':cached.get('explanation_style') != STYLE_VERSION,
                      'routing_changed':bool(cached.get('routing_signature') and cached['routing_signature'] != service.llm.cache_signature()),
                      'reading_order':reading_order(selection['paths'] if selection else index.code_paths(scan['id']),
                                                    repo='' if demo else scan['repo'],
                                                    commit='' if demo else scan['commit'])}
        return {'available':bool(cached),'building':service.overview_progress is not None,
                'progress':service.overview_progress,'overview':cached,
                'reason':'' if cached else 'No overview has been built for the current information yet.'}

    @app.post('/api/overview')
    async def build_overview():
        idle()
        if not index.active_scan():
            raise HTTPException(409,'Run a successful scan before building the overview.')
        scan = index.active_scan()
        selection = selected_local(index, scan)
        if selection and not selection['paths']:
            raise HTTPException(409, 'Read the selected local folder before building its overview.')
        present = set() if selection else {p for p in ('slack/','jira/') if index.source_blocks(scan['id'],p)}
        return {'started':True, 'job_id':service.start_job('overview'), 'topics':len(topics_for(present))}

    @app.post('/api/ask')
    async def ask(question: Question):
        idle()
        if not question.question.strip():
            raise HTTPException(422,'Enter a question.')
        return await service.ask(question.question.strip(), conversation=question.conversation)

    def quality_selected():
        if not chosen['this_run']:
            raise HTTPException(409, 'Choose your project on Connections first.')

    @app.get('/api/quality')
    async def quality_list():
        quality_selected()
        service.sync_source_credentials()
        return {'sets': quality.catalog(service), 'runs': quality.runs(index)}

    @app.post('/api/quality/runs')
    async def quality_start(item: EvaluationStart):
        quality_selected()
        return {'started': True, 'job_id': service.start_job('evaluation', target=item.set_id)}

    @app.post('/api/quality/compare')
    async def quality_compare(item: EvaluationCompare):
        quality_selected()
        return await quality.compare(service,item.left,item.right)

    @app.get('/api/quality/runs/{run_id}/cases/{case_id}')
    async def quality_case(run_id: int, case_id: str):
        quality_selected()
        return await quality.inspect(service, run_id, case_id)

    @app.post('/api/quality/runs/{run_id}/cases/{case_id}/review')
    async def quality_review(run_id: int, case_id: str, item: EvaluationReview, request: Request):
        quality_selected()
        return await quality.review(service, run_id, case_id, item, request.state.owner['username'])

    # A scan writes one plain-text report per run to data/logs. They were only readable by
    # opening the folder, so a run that went wrong left nothing visible in the application.
    LOG_NAME = re.compile(r'scan-(\d{4})-([a-z]+)-(.+)\.log')

    def read_header(path):
        """The key/value block write_scan_log puts at the top of every report."""
        header = {}
        try:
            with path.open(encoding='utf-8') as handle:
                for line in handle:
                    if not line.strip():
                        break
                    parts = line.rstrip('\n').split('   ',1)
                    if len(parts) == 2:
                        header[parts[0].strip()] = parts[1].strip()
        except OSError:
            return {}
        return header

    @app.get('/api/import-history')
    async def import_history():
        runs = []
        for path in sorted(log_dir().glob('scan-*.log'), reverse=True):
            found = LOG_NAME.fullmatch(path.name)
            if not found:
                continue
            header = read_header(path)
            runs.append({'file':path.name,'scan_id':int(found.group(1)),'status':found.group(2),
                         'repo':header.get('repository',''),'branch':header.get('branch',''),
                         'commit':header.get('commit',''),'started':header.get('started',''),
                         'finished':header.get('finished',''),
                         'read':header.get('files read',''),'skipped':header.get('skipped',''),
                         'failed':header.get('failed',''),'error':header.get('error','')})
        cfg = index.settings() or {}
        return {'runs':runs,'kept':KEEP_LOGS,
                'slack_read_at':(cfg.get('slack') or {}).get('read_at',''),
                'jira_read_at':(cfg.get('jira') or {}).get('read_at',''),
                'note':'Only repository scans write a report. Slack and Jira reads record the time '
                       'they last ran, not a per-run report.'}

    @app.get('/api/import-history/{name}')
    async def import_log(name: str):
        # The name must be one this application wrote. Anything else never becomes a path.
        if not LOG_NAME.fullmatch(name):
            raise HTTPException(404,'No such import report.')
        path = log_dir()/name
        if not path.is_file():
            raise HTTPException(404,'No such import report.')
        return {'name':name,'text':path.read_text(encoding='utf-8')[:200_000]}

    @app.get('/api/existing-tests')
    async def existing_test_definitions():
        if not chosen['this_run']:
            return {'available': False, 'reason': 'Choose a project in Connections first.', 'files': []}
        scan = index.active_scan()
        if not scan:
            return {'available': False, 'reason': 'Run a successful scan first.', 'files': []}
        checked = await service.check_external_access(scan)
        payload = await run_in_threadpool(existing_tests.derive, index, scan)
        service.ensure_current(checked)
        return payload

    def feature_read_pending():
        job = service.job_status() or {}
        return (job.get('kind') in {'scan', 'local', 'jira', 'slack'}
                and job.get('state') in {'queued', 'running', 'cancelling'}) or any(
                    progress is not None for progress in (service.progress, service.local_progress,
                                                         service.jira_progress, service.slack_progress))

    async def current_features():
        if not chosen['this_run']:
            return None, None, 'Choose a project in Connections first.'
        if feature_read_pending():
            return None, None, 'Reading project files. Features will appear after the read finishes.'
        scan = index.active_scan()
        if not scan:
            return None, None, 'Run a successful scan first.'
        checked = await service.check_external_access(scan)
        service.ensure_current(checked)
        # A project change or queued refresh may happen while access is checked.
        active = index.active_scan()
        if feature_read_pending() or not active or active['id'] != scan['id']:
            raise SourceError('stale', 'Project files changed while loading features. Refresh features.')
        payload = features.derive(index, scan, facts.derive(index, scan))
        service.ensure_current(checked)
        scope = {'repo':scan['repo'], 'branch':scan['branch'], 'scan_id':scan['id'],
                 'commit':scan['commit'], 'knowledge_revision':checked[0]}
        return payload, scope, ''

    @app.get('/api/features')
    async def feature_list():
        payload, scope, reason = await current_features()
        if payload is None:
            return {'available':False, 'reason':reason, 'features':[]}
        return {'available':True,'reason':'',**features.listing(payload), **scope}

    @app.get('/api/architecture')
    async def current_architecture():
        if not chosen['this_run']:
            return {'available':False, 'architecture':None, 'reason':'Choose a project in Connections first.'}
        if feature_read_pending():
            return {'available':False, 'architecture':None, 'reason':'Reading project files. Architecture will appear after the read finishes.'}
        scan = index.active_scan()
        if not scan:
            return {'available':False, 'architecture':None, 'reason':'Read this project’s files to build its architecture.'}
        checked = await service.check_external_access(scan)
        service.ensure_current(checked)
        payload = await asyncio.to_thread(architecture.derive, index, scan)
        service.ensure_current(checked)
        active = index.active_scan()
        if feature_read_pending() or not active or active['id'] != scan['id']:
            raise SourceError('stale', 'Project files changed while drawing the architecture. Refresh architecture.')
        return {'available':True, 'reason':'', 'architecture':{
            **payload, 'repo':scan['repo'], 'branch':scan.get('branch'), 'scan_id':scan['id'],
            'commit':scan['commit'], 'knowledge_revision':checked[0]}}

    @app.get('/api/features/{feature_id}')
    async def feature_detail(feature_id: str):
        payload, scope, reason = await current_features()
        if payload is None:
            raise HTTPException(409, reason)
        found = next((f for f in payload['features'] if f['id'] == feature_id),None)
        if not found:
            raise HTTPException(404,'No feature by that name was derived from this scan.')
        return {**features.detail(found), **scope, 'walkthrough_sections': [
            {'key':item['key'], 'title':item['title']} for item in feature_kt.SECTIONS]}

    @app.post('/api/features/{feature_id}/walkthrough/{section_key}')
    async def feature_walkthrough(feature_id: str, section_key: str):
        idle()
        if not chosen['this_run']:
            raise HTTPException(409, 'Choose your saved project first.')
        return await feature_kt.build(service, feature_id, section_key)

    @app.post('/api/feedback')
    async def feedback(item: Feedback):
        if not index.feedback(item.answer_id,item.rating,item.sufficiency):
            raise HTTPException(404,'This answer is no longer current. Ask again after the latest scan.')
        return {'saved':True}

    app.mount('/static',StaticFiles(directory=ROOT/'pka/static'),name='static')

    # The interface routes in the browser, so reloading on /connections asks this server for a
    # path it has no handler for. Hand back the same page and let the router read the address.
    # Registered last, so every real route above still wins, and it never answers /api or /static.
    @app.get('/{path:path}')
    async def ui_route(path: str):
        if path.startswith(('api/','static/')) or not UI.exists():
            raise HTTPException(404,'Not found.')
        return FileResponse(UI)

    if _workspace_id == 1:
        from pka.workspaces import WorkspaceDispatch
        app.state.workspaces = children
        def member_app(path, vault):
            return create_app(demo, path, connector_factory, auth_store=auth,
                              credential_store=vault, _workspace_id=2, hosting=hosting)
        app.add_middleware(WorkspaceDispatch, store=auth, root_path=index.path,
                           owner_vault=credential_store, children=children, factory=member_app)
    return app
