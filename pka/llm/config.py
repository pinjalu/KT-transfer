"""Reviewed free-model catalog and validated, workspace-local routing settings.

Catalog availability is not proof of an API account's billing status. Cloud use
also requires a recent, key-bound confirmation of a free account with no billing.
"""
import hashlib
import json
import os
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

CATALOG_REVIEWED = '2026-10-27'
CATALOG_EXPIRES = '2026-11-26'
CATALOG = [
    {'provider':'gemini', 'model':'gemini-3.8-flash', 'label':'Gemini 3.8 Flash',
     'pricing':'https://ai.google.dev/gemini-api/docs/pricing',
     'structured':'https://ai.google.dev/gemini-api/docs/generate-content/structured-output'},
    {'provider':'gemini', 'model':'gemini-3.5-flash-lite', 'label':'Gemini 3.5 Flash-Lite',
     'pricing':'https://ai.google.dev/gemini-api/docs/pricing',
     'structured':'https://ai.google.dev/gemini-api/docs/generate-content/structured-output'},
    {'provider':'groq', 'model':'openai/gpt-oss-120b', 'label':'Groq GPT-OSS 120B',
     'pricing':'https://console.groq.com/docs/rate-limits',
     'structured':'https://console.groq.com/docs/structured-outputs'},
    {'provider':'groq', 'model':'openai/gpt-oss-20b', 'label':'Groq GPT-OSS 20B',
     'pricing':'https://console.groq.com/docs/rate-limits',
     'structured':'https://console.groq.com/docs/structured-outputs'},
]
FEATURES = {'overview':'Project overview', 'ask':'Ask assistant', 'jira':'Jira explanations',
            'business_logic':'Business logic / feature KT', 'tests':'Test suggestions',
            'slack':'Slack decision summaries'}
SECRETS = {'gemini':'GEMINI_API_KEY', 'groq':'GROQ_API_KEY'}
PROMPT_VERSION = 'router-3-grounded-explanations'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Limits(Strict):
    rpm: int = Field(default=2, ge=1, le=1000)
    rpd: int = Field(default=10, ge=1, le=100000)
    tpm: int = Field(default=12000, ge=100, le=1000000)
    tpd: int = Field(default=100000, ge=100, le=10000000)


class Target(Strict):
    provider: Literal['ollama', 'gemini', 'groq']
    model: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:/-]+$')

    @model_validator(mode='after')
    def catalog_only(self):
        if self.provider == 'ollama':
            # Cloud models available through Ollama are outside the local fallback policy.
            if 'cloud' in self.model.lower() or '://' in self.model or self.model.startswith('/'):
                raise ValueError('Choose a locally installed Ollama model, not a cloud model or URL.')
        elif not any((m['provider'], m['model']) == (self.provider, self.model) for m in CATALOG):
            raise ValueError('Cloud models must be in the reviewed free-tier catalog.')
        return self


class Provider(Strict):
    enabled: bool = False
    limits: Limits = Field(default_factory=Limits)
    timeout_seconds: int = Field(default=45, ge=5, le=180)


class Routing(Strict):
    mode: Literal['automatic', 'manual'] = 'automatic'
    local_enabled: bool = True
    local_model: str = Field(default_factory=lambda: os.getenv('OLLAMA_MODEL', 'qwen3:1.7b'))
    manual: Target = Field(default_factory=lambda: Target(provider='ollama', model=os.getenv('OLLAMA_MODEL', 'qwen3:1.7b')))
    manual_fallback: bool = False
    overview_concurrency: int = Field(default=2, ge=1, le=4)
    overview_interval_seconds: int = Field(default=0, ge=0, le=120)
    providers: dict[str, Provider] = Field(default_factory=lambda: {
        'gemini':Provider(), 'groq':Provider(limits=Limits(rpm=30, rpd=1000, tpm=8000, tpd=200000))})
    project_limits: Limits = Field(default_factory=lambda: Limits(rpm=10, rpd=100, tpm=20000, tpd=300000))
    routes: dict[str, list[Target]] = Field(default_factory=lambda: {
        name: [Target(provider=p, model=m) for p, m in route] for name, route in {
            'overview':[('gemini','gemini-3.8-flash'),('groq','openai/gpt-oss-120b')],
            'ask':[('groq','openai/gpt-oss-120b'),('gemini','gemini-3.8-flash')],
            'jira':[('groq','openai/gpt-oss-120b'),('gemini','gemini-3.8-flash')],
            'business_logic':[('gemini','gemini-3.8-flash'),('groq','openai/gpt-oss-120b')],
            'tests':[('groq','openai/gpt-oss-120b'),('gemini','gemini-3.8-flash')],
            'slack':[('gemini','gemini-3.5-flash-lite'),('groq','openai/gpt-oss-120b')],
        }.items()})

    @model_validator(mode='after')
    def complete_routes(self):
        Target(provider='ollama', model=self.local_model)
        if set(self.providers) != {'gemini','groq'} or set(self.routes) != set(FEATURES):
            raise ValueError('Supply both cloud providers and every supported feature route.')
        for route in self.routes.values():
            if not 1 <= len(route) <= 3 or len({t.provider for t in route}) != len(route):
                raise ValueError('Each feature needs one to three targets from distinct providers.')
        # Published Groq free limits are upper bounds, not permission to increase a plan.
        cap = {'rpm':30, 'rpd':1000, 'tpm':8000, 'tpd':200000}
        if any(getattr(self.providers['groq'].limits, k) > v for k,v in cap.items()):
            raise ValueError('Groq limits exceed the reviewed free-plan ceiling.')
        return self

    def targets(self, feature):
        local = Target(provider='ollama', model=self.local_model)
        route = [self.manual] if self.mode == 'manual' else list(self.routes[feature])
        if self.mode == 'manual' and self.manual_fallback:
            route += self.routes[feature]
        if self.local_enabled and (self.mode == 'automatic' or self.manual_fallback):
            route.append(local)
        return list({(t.provider,t.model):t for t in route}.values())


def catalog_current():
    return date.today().isoformat() <= CATALOG_EXPIRES
