"""Local-only Ollama adapter. Never downloads a model or uses Ollama cloud."""
import asyncio
import time
import httpx
from pka.llm.http import tokens
from pka.llm.types import ProviderError, Reply

HOST = 'http://127.0.0.1:11434'
COLD_START = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError, httpx.RemoteProtocolError)


async def transport(payload, started, retry_delay=3):
    for attempt in (1,2):
        try:
            async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
                # Inspect metadata before sending any content. An innocently named
                # local alias can otherwise forward to an Ollama cloud model.
                shown = await client.post(HOST+'/api/show',json={'model':payload['model']})
                if shown.status_code != 200:
                    raise ProviderError('model_unavailable',status=shown.status_code)
                info = shown.json()
                if (not isinstance(info,dict) or info.get('remote_host') or info.get('remote_model')
                        or not info.get('model_info') or info.get('details',{}).get('format') != 'gguf'):
                    raise ProviderError('local_model_unverified')
                return await client.post(HOST+'/api/chat', json=payload)
        except COLD_START:
            if attempt == 2: raise
            await asyncio.sleep(retry_delay)


class Ollama:
    async def generate(self, request, target, key='', timeout=180):
        # Compatibility hook for existing local diagnostics and transport tests.
        from pka.service import _ask_ollama
        payload = {'model':target.model, 'stream':False, 'think':False, 'format':request.schema,
                   'keep_alive':'5m', 'messages':request.messages,
                   'options':{'temperature':request.temperature,'num_ctx':request.context_window,
                              'num_predict':request.max_output_tokens}}
        try:
            response = await _ask_ollama(payload, time.perf_counter())
            if response.status_code != 200:
                raise ProviderError('model_unavailable' if response.status_code == 404 else 'temporary', status=response.status_code)
            body = response.json()
            if body.get('done_reason') == 'length': raise ProviderError('incomplete_response')
            content = body['message']['content']
            if not isinstance(content, str): raise ProviderError('invalid_response')
            return Reply(content, tokens(body.get('prompt_eval_count')), tokens(body.get('eval_count')))
        except httpx.TimeoutException:
            raise ProviderError('timeout') from None
        except httpx.RequestError:
            raise ProviderError('connection') from None
        except (ValueError, TypeError, KeyError):
            raise ProviderError('invalid_response') from None
