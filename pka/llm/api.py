"""Authenticated AI settings. Keys are written to the active account vault only."""
from typing import Literal
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from pydantic import Field, SecretStr
from pka import credentials, monitoring
from pka.connectors.base import SourceError
from pka.llm.config import CATALOG, CATALOG_EXPIRES, CATALOG_REVIEWED, FEATURES, SECRETS, Routing, Strict, Target, catalog_current


class KeyUpdate(Strict):
    provider: Literal['gemini','groq']
    key: SecretStr = Field(max_length=500)


class Confirmation(Strict):
    provider: Literal['gemini','groq']
    free_plan_without_billing_or_credits: bool


class Permission(Strict):
    providers: list[Literal['gemini','groq']] = Field(default_factory=list,max_length=2)
    approved_public_content: bool = False
    approved_github_content: bool = False
    approved_jira_content: bool = False
    approved_slack_content: bool = False


def install(app, service):
    router = service.llm

    @app.exception_handler(RequestValidationError)
    async def safe_validation(request, exc):
        if request.url.path.startswith('/api/ai/') or request.url.path == '/api/credentials':
            # FastAPI's default errors include input values, including invalid secrets.
            return JSONResponse({'detail':'Invalid AI settings or credential fields. Check the allowed values and limits.'},status_code=422)
        return await request_validation_exception_handler(request,exc)

    @app.get('/api/ai')
    async def ai_settings():
        config = router.store.config()
        repo = (service.index.settings() or {}).get('repo','')
        return {'config':config.model_dump(), 'features':FEATURES, 'catalog':CATALOG,
                'catalog_reviewed':CATALOG_REVIEWED,'catalog_expires':CATALOG_EXPIRES,
                'catalog_current':catalog_current(), 'repo':repo,
                'permission':router.store.permission(repo),
                'secure_storage':credentials.active_vault.get() is not None,
                'providers':{p:{'key_configured':bool(router.key_reader(p)),
                    'free_account_confirmed':router.store.confirmed(p,router.key_reader(p))} for p in SECRETS},
                'usage':router.ledger.dashboard(router.workspace,config),
                'monitoring':{'file':'logs/activity.jsonl','max_bytes':monitoring.MAX_BYTES,'backups':monitoring.BACKUPS},
                'policy':'Cloud is off by default. Free-plan confirmation is your manual attestation, not a provider billing check. It expires after seven days and on key changes. GitHub content requires explicit project approval and current access. Jira and Slack additionally require separate source approval for that project and those providers. Local folders and conversation history stay local.'}

    @app.post('/api/ai/config')
    async def ai_config(value: Routing):
        for provider, settings in value.providers.items():
            if settings.enabled:
                if not catalog_current(): raise HTTPException(409,'The free-model catalog needs review before cloud can be enabled.')
                if not router.store.confirmed(provider,router.key_reader(provider)):
                    raise HTTPException(409,'Save a key and confirm its free account with billing and promotional credits disabled first.')
        router.store.save_config(value.model_dump())
        monitoring.event('ai.config_saved', index_path=service.index.path, mode=value.mode)
        return {'saved':True}

    @app.post('/api/ai/test')
    async def ai_test(value: Target):
        if value.provider not in SECRETS:
            raise HTTPException(422,'Choose Gemini or Groq for a connection test.')
        try:
            result = await router.probe(value)
        except SourceError as error:
            info = getattr(error,'generation',{})
            attempts = info.get('attempts') or []
            code = attempts[-1].get('error',error.code) if attempts else error.code
            return {'ok':False,'provider':value.provider,'model':value.model,'code':code,
                    'generation':info,'synthetic_only':True}
        return {'ok':True,'provider':value.provider,'model':value.model,'generation':result.generation,'synthetic_only':True}

    @app.post('/api/ai/key')
    async def ai_key(value: KeyUpdate):
        try:
            credentials.save({SECRETS[value.provider]:value.key.get_secret_value()})
        except ValueError as error:
            raise HTTPException(400,str(error)) from None
        router.store.confirm(value.provider,'',False)
        config = router.store.config()
        config.providers[value.provider].enabled = False
        router.store.save_config(config.model_dump())
        # Key rotation never resets shared quota counters or cooldowns.
        monitoring.event('ai.key_saved', index_path=service.index.path, provider=value.provider, enabled=False)
        return {'saved':True,'enabled':False}

    @app.post('/api/ai/confirmation')
    async def ai_confirmation(value: Confirmation):
        key = router.key_reader(value.provider)
        if value.free_plan_without_billing_or_credits and not key:
            raise HTTPException(409,'Save this provider key in the secure vault first.')
        router.store.confirm(value.provider,key,value.free_plan_without_billing_or_credits)
        monitoring.event('ai.confirmation', index_path=service.index.path, provider=value.provider, confirmed=value.free_plan_without_billing_or_credits)
        if not value.free_plan_without_billing_or_credits:
            config = router.store.config()
            config.providers[value.provider].enabled = False
            router.store.save_config(config.model_dump())
        return {'saved':True,'verification':'manual_attestation','valid_days':7}

    @app.post('/api/ai/permission')
    async def ai_permission(value: Permission):
        repo = (service.index.settings() or {}).get('repo','')
        if not repo: raise HTTPException(409,'Select a project first.')
        revision = service.index.revision
        classification = 'github' if value.approved_github_content else 'public'
        extra_sources = [name for name, approved in (('jira',value.approved_jira_content),('slack',value.approved_slack_content)) if approved]
        if value.providers:
            if value.approved_github_content:
                if router.repository_check is None or not await router.repository_check(repo):
                    raise HTTPException(409,'Read the selected GitHub repository first. Your current account must have access before cloud approval can be saved.')
            elif not value.approved_public_content or not await router.public_check(repo):
                raise HTTPException(409,'Cloud approval requires explicit consent. Legacy public-only consent also requires a currently public GitHub repository.')
            if extra_sources:
                if not value.approved_github_content or not service.index.active_scan():
                    raise HTTPException(409,'Select and approve the connected project before approving Jira or Slack content.')
                await service.check_external_access(service.index.active_scan(),names=tuple(extra_sources))
        # Guard against changing projects while the upstream access check runs.
        if repo != (service.index.settings() or {}).get('repo','') or revision != service.index.revision:
            raise HTTPException(409,'The selected project changed. Review its privacy settings again.')
        result = router.store.permit(repo,value.providers,classification=classification,source_types=['github',*extra_sources])
        monitoring.event('ai.permission', index_path=service.index.path, approved=bool(value.providers), count=len(value.providers))
        return result
