import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
import os
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from pka import applog
from pka.config import ROOT, LIMITS, data_dir, validate_selection
from pka.connectors.base import SourceError
from pka.index import Index
from pka.service import Service

class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    repo: str = Field(max_length=400)  # a pasted repository address is longer than owner/repository
    branch: str = Field(max_length=200)
class Question(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=3,max_length=600)
class Feedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer_id: int
    rating: Literal['correct','partially correct','incorrect','not assessed']
    sufficiency: Literal['sufficient','partly sufficient','insufficient','not assessed']


def create_app(demo=False, db_path=None):
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

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        host = request.headers.get('host','').split(':')[0].lower()
        origin = request.headers.get('origin')
        if host not in {'localhost','127.0.0.1'}:
            return JSONResponse({'detail':'Local host required.'},status_code=403)
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'Same-origin requests only.'},status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail':'Cross-site requests refused.'},status_code=403)
        if request.url.path.startswith('/api/') and request.headers.get('x-pka-request') != '1':
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
                'warning':service.access_warning,'ready':index.active_scan() is not None}

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
        applog.event('config.saved', repo=repo, branch=branch, typed_chars=len(selection.repo))
        async with service.lock:
            index.configure({'repo':repo,'branch':branch})
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
