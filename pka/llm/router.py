"""Bounded function routing with privacy gates before every provider attempt."""
import asyncio
import json
import re
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
import httpx
from pydantic import ValidationError
from pka import credentials, monitoring
from pka.connectors.base import SourceError
from pka.llm.config import FEATURES, PROMPT_VERSION, Routing, SECRETS, Target, catalog_current, digest
from pka.llm.types import Generated, ProviderError, Request
from pka.llm.store import Store
from pka.llm.ollama import Ollama
from pka.llm.gemini import Gemini
from pka.llm.groq import Groq

ACTIVE = ContextVar('pka_llm_context', default=None)


def current_feature():
    context = ACTIVE.get()
    return context[1] if context else 'ask'


def secret(provider):
    vault = credentials.active_vault.get()
    return vault.read().get(SECRETS[provider], '') if vault is not None else ''


async def public_repository(repo):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo): return False
    # Anonymous metadata cannot confirm a private repository. Content reads still
    # use the existing permission-checked MCP connectors.
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
            response = await client.get('https://api.github.com/repos/'+repo,
                headers={'Accept':'application/vnd.github+json'})
        value = response.json()
        return response.status_code == 200 and value.get('private') is False and value.get('full_name','').casefold() == repo.casefold()
    except (httpx.RequestError, ValueError, TypeError, AttributeError):
        return False


