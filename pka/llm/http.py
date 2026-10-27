"""Fixed-origin, bounded provider transport and non-sensitive error classification."""
import json
import re
import time
from email.utils import parsedate_to_datetime
import httpx
from pka.llm.types import ProviderError

MAX_RESPONSE_BYTES = 1_000_000


def delay(value):
    if not value:
        return None
    try:
        return max(1, min(604800, float(value)))
    except (ValueError, TypeError):
        try:
            return max(1, min(604800, parsedate_to_datetime(value).timestamp() - time.time()))
        except (ValueError, TypeError, OverflowError):
            units = {'ms':.001,'s':1,'m':60,'h':3600,'d':86400}
            parts = re.findall(r'(\d+(?:\.\d+)?)(ms|s|m|h|d)', str(value))
            return min(604800, max(1, sum(float(n)*units[u] for n,u in parts))) if parts else None


def reported_headers(headers):
    result = {}
    for key in ('limit-requests','remaining-requests','limit-tokens','remaining-tokens'):
        value = headers.get('x-ratelimit-'+key, '')
        if value.isdigit():
            result[key] = min(int(value), 10**12)
    for key in ('reset-requests','reset-tokens'):
        parsed = delay(headers.get('x-ratelimit-'+key))
        if parsed is not None:
            result[key+'-seconds'] = parsed
    return result


def http_error(status, headers, body):
    reported = reported_headers(headers)
    retry = delay(headers.get('retry-after'))
    if status == 429:
        raw = body.decode('utf-8', errors='replace').lower()
        # Structured quota errors can name a daily or exhausted balance limit.
        daily = any(word in raw for word in ('perday', 'per_day', 'per day', 'daily', 'insufficient_quota'))
        if daily:
            retry = max(retry or 0, 86400)
        else:
            try:
                details = json.loads(body).get('error', {}).get('details', [])
                hints = [delay(d.get('retryDelay')) for d in details if isinstance(d, dict)]
                retry = max([retry or 60] + [h for h in hints if h])
            except (ValueError, TypeError, AttributeError):
                retry = retry or 60
        return ProviderError('quota', status=status, retry_after=retry, reported=reported)
    if status in (401,403):
        return ProviderError('authentication', status=status, retry_after=3600, reported=reported)
    if status == 404:
        return ProviderError('model_unavailable', status=status, retry_after=3600, reported=reported)
    if status >= 500 or status in (408,409):
        return ProviderError('temporary', status=status, retry_after=retry or 15, reported=reported)
    # A bad request is specific to its payload. Do not invent a provider-wide
    # cooldown that also blocks unrelated valid questions. Honor an explicit
    # Retry-After, while quota/auth/server failures retain their own cooldowns.
    return ProviderError('request_rejected', status=status, retry_after=retry, reported=reported)


async def post_json(url, payload, headers, timeout, transport=None):
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False,
                                     transport=transport) as client:
            async with client.stream('POST', url, json=payload, headers=headers) as response:
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        if response.status_code != 200:
                            raise http_error(response.status_code,response.headers,b'')
                        raise ProviderError('invalid_response')
                    chunks.append(chunk)
                body = b''.join(chunks)
                if response.status_code != 200:
                    raise http_error(response.status_code, response.headers, body)
                try:
                    return json.loads(body), reported_headers(response.headers)
                except (ValueError, TypeError):
                    raise ProviderError('invalid_response') from None
    except httpx.TimeoutException:
        raise ProviderError('timeout', retry_after=15) from None
    except httpx.RequestError:
        raise ProviderError('connection', retry_after=15) from None


def tokens(value):
    return value if type(value) is int and 0 <= value <= 10**9 else None
