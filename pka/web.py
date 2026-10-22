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
from pka.config import ROOT, KEEP_LOGS, LIMITS, data_dir, log_dir, validate_selection
from pka import credentials, oauth
from pka.connectors import registry
from pka.connectors.base import SourceError
from pka import facts, features
from pka.index import Index
from pka.overview import reading_order, topics_for
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
    # One character, not three. The old floor existed to stop an empty box being sent, and the
    # handler already refuses whitespace, but it also caught "hi" and "hy" and answered them
    # with a field validation error instead of the greeting the small talk guard exists to
    # give. A short question is not a malformed one.
    question: str = Field(min_length=1,max_length=600)
class Feedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer_id: int
    rating: Literal['correct','partially correct','incorrect','not assessed']
    sufficiency: Literal['sufficient','partly sufficient','insufficient','not assessed']


def create_app(demo=False, db_path=None, connector_factory=None):
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
        repo = 'demo/example-shop' if demo else os.getenv('GITHUB_REPOSITORY','')
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

    # The built React interface, if it has been built. `npm run build` in frontend/ writes it.
    # Without it the original single-page interface is still served, so a checkout with no Node
    # toolchain still runs.
    UI = ROOT/'pka/static/ui/index.html'
    LEGACY = ROOT/'pka/static/index.html'

    @app.get('/')
    async def home():
        return FileResponse(UI if UI.exists() else LEGACY)

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
                    'knowledge_revision':index.revision,
                    'busy':False,'demo':demo,'limits':asdict(LIMITS),
                    'model':os.getenv('OLLAMA_MODEL','qwen3:1.7b'),
                    'token_configured':bool(os.getenv('GITHUB_TOKEN','')) and not demo,
                    'warning':'','job_error':'','job_name':'',
                    'jira_reading':False,'jira_progress':None,
                    'slack_reading':False,'slack_progress':None,
                    'overview_building':False,'overview_progress':None,
                    'awaiting_project':True,
                    'stored_project':{'repo':previous.get('repo',''),
                                      'branch':previous.get('branch','')} if previous.get('repo') else None}
        return {'settings':index.settings(),'scan':scan,'last_successful_scan':index.last_successful(),
                'knowledge_revision':index.revision,
                'busy':service.busy() or bool(service.task and not service.task.done()),'demo':demo,
                'limits':asdict(LIMITS),'model':os.getenv('OLLAMA_MODEL','qwen3:1.7b'),
                'token_configured':bool(os.getenv('GITHUB_TOKEN','')) and not demo,
                'warning':service.access_warning,'ready':index.active_scan() is not None,
                'job_error':service.job_error,'job_name':service.job_name,
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
        applog.event('config.saved', repo=repo, branch=branch, platforms=','.join(platforms),
                     typed_chars=len(selection.repo))
        async with service.lock:
            index.configure({'repo':repo,'branch':branch,'platforms':platforms})
            service.access_warning = ''
            chosen['this_run'] = True
        # Saying whether this reconnected to a stored snapshot or starts empty, because the
        # difference decides whether the next thing to do is ask a question or run a scan.
        return {'ok':True,'reconnected':index.active_scan() is not None}

    @app.post('/api/scan')
    async def scan():
        idle()
        if not index.settings():
            raise HTTPException(409,'Save a repository and branch first.')
        service.task = asyncio.create_task(service.background('scan',service.scan()))
        return {'started':True}

    @app.post('/api/scan/cancel')
    async def cancel():
        service.cancel.set()
        return {'requested':True,'message':'Cancellation takes effect after the current connector or model request finishes.'}

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
        # Its own setup comes first, because that is what the reader can act on here. Only once
        # that is done does the missing index become the thing in the way.
        if key == 'jira':
            if not row['credentials_present']:
                return False, 'Add the site address, email and API token.'
            if not (cfg.get('jira') or {}).get('project'):
                return False, 'Choose a project to read.'
            if not scan:
                return False, 'Add GitHub and scan a repository, so there is an index to add these issues to.'
            return True, ''
        if key == 'slack_user':
            if not row.get('connected'):
                return False, 'Add the client id and secret, then press Connect.'
            if not (cfg.get('slack') or {}).get('channels'):
                return False, 'Choose the channels to read.'
            if not scan:
                return False, 'Add GitHub and scan a repository, so there is an index to add these messages to.'
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
        idle()
        if demo:
            raise HTTPException(409,'Example mode does not connect to anything.')
        try:
            saved = credentials.save(update.values)
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
        token = os.getenv('SLACK_USER_TOKEN','')
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
        token = os.getenv('SLACK_USER_TOKEN','')
        if not token:
            raise HTTPException(409,'Connect Slack first.')
        cfg = index.settings() or {}
        saved = cfg.get('slack') or {}
        # The token is not passed on. It is handed to the MCP server at launch instead.
        service.task = asyncio.create_task(service.background('slack',
            service.read_slack(saved.get('workspace',''), saved.get('channels',[]))))
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
                found = remember('jira', await via_connector('jira_projects'))
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
        # Only the key travels. The site, email and token go to the MCP server at launch.
        service.task = asyncio.create_task(service.background('jira',service.read_jira(key)))
        return {'started':True,'project':key}

    @app.get('/api/overview')
    async def overview():
        scan = index.active_scan()
        if not scan:
            return {'available':False,'reason':'Run a successful scan first.'}
        await service.check_external_access(scan)
        cached = index.overview(scan['commit'])
        if cached:
            # The reading order is derived from the indexed paths and no model touches it, so
            # there is no reason for a reader to be shown an old one. It was cached inside a
            # payload that only a model rebuild replaces, which meant a correction to it could
            # not reach anybody without paying for that rebuild: after a fix stopped Jira issues
            # being offered as files to read, the stale list kept offering them. Derived at the
            # moment it is asked for instead, which is one query and a sort.
            cached = {**cached,
                      'reading_order':reading_order(index.code_paths(scan['id']),
                                                    repo='' if demo else scan['repo'],
                                                    commit='' if demo else scan['commit'])}
        return {'available':bool(cached),'building':service.overview_progress is not None,
                'progress':service.overview_progress,'overview':cached,
                'reason':'' if cached else 'No overview has been built for this commit yet.'}

    @app.post('/api/overview')
    async def build_overview():
        idle()
        if not index.active_scan():
            raise HTTPException(409,'Run a successful scan before building the overview.')
        scan = index.active_scan()
        present = {p for p in ('slack/','jira/') if index.source_blocks(scan['id'],p)}
        service.task = asyncio.create_task(service.background('overview',service.build_overview()))
        return {'started':True,'topics':len(topics_for(present))}

    @app.post('/api/ask')
    async def ask(question: Question):
        idle()
        if not question.question.strip():
            raise HTTPException(422,'Enter a question.')
        return await service.ask(question.question.strip())

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

    @app.get('/api/features')
    async def feature_list():
        scan = index.active_scan()
        if not scan:
            return {'available':False,'reason':'Run a successful scan first.','features':[]}
        await service.check_external_access(scan)
        payload = features.derive(index,scan,facts.derive(index,scan))
        return {'available':True,'reason':'',**features.listing(payload)}

    @app.get('/api/features/{feature_id}')
    async def feature_detail(feature_id: str):
        scan = index.active_scan()
        if not scan:
            raise HTTPException(409,'Run a successful scan first.')
        await service.check_external_access(scan)
        payload = features.derive(index,scan,facts.derive(index,scan))
        found = next((f for f in payload['features'] if f['id'] == feature_id),None)
        if not found:
            raise HTTPException(404,'No feature by that name was derived from this scan.')
        return features.detail(found)

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

    return app