class Router:
    def __init__(self, index, ledger_path=None, *, adapters=None, key_reader=secret, public_check=public_repository, repository_check=None):
        self.index = index
        self.store = Store(index.path)
        self.ledger = Store(ledger_path or index.path)
        self.workspace = digest(str(index.path))
        self.adapters = adapters or {'ollama':Ollama(), 'gemini':Gemini(), 'groq':Groq()}
        self.key_reader, self.public_check = key_reader, public_check
        self.repository_check = repository_check

    def signature(self):
        repo = (self.index.settings() or {}).get('repo','')
        config = self.store.config()
        keys = {p:digest(self.key_reader(p)) for p in SECRETS if config.providers[p].enabled}
        return digest({'routing':self.store.signature(repo),'version':PROMPT_VERSION,'keys':keys})

    def cache_signature(self):
        config = self.store.config().model_dump()
        config.pop('overview_concurrency')
        config.pop('overview_interval_seconds')
        config.pop('project_limits')
        config['providers'] = {p:{'enabled':v['enabled']} for p,v in config['providers'].items()}
        repo = (self.index.settings() or {}).get('repo','')
        return digest({'config':config,'permission':self.store.permission(repo),'version':PROMPT_VERSION})

    async def probe(self, target):
        """Explicit connection test: fixed synthetic content, pinned model, no fallback.

        This diagnostic can test a disabled provider but cannot enable it, approve
        a project, take arbitrary prompts, or bypass free-plan/quota checks.
        """
        if target.provider not in SECRETS:
            raise SourceError('llm_config', 'Choose a cloud provider for this connection test.')
        key = self.key_reader(target.provider)
        request = Request(
            [{'role':'user','content':'Synthetic connection test. Return JSON with status equal to ok and sum equal to 5 (2 plus 3).'}],
            {'type':'object','properties':{'status':{'type':'string','enum':['ok']},'sum':{'type':'integer','enum':[5]}},
             'required':['status','sum'],'additionalProperties':False}, [], max_output_tokens=512)
        def validate(raw):
            if raw != {'status':'ok','sum':5} or type(raw.get('sum')) is not int:
                raise ValueError('Invalid synthetic response')
            return raw
        async def unchanged():
            if self.key_reader(target.provider) != key or not self.store.confirmed(target.provider,key):
                raise SourceError('stale','The key or free-plan confirmation changed. Retry the connection test.')
        return await self._run(request, validate, 'ask', unchanged, synthetic=True, override=target, diagnostic=True)

    async def generate(self, request, validator, feature, guard, *, synthetic=False, override=None):
        return await self._run(request, validator, feature, guard, synthetic=synthetic, override=override)

    async def _run(self, request, validator, feature, guard, *, synthetic=False, override=None, diagnostic=False):
        generation_id = uuid.uuid4().hex
        started = time.perf_counter()
        def log(name, **fields):
            monitoring.event(name, index_path=self.index.path, generation_id=generation_id,
                feature=feature, synthetic=synthetic, diagnostic=diagnostic, **fields)
        log('llm.started', source_count=len(request.sources))
        try:
            value = await self._generate(request, validator, feature, guard,
                synthetic=synthetic, override=override, diagnostic=diagnostic, log=log)
        except asyncio.CancelledError:
            log('llm.finished', status='cancelled', elapsed_seconds=round(time.perf_counter()-started,3))
            raise
        except Exception as error:
            log('llm.finished', status='failed', code=error.code if isinstance(error,SourceError) else 'unexpected',
                elapsed_seconds=round(time.perf_counter()-started,3))
            raise
        log('llm.finished', status='succeeded', provider=value.generation['provider'], model=value.generation['model'],
            elapsed_seconds=round(time.perf_counter()-started,3), attempt_count=len(value.generation['attempts']))
        return value

    async def _generate(self, request, validator, feature, guard, *, synthetic, override, diagnostic, log):
        if feature not in FEATURES: raise SourceError('llm_config','Unknown generation functionality.')
        config = self.store.config()
        signature = self.signature()
        repo = (self.index.settings() or {}).get('repo','')
        project = digest('synthetic' if synthetic else repo)
        attempts, attempted = [], set()
        targets = [override] if override else config.targets(feature)
        for target in targets:
            provider = target.provider
            if provider in attempted:
                continue  # At most one charged request per cloud provider in a logical generation.
            reason, key = '', ''
            if provider == 'ollama':
                if not config.local_enabled: reason = 'local_disabled'
            elif not config.providers[provider].enabled and not diagnostic:
                reason = 'disabled'
            elif not catalog_current():
                reason = 'catalog_expired'
            else:
                key = self.key_reader(provider)
                if not key: reason = 'missing_key'
                elif not self.store.confirmed(provider,key): reason = 'free_account_unconfirmed'
                elif not synthetic:
                    permission = self.store.permission(repo)
                    if provider not in permission['providers'] or permission['classification'] not in {'public','github'}:
                        reason = 'privacy_not_approved'
                    elif request.has_history:
                        reason = 'conversation_requires_local'
                    elif any(s.get('path','').startswith('local:') or
                             any(s.get('path','').startswith(kind+'/') and kind not in permission['source_types']
                                 for kind in ('jira','slack')) for s in request.sources):
                        reason = 'private_source_requires_local'
                    elif permission['classification'] == 'public' and not await self.public_check(repo):
                        reason = 'public_repository_unconfirmed'
                    elif permission['classification'] == 'github' and (self.repository_check is None or not await self.repository_check(repo)):
                        reason = 'repository_access_unconfirmed'
            if reason:
                attempts.append({'provider':provider,'model':target.model,'status':'skipped','error':reason})
                log('llm.skipped', provider=provider, model=target.model, reason=reason)
                continue
            await guard()
            if self.signature() != signature: raise SourceError('stale','AI permissions or routing changed. Retry with the current settings.')
            # Reserve input estimate plus the full output allowance before network IO.
            from pka.llm.token_budget import estimate
            estimated, estimation_method = estimate(request, target)
            identifier, reason = self.ledger.reserve(self.workspace,project,feature,target,estimated,
                config.providers[provider].limits if provider != 'ollama' else config.project_limits,config.project_limits)
            if reason:
                attempts.append({'provider':provider,'model':target.model,'status':'skipped','error':reason})
                log('llm.skipped', provider=provider, model=target.model, reason=reason)
                continue
            if attempts:
                log('llm.fallback', provider=provider, model=target.model)
            attempted.add(provider)
            started, reply = time.perf_counter(), None
            log('llm.attempt', provider=provider, model=target.model, attempt_id=identifier, estimated_tokens=estimated)
            try:
                reply = await self.adapters[provider].generate(request,target,key,
                    config.providers[provider].timeout_seconds if provider != 'ollama' else 180)
                try:
                    raw = json.loads(reply.content)
                    result = validator(raw)
                except (ValidationError, ValueError, KeyError, TypeError, SourceError):
                    raise ProviderError('invalid_response') from None
                await guard()
                if self.signature() != signature: raise SourceError('stale','AI permissions or routing changed during generation. The result was withheld.')
            except asyncio.CancelledError:
                self.ledger.finish(identifier,time.perf_counter()-started,status='cancelled')
                log('llm.cancelled', provider=provider, model=target.model, attempt_id=identifier)
                raise
            except SourceError:
                self.ledger.finish(identifier,time.perf_counter()-started,status='withheld')
                log('llm.withheld', provider=provider, model=target.model, attempt_id=identifier)
                raise
            except ProviderError as error:
                elapsed = round(time.perf_counter()-started,3)
                self.ledger.finish(identifier,elapsed,reply=reply,error=error,status='failed')
                log('llm.failed', provider=provider, model=target.model, attempt_id=identifier,
                    code=error.code, http_status=error.status, retry_after_seconds=error.retry_after, elapsed_seconds=elapsed)
                attempts.append({'provider':provider,'model':target.model,'status':'failed','error':error.code,
                                 'http_status':error.status,'latency_seconds':elapsed,
                                 'input_tokens':reply.input_tokens if reply else None,'output_tokens':reply.output_tokens if reply else None})
                continue
            except Exception:
                # A provider/transport bug must not publish raw errors, content or keys.
                elapsed = round(time.perf_counter()-started,3)
                self.ledger.finish(identifier,elapsed,reply=reply,error=ProviderError('adapter_error'),status='failed')
                log('llm.failed', provider=provider, model=target.model, attempt_id=identifier, code='adapter_error', elapsed_seconds=elapsed)
                attempts.append({'provider':provider,'model':target.model,'status':'failed',
                                 'error':'adapter_error','latency_seconds':elapsed})
                continue
            elapsed = round(time.perf_counter()-started,3)
            self.ledger.finish(identifier,elapsed,reply=reply)
            log('llm.succeeded', provider=provider, model=target.model, attempt_id=identifier,
                elapsed_seconds=elapsed, input_tokens=reply.input_tokens, output_tokens=reply.output_tokens)
            attempts.append({'provider':provider,'model':target.model,'status':'succeeded','latency_seconds':elapsed,
                             'input_tokens':reply.input_tokens,'output_tokens':reply.output_tokens})
            info = {'provider':provider,'model':target.model,'function':feature,'latency_seconds':elapsed,
                    'input_tokens':reply.input_tokens,'output_tokens':reply.output_tokens,
                    'usage_source':'provider' if reply.input_tokens is not None and reply.output_tokens is not None else 'not_reported',
                    'estimated_reserved_tokens':estimated,'estimation_method':estimation_method,'reported_limits':reply.reported,
                    'attempts':attempts,'routing_signature':signature,'request_id':identifier}
            return Generated(result,info)
        failure = SourceError('llm_unavailable','No eligible model completed this request. Check AI Settings for privacy, free-account confirmation, quotas and provider status. Retrieved excerpts remain available.')
        failure.generation = {'function':feature,'attempts':attempts,'provider':None,'model':None}
        raise failure


