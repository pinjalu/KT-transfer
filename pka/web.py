import asyncio
from contextlib import asynccontextmanager
import time
from dataclasses import asdict
import os
import re
from typing import Literal
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from pka import applog
from pka.config import ROOT, LIMITS, data_dir, validate_selection
from pka import credentials, oauth
from pka.connectors import registry
from pka.connectors.base import SourceError
from pka.connectors.jira import JiraSource
from pka.connectors.slack import SlackSource
from pka.index import Index
from pka.overview import TOPICS
from pka.service import Service

class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    repo: str = Field(max_length=400)  # a pasted repository address is longer than owner/repository
    branch: str = Field(max_length=200)
    platforms: list[str] = Field(default_factory=list, max_length=20)
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
    question: str = Field(min_length=3,max_length=600)
class Feedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer_id: int
    rating: Literal['correct','partially correct','incorrect','not assessed']
    sufficiency: Literal['sufficient','partly sufficient','insufficient','not assessed']


def create_app(demo=False, db_path=None):
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

    index = Index(db_path or data_dir()/('demo.sqlite3' if demo else 'index.sqlite3'))
    index.recover()
    if not index.settings():
        repo = 'demo/example-shop' if demo else os.getenv('GITHUB_REPOSITORY','')
        branch = 'main' if demo else os.getenv('GITHUB_BRANCH','main')
        if repo and repo != 'OWNER/REPOSITORY':
            try:
                repo, branch = validate_selection(repo,branch)
                index.configure({'repo':repo,'branch':branch})
            except ValueError:
                pass
    service = Service(index,demo)
    @asynccontextmanager
    async def lifespan(app):
        yield
        if service.task and not service.task.done():
            service.cancel.set()
            service.task.cancel()
            try:
                await service.task
            except asyncio.CancelledError:
                pass
    app = FastAPI(title='Project Knowledge Assistant',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.service = service

    callbacks = {p['oauth']['redirect_path'] for p in registry.PLATFORMS if p.get('oauth')}

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        host = request.headers.get('host','').split(':')[0].lower()
        origin = request.headers.get('origin')
        if host not in {'localhost','127.0.0.1'}:
            return JSONResponse({'detail':'Local host required.'},status_code=403)
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
                if int(request.headers.get('content-length','0')) > 8192:
                    return JSONResponse({'detail':'Request too large.'},status_code=413)
            except ValueError:
                return JSONResponse({'detail':'Invalid request size.'},status_code=400)
        result = await call_next(request)
        result.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        result.headers['X-Content-Type-Options'] = 'nosniff'
        result.headers['Referrer-Policy'] = 'no-referrer'
        result.headers['Cache-Control'] = 'no-store'
        return result

    @app.exception_handler(SourceError)
    async def source_error(request, exc):
        applog.failure('api.source_error', path=request.url.path, code=exc.code, msg=exc)
        return JSONResponse({'detail':str(exc),'code':exc.code},status_code=409)

    def idle():
        if service.busy() or (service.task and not service.task.done()):
            raise HTTPException(409,'Another scan or answer is in progress. Wait or cancel the scan.')

    @app.get('/')
    async def home():
        return FileResponse(ROOT/'pka/static/index.html')

    @app.get('/api/status')
    async def status():
        scan = service.progress or index.latest()
        if scan:
            scan = {k:v for k,v in scan.items() if k != 'files'}
        return {'settings':index.settings(),'scan':scan,'last_successful_scan':index.last_successful(),
                'busy':service.busy() or bool(service.task and not service.task.done()),'demo':demo,
                'limits':asdict(LIMITS),'model':os.getenv('OLLAMA_MODEL','qwen3:1.7b'),
                'token_configured':bool(os.getenv('GITHUB_TOKEN','')) and not demo,
                'warning':service.access_warning,'ready':index.active_scan() is not None,
                'jira_reading':service.jira_progress is not None,
                'jira_progress':service.jira_progress,
                'slack_reading':service.slack_progress is not None,
                'slack_progress':service.slack_progress,
                'overview_building':service.overview_progress is not None,
                'overview_progress':service.overview_progress}

    @app.get('/api/scan-files')
    async def scan_files(offset: int = 0):
        if offset < 0:
            raise HTTPException(400,'Offset must be non-negative.')
        scan = service.progress or index.latest() or {}
        files = scan.get('files',[])
        return {'files':files[offset:offset+100],'next_offset':offset+100 if len(files)>offset+100 else None}

    @app.post('/api/config')
    async def config(selection: Selection):
        idle()
        if demo:
            raise HTTPException(409,'Example mode uses a fixed fixture repository. Restart without --demo for your repository.')
        try:
            repo, branch = validate_selection(selection.repo,selection.branch)
        except ValueError as exc:
            applog.warn('config.rejected', chars=len(selection.repo), reason=exc)
            raise HTTPException(422,str(exc)) from None
        try:
            platforms = registry.validate(selection.platforms or ['github'])
        except ValueError as exc:
            applog.warn('config.rejected', reason=exc)
            raise HTTPException(422,str(exc)) from None
        if 'github' not in platforms:
            platforms = ['github'] + platforms   # the repository scan is what the index is built from
        applog.event('config.saved', repo=repo, branch=branch, platforms=','.join(platforms),
                     typed_chars=len(selection.repo))
        async with service.lock:
            index.configure({'repo':repo,'branch':branch,'platforms':platforms})
            service.access_warning = ''
        return {'ok':True}

    @app.post('/api/scan')
    async def scan():
        idle()
        if not index.settings():
            raise HTTPException(409,'Save a repository and branch first.')
        service.task = asyncio.create_task(service.scan())
        return {'started':True}

    @app.post('/api/scan/cancel')
    async def cancel():
        service.cancel.set()
        return {'requested':True,'message':'Cancellation takes effect after the current GitHub request finishes.'}

    def _scope(key, cfg, scan):
        """What this platform is actually set to read, in the reader's own words."""
        if key == 'github':
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
        if key == 'github':
            if not cfg.get('repo'):
                return False, 'Choose a repository and branch.'
            if not scan:
                return False, 'Scan the repository.'
            return True, ''
        if key == 'jira':
            if not row['credentials_present']:
                return False, 'Add the site address, email and API token.'
            if not (cfg.get('jira') or {}).get('project'):
                return False, 'Choose a project to read.'
            return True, ''
        if key == 'slack_user':
            if not row.get('connected'):
                return False, 'Add the client id and secret, then press Connect.'
            if not (cfg.get('slack') or {}).get('channels'):
                return False, 'Choose the channels to read.'
            return True, ''
        return bool(row['credentials_present']), 'Add the credentials for this platform.'

    @app.get('/api/platforms')
    async def platforms(request: Request):
        credentials.refresh()   # before describing, so an edit in the file is reflected at once
        cfg = index.settings() or {}
        rows = registry.describe(cfg.get('platforms') or ['github'])
        # Show the exact address this browser will send, so it can be registered without guessing.
        base = str(request.base_url).rstrip('/')
        scan = index.active_scan()
        for row in rows:
            if row.get('oauth'):
                row['redirect_uri'] = base + registry.BY_KEY[row['key']]['oauth']['redirect_path']
            row['ready'], row['pending'] = _readiness(row, cfg, scan)
            row['scope'] = _scope(row['key'], cfg, scan)
        return {'platforms':rows,
                'credentials':credentials.status(),
                'note':'Selecting a platform records that this project uses it. It never grants access. '
                       'Access needs a credential in your local .env file and a scope you name yourself.'}

    @app.get('/api/connect/{platform}')
    async def connect(platform: str, request: Request):
        if demo:
            raise HTTPException(409,'Example mode does not connect to anything.')
        credentials.refresh()   # pick up an edit made in the file since startup
        url = oauth.begin(platform, str(request.base_url), os.getenv)
        applog.event('oauth.begin', platform=platform)
        return {'url':url}

    @app.get('/api/slack/callback')
    async def slack_callback(code: str = '', state: str = '', error: str = ''):
        if error:
            applog.warn('oauth.refused', platform='slack_user', reason=error)
            return RedirectResponse('/?connect=refused', status_code=303)
        if not code or not state:
            return RedirectResponse('/?connect=incomplete', status_code=303)
        try:
            credentials.refresh()
            platform, name, token, granted = await oauth.complete(state, code, os.getenv)
            credentials.save({name:token})
        except SourceError as exc:
            applog.failure('oauth.failed', platform='slack_user', msg=exc)
            reason = str(exc).rsplit(': ',1)[-1].strip('. ')[:60]
            return RedirectResponse('/?connect=failed&reason='+quote(reason), status_code=303)
        # names and granted scopes only; the token itself must never reach a log
        applog.event('oauth.connected', platform=platform, stored=name, scopes=granted)
        return RedirectResponse('/?connect=ok', status_code=303)

    @app.post('/api/credentials')
    async def set_credentials(update: CredentialUpdate):
        if demo:
            raise HTTPException(409,'Example mode does not connect to anything.')
        try:
            saved = credentials.save(update.values)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from None
        # Names only. A credential value must never reach a log.
        listings.clear()   # new credentials may see a different set of channels or projects
        applog.event('credentials.saved', names=','.join(saved) or 'none')
        return {'saved':saved,'status':credentials.status()}

    @app.get('/api/slack/channels')
    async def slack_channels():
        credentials.refresh()
        token = os.getenv('SLACK_USER_TOKEN','')
        if not token:
            return {'connected':False,'channels':[],'chosen':[],'workspace':'',
                    'reason':'Connect Slack first.'}
        cfg = index.settings() or {}
        saved = cfg.get('slack') or {}
        found = cached('slack')
        if found is None:
            try:
                found = remember('slack', await SlackSource(token).channels())
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
        token = os.getenv('SLACK_USER_TOKEN','')
        if not token:
            raise HTTPException(409,'Connect Slack first.')
        cfg = index.settings() or {}
        saved = cfg.get('slack') or {}
        service.task = asyncio.create_task(
            service.read_slack(token, saved.get('workspace',''), saved.get('channels',[])))
        return {'started':True,'channels':len(saved.get('channels',[]))}

    def jira_credentials():
        credentials.refresh()
        return (os.getenv('JIRA_SITE',''), os.getenv('JIRA_EMAIL',''), os.getenv('JIRA_API_TOKEN',''))

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
                found = remember('jira', await JiraSource(site, email, token).projects())
            except SourceError as exc:
                return {'connected':True,'projects':[],'chosen':saved,'reason':str(exc)}
        return {'connected':True,'projects':found,'chosen':saved,'reason':'',
                'read_at':(cfg.get('jira') or {}).get('read_at',''),
                'blocks':index.source_blocks((index.active_scan() or {}).get('id',0),'jira/')}

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
        service.task = asyncio.create_task(service.read_jira(site, email, token, key))
        return {'started':True,'project':key}

    @app.get('/api/overview')
    async def overview():
        scan = index.active_scan()
        if not scan:
            return {'available':False,'reason':'Run a successful scan first.'}
        cached = index.overview(scan['commit'])
        return {'available':bool(cached),'building':service.overview_progress is not None,
                'progress':service.overview_progress,'overview':cached,
                'reason':'' if cached else 'No overview has been built for this commit yet.'}

    @app.post('/api/overview')
    async def build_overview():
        idle()
        if not index.active_scan():
            raise HTTPException(409,'Run a successful scan before building the overview.')
        service.task = asyncio.create_task(service.build_overview())
        return {'started':True,'topics':len(TOPICS)}

    @app.post('/api/ask')
    async def ask(question: Question):
        idle()
        if not question.question.strip():
            raise HTTPException(422,'Enter a question.')
        return await service.ask(question.question.strip())

    @app.post('/api/feedback')
    async def feedback(item: Feedback):
        if not index.feedback(item.answer_id,item.rating,item.sufficiency):
            raise HTTPException(404,'This answer is no longer current. Ask again after the latest scan.')
        return {'saved':True}

    app.mount('/static',StaticFiles(directory=ROOT/'pka/static'),name='static')
    return app
