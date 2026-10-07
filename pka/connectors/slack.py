"""Read-only Slack adapter. Lists the channels a token can see and reads the ones chosen.

Nothing here can post, edit, join or leave. Only two Slack methods are ever called, both of
them reads, and the host is fixed, so no caller can direct this at another address.

A channel is read only when it appears in the allowlist the user saved. The token can see more
than that, and the difference is the point: Slack decides what is reachable, the allowlist
decides what is actually read, and both have to agree before a message enters the index.
"""
import asyncio
import time

import httpx

from pka.config import LIMITS
from pka.connectors.base import SourceError

API = 'https://slack.com/api/'
LIST_METHOD = 'conversations.list'
HISTORY_METHOD = 'conversations.history'
REPLIES_METHOD = 'conversations.replies'

# Slack reports its own reasons. These are the ones worth translating for a reader.
REASONS = {
    'invalid_auth': 'The Slack token is not valid any more. Connect Slack again.',
    'token_revoked': 'The Slack token was revoked. Connect Slack again.',
    'account_inactive': 'That Slack account is no longer active.',
    'missing_scope': 'The Slack token is missing a reading permission. Connect Slack again.',
    'not_in_channel': 'Your account is not in that channel, so its messages cannot be read.',
    'channel_not_found': 'That channel no longer exists or is not visible to your account.',
}


class SlackSource:
    """Lists and reads Slack conversations with a user token."""

    def __init__(self, token: str, transport=None):
        if not token:
            raise SourceError('slack', 'Connect Slack before reading messages.')
        self.token = token
        self.transport = transport

    async def _get(self, method: str, params: dict) -> dict:
        if method not in {LIST_METHOD, HISTORY_METHOD, REPLIES_METHOD}:
            raise SourceError('slack', 'That Slack method is not permitted.')
        headers = {'Authorization': 'Bearer ' + self.token,
                   'User-Agent': 'ProjectKnowledgeAssistant/0.1'}
        async with httpx.AsyncClient(transport=self.transport, timeout=30,
                                     follow_redirects=False, trust_env=False) as client:
            for attempt in range(3):
                try:
                    response = await client.get(API + method, headers=headers, params=params)
                except httpx.RequestError:
                    if attempt == 2:
                        raise SourceError('network', 'Slack could not be reached. Check your connection.') from None
                    await asyncio.sleep(2 ** attempt)
                    continue
                if response.status_code == 429:
                    wait = int(response.headers.get('retry-after', '5') or 5)
                    if wait <= 10 and attempt < 2:
                        await asyncio.sleep(wait)
                        continue
                    raise SourceError('rate_limit', f'Slack asked us to wait {wait} seconds. Try again shortly.')
                if response.status_code != 200:
                    raise SourceError('slack', f'Slack returned HTTP {response.status_code}.')
                try:
                    body = response.json()
                except ValueError:
                    raise SourceError('slack', 'Slack returned an unreadable response.') from None
                if not body.get('ok'):
                    code = str(body.get('error', 'unknown'))
                    raise SourceError('slack', REASONS.get(code, 'Slack refused the request: ' + code + '.'))
                return body
        raise SourceError('network', 'Slack request failed.')

    async def channels(self) -> list:
        """Every channel this token can see. Reading one still needs it in the allowlist."""
        found, cursor, pages = [], '', 0
        while pages < LIMITS.slack_max_pages:
            params = {'types': 'public_channel,private_channel', 'exclude_archived': 'true', 'limit': 200}
            if cursor:
                params['cursor'] = cursor
            body = await self._get(LIST_METHOD, params)
            for channel in body.get('channels', []):
                found.append({'id': channel.get('id', ''), 'name': channel.get('name', ''),
                              'private': bool(channel.get('is_private')),
                              'member': bool(channel.get('is_member')),
                              'members': channel.get('num_members')})
            cursor = (body.get('response_metadata') or {}).get('next_cursor', '')
            pages += 1
            if not cursor:
                break
        found.sort(key=lambda c: (not c['member'], c['private'], c['name']))
        return found

    async def messages(self, channel_id: str, oldest: str = '') -> list:
        """Messages in one channel, oldest first, with thread replies folded in beneath."""
        collected, cursor, pages = [], '', 0
        while pages < LIMITS.slack_max_pages and len(collected) < LIMITS.slack_max_messages:
            params = {'channel': channel_id, 'limit': 200}
            if cursor:
                params['cursor'] = cursor
            if oldest:
                params['oldest'] = oldest
            body = await self._get(HISTORY_METHOD, params)
            for message in body.get('messages', []):
                if message.get('subtype') in {'channel_join', 'channel_leave'}:
                    continue
                if not (message.get('text') or '').strip():
                    continue
                collected.append(message)
                if len(collected) >= LIMITS.slack_max_messages:
                    break
            cursor = (body.get('response_metadata') or {}).get('next_cursor', '')
            pages += 1
            if not (body.get('has_more') and cursor):
                break
        collected.sort(key=lambda m: float(m.get('ts', 0) or 0))
        out = []
        threads = 0
        for message in collected:
            out.append(message)
            if message.get('reply_count') and threads < LIMITS.slack_max_threads:
                threads += 1
                try:
                    body = await self._get(REPLIES_METHOD, {'channel': channel_id,
                                                            'ts': message['ts'], 'limit': 100})
                except SourceError:
                    continue
                for reply in body.get('messages', [])[1:]:
                    if (reply.get('text') or '').strip():
                        out.append({**reply, 'in_thread': True})
        return out


def permalink(workspace: str, channel_id: str, ts: str) -> str:
    """Rebuild a message link without a second request. Slack's own format."""
    if not workspace:
        return ''
    return f"https://{workspace}.slack.com/archives/{channel_id}/p{str(ts).replace('.', '')}"


def transcript(channel_name: str, messages: list, workspace: str, channel_id: str) -> list:
    """Turn messages into readable blocks, each small enough to quote back as evidence."""
    blocks, current, first = [], [], None
    for message in messages:
        stamp = time.strftime('%Y-%m-%d %H:%M', time.localtime(float(message.get('ts', 0) or 0)))
        who = message.get('user') or message.get('bot_id') or 'unknown'
        prefix = '    reply ' if message.get('in_thread') else ''
        line = f"{prefix}[{stamp}] {who}: {(message.get('text') or '').strip()}"
        if first is None:
            first = message
        current.append(line)
        if sum(len(x) for x in current) >= LIMITS.chunk_chars:
            blocks.append((current, first))
            current, first = [], None
    if current:
        blocks.append((current, first))
    out = []
    for index, (lines, started) in enumerate(blocks, start=1):
        out.append({
            'path': 'slack/' + channel_name,
            'start': index,
            'end': index,
            'text': '\n'.join(lines),
            'symbols': channel_name,
            'split': len(blocks) > 1,
            'url': permalink(workspace, channel_id, (started or {}).get('ts', '')),
        })
    return out