@contextmanager
def using(router, feature, guard, *, synthetic=False, override=None):
    token = ACTIVE.set((router,feature,guard,synthetic,override))
    try: yield
    finally: ACTIVE.reset(token)


async def generate(request, validator, feature='ask'):
    context = ACTIVE.get()
    if context:
        router, selected, guard, synthetic, override = context
        return await router.generate(request,validator,'tests' if feature=='tests' else selected,guard,
                                     synthetic=synthetic,override=override)
    # Standalone callers keep local-only behavior; no environment cloud key is used.
    target = Target(provider='ollama',model=Routing().local_model)
    started = time.perf_counter()
    try:
        reply = await Ollama().generate(request,target)
        result = validator(json.loads(reply.content))
    except ProviderError as exc:
        from pka.service import _why_request
        if exc.code == 'connection': message = _why_request(httpx.ConnectError('local'))
        elif exc.code == 'timeout': message = _why_request(httpx.ReadTimeout('local'))
        elif exc.code == 'model_unavailable': message = f'Ollama has no model called {target.model}. Install it with: ollama pull {target.model}'
        else: message = 'The local model could not return a complete structured response. Inspect the retrieved excerpts.'
        raise SourceError('ollama',message) from None
    except (ValueError,KeyError,TypeError):
        raise SourceError('answer_format','The model returned an invalid answer. Inspect the retrieved sources and try a narrower question.') from None
    return Generated(result,{'provider':'ollama','model':target.model,'function':feature,
                            'latency_seconds':round(time.perf_counter()-started,3),
                            'input_tokens':reply.input_tokens,'output_tokens':reply.output_tokens,
                            'usage_source':'provider' if reply.input_tokens is not None else 'not_reported','attempts':[]})
