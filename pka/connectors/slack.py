"""Read-only Slack adapter. Lists the channels a token can see and reads the ones chosen.

Nothing here can post, edit, join or leave. Only allowlisted read methods are called, and the
host is fixed, so no caller can direct this at another address.

A channel is read only when it appears in the allowlist the user saved. The token can see more
than that, and the difference is the point: Slack decides what is reachable, the allowlist
decides what is actually read, and both have to agree before a message enters the index.
"""
import asyncio
import hashlib
import json
import re
import time
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from pka.config import LIMITS
from pka.connectors.base import SourceError

API = 'https://slack.com/api/'
LIST_METHOD = 'conversations.list'
HISTORY_METHOD = 'conversations.history'
REPLIES_METHOD = 'conversations.replies'
PERMALINK_METHOD = 'chat.getPermalink'

# Slack reports its own reasons. These are the ones worth translating for a reader.
REASONS = {
    'invalid_auth': 'The Slack token is not valid any more. Connect Slack again.',
    'token_revoked': 'The Slack token was revoked. Connect Slack again.',
    'account_inactive': 'That Slack account is no longer active.',
    'missing_scope': 'The Slack token is missing a reading permission. Connect Slack again.',
    'not_in_channel': 'Your account is not in that channel, so its messages cannot be read.',
    'channel_not_found': 'That channel no longer exists or is not visible to your account.',
    'access_denied': 'Slack no longer permits this read.',
    'no_permission': 'Slack no longer permits this read.',
    'token_expired': 'The Slack token expired. Connect Slack again.',
}


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,12}(?:\.\d{1,6})?', value):
        raise SourceError('slack', 'Slack returned an invalid message timestamp.')
    return value


def message_record(raw):
    """Keep only current text and identity, never a previous_message body or tombstone text."""
    if not isinstance(raw, dict):
        raise SourceError('slack', 'Slack returned an invalid message.')
    subtype = raw.get('subtype')
    if subtype in {'message_deleted', 'tombstone'}:
        return {'ts':timestamp(raw.get('deleted_ts') or raw.get('ts')), 'deleted':True}
    if subtype == 'message_changed':
        raw = raw.get('message')
        if not isinstance(raw, dict):
            raise SourceError('slack', 'Slack returned an unreadable message edit.')
    ts = timestamp(raw.get('ts'))
    if raw.get('hidden') or raw.get('subtype') in {'channel_join', 'channel_leave'}:
        return {'ts':ts, 'excluded':True}
    text = raw.get('text', '')
    if text is None:
        text = ''
    if not isinstance(text, str):
        raise SourceError('slack', 'Slack returned unreadable message text.')
    thread = timestamp(raw['thread_ts']) if raw.get('thread_ts') else ts
    edit = raw.get('edited') or {}
    if not isinstance(edit, dict):
        raise SourceError('slack', 'Slack returned unreadable edit information.')
    edited = raw.get('edited_ts') or edit.get('ts', '')
    if edited:
        timestamp(edited)
    count = raw.get('reply_count', 0)
    if type(count) is not int or count < 0:
        raise SourceError('slack', 'Slack returned an invalid reply count.')
    return {'ts':ts, 'text':text.strip(), 'user':raw.get('user') or '', 'bot_id':raw.get('bot_id') or '',
            'thread_ts':thread, 'edited_ts':edited, 'reply_count':count,
            'in_thread':thread != ts or bool(raw.get('in_thread'))}


def snapshot(messages):
    """Versioned digest of imported content and thread relationships, excluding UI links."""
    fields = ('ts','text','user','bot_id','thread_ts','edited_ts','reply_count','in_thread')
    records = [{key:m.get(key) for key in fields} for m in messages]
    records.sort(key=lambda m:Decimal(m['ts']))
    return hashlib.sha256(json.dumps({'version':2, 'messages':records}, sort_keys=True).encode()).hexdigest()


class SlackSource:
    """Lists and reads Slack conversations with a user token."""

    def __init__(self, token: str, transport=None):
        if not token:
            raise SourceError('slack', 'Connect Slack before reading messages.')
        self.token = token
        self.transport = transport

    async def _get(self, method: str, params: dict) -> dict:
        if method not in {LIST_METHOD, HISTORY_METHOD, REPLIES_METHOD, PERMALINK_METHOD}:
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
                    try:
                        wait = max(0, int(response.headers.get('retry-after', '5') or 5))
                    except ValueError:
                        wait = 60
                    if wait <= 10 and attempt < 2:
                        await asyncio.sleep(wait)
                        continue
                    raise SourceError('rate_limit', f'Slack asked us to wait {wait} seconds. Try again shortly.')
                if response.status_code in {401, 403, 404}:
                    raise SourceError('access_denied', 'Slack no longer permits this history request.')
                if response.status_code != 200:
                    raise SourceError('slack', f'Slack returned HTTP {response.status_code}.')
                try:
                    body = response.json()
                except ValueError:
                    raise SourceError('slack', 'Slack returned an unreadable response.') from None
                if not isinstance(body, dict):
                    raise SourceError('slack', 'Slack returned an unreadable response.')
                if not body.get('ok'):
                    code = str(body.get('error', 'unknown'))
                    raise SourceError('access_denied' if code in REASONS else 'stale_source' if code == 'thread_not_found' else 'slack',
                                      REASONS.get(code, 'Slack refused the request: ' + code + '.'))
                return body
        raise SourceError('network', 'Slack request failed.')

    async def check_channel_access(self, channel_id: str, snapshot_digest: str = '') -> dict:
        if snapshot_digest:
            if not re.fullmatch(r'[0-9a-f]{64}', snapshot_digest):
                raise SourceError('stale_source', 'Read Slack again to record a current message snapshot.')
            messages = await self.messages(channel_id)
            if not self.last_coverage['verification_safe']:
                raise SourceError('access_unverified', 'Slack messages could not all be rechecked. Retry after the reported read gap is resolved.')
            current = snapshot(messages)
            if current != snapshot_digest:
                raise SourceError('stale_source', 'Slack messages or replies changed or left the readable import window. Read Slack again before using saved content.')
            return {'channel':channel_id, 'readable':True, 'snapshot':current}
        # A successful channel listing does not establish permission to read its history.
        # Discard the probe message; this call never updates the saved snapshot.
        body = await self._get(HISTORY_METHOD, {'channel': channel_id, 'limit': 1})
        if not isinstance(body.get('messages'), list):
            raise SourceError('slack', 'Slack history access could not be verified.')
        return {'channel': channel_id, 'readable': True}

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
        """Read a bounded current snapshot, paging each selected thread and deduplicating IDs."""
        collected, cursor, pages, seen_cursors = {}, '', 0, set()
        deleted, hidden, skipped, notes = set(), set(), set(), []
        safe, history_incomplete = True, False

        def merge(target, raw, thread=''):
            message = message_record(raw)
            ts = message['ts']
            if message.get('deleted'):
                deleted.add(ts)
                target.pop(ts, None)
            elif message.get('excluded'):
                skipped.add(ts)
                hidden.add(ts)
                target.pop(ts, None)
            elif ts not in deleted and ts not in hidden:
                if thread and ts != thread:
                    if message['thread_ts'] not in {ts, thread}:
                        raise SourceError('slack', 'A Slack reply referred to a different thread.')
                    message.update(thread_ts=thread, in_thread=True)
                previous = target.get(ts)
                if previous and previous != message:
                    old_edit, new_edit = Decimal(previous['edited_ts'] or '0'), Decimal(message['edited_ts'] or '0')
                    if old_edit > new_edit:
                        return
                    if old_edit == new_edit and any(previous[k] != message[k] for k in ('text','user','bot_id','thread_ts')):
                        raise SourceError('slack', 'Slack returned inconsistent versions of one message. Read again.')
                target[ts] = message

        while pages < LIMITS.slack_max_pages and len(collected) < LIMITS.slack_max_messages:
            params = {'channel': channel_id, 'limit': 200}
            if cursor:
                params['cursor'] = cursor
            if oldest:
                params['oldest'] = oldest
            body = await self._get(HISTORY_METHOD, params)
            batch = body.get('messages')
            if not isinstance(batch, list):
                raise SourceError('slack', 'Slack returned an unreadable message page.')
            for position, message in enumerate(batch):
                merge(collected, message)
                if len(collected) >= LIMITS.slack_max_messages:
                    history_incomplete |= position + 1 < len(batch)
                    break
            cursor = self._cursor(body)
            pages += 1
            more = bool(body.get('has_more') or cursor)
            if not more:
                break
            if (not cursor or cursor in seen_cursors or pages >= LIMITS.slack_max_pages
                    or len(collected) >= LIMITS.slack_max_messages):
                history_incomplete = True
                safe &= bool(cursor) and cursor not in seen_cursors
                break
            seen_cursors.add(cursor)
        # Broadcast replies can appear in history even when their root is outside the window.
        roots = sorted({m['thread_ts'] for m in collected.values() if m['reply_count'] or m['in_thread']}, key=Decimal)
        all_messages = dict(collected)
        threads = failed_threads = skipped_threads = truncated_threads = reply_pages = 0
        reply_total = 0
        for root in roots:
            if threads >= LIMITS.slack_max_threads or reply_total >= LIMITS.slack_max_channel_replies:
                skipped_threads += 1
                continue
            threads += 1
            thread, cursor, seen = {}, '', set()
            incomplete, thread_pages, thread_failed = False, 0, False
            expected = collected.get(root, {}).get('reply_count', 0)
            remaining = min(LIMITS.slack_max_replies, LIMITS.slack_max_channel_replies-reply_total)
            while thread_pages < LIMITS.slack_max_reply_pages:
                params = {'channel':channel_id, 'ts':root, 'limit':min(200, remaining+1)}
                if cursor:
                    params['cursor'] = cursor
                try:
                    body = await self._get(REPLIES_METHOD, params)
                except SourceError as exc:
                    if exc.code in {'access_denied','stale_source'}:
                        raise
                    failed_threads += 1; safe = False; thread_failed = True
                    notes.append(f'Thread {root}: {exc}')
                    break
                replies = body.get('messages')
                if not isinstance(replies, list):
                    raise SourceError('slack', 'Slack returned an unreadable reply page.')
                for position, reply in enumerate(replies):
                    merge(thread, reply, root)
                    if len([ts for ts in thread if ts != root]) >= remaining:
                        incomplete |= position+1 < len(replies)
                        break
                thread_pages += 1; reply_pages += 1
                cursor = self._cursor(body)
                more = bool(body.get('has_more') or cursor)
                if not more:
                    break
                if (not cursor or cursor in seen or thread_pages >= LIMITS.slack_max_reply_pages
                        or len([ts for ts in thread if ts != root]) >= remaining):
                    incomplete = True
                    safe &= bool(cursor) and cursor not in seen
                    break
                seen.add(cursor)
            if thread_failed:
                # A failed page cannot leave a misleading fragment of this new thread.
                for ts in list(all_messages):
                    if ts != root and all_messages[ts]['thread_ts'] == root:
                        del all_messages[ts]
                continue
            if root in thread:
                expected = thread[root]['reply_count'] or expected
                # The root from replies is newer than the history read, including an edit.
                all_messages[root] = thread[root]
            elif root not in deleted:
                safe = False; incomplete = True
                notes.append(f'Thread {root}: the parent message was not returned.')
            replies = [m for ts,m in thread.items() if ts != root]
            if len(replies) < expected and not incomplete:
                safe = False; incomplete = True
            if incomplete:
                truncated_threads += 1
            for message in replies:
                all_messages[message['ts']] = message
            reply_total += len(replies)
        for ts in deleted | hidden:
            all_messages.pop(ts, None)
        # Keep a thread together and ordered; never duplicate a broadcast reply.
        ordered = sorted(all_messages.values(), key=lambda m:(Decimal(m['thread_ts']), Decimal(m['ts'])))
        out = [m for m in ordered if m['text']]
        skipped.update(m['ts'] for m in ordered if not m['text'])
        if history_incomplete:
            notes.append('Channel history is incomplete: a message/page limit or pagination gap stopped the read.')
        if failed_threads:
            notes.append(f'{failed_threads} thread(s) could not be read.')
        if skipped_threads:
            notes.append(f'{skipped_threads} thread(s) were skipped at the thread limit.')
        if truncated_threads:
            notes.append(f'{truncated_threads} thread(s) have additional replies that were not read.')
        self.last_coverage = {'state':'partial' if notes else 'complete', 'notes':notes,
            'history_messages':sum(not m['in_thread'] for m in out), 'replies':sum(m['in_thread'] for m in out), 'pages':pages,
            'reply_pages':reply_pages, 'threads_read':threads, 'edited_messages':sum(bool(m['edited_ts']) for m in out),
            'deleted_events':len(deleted), 'excluded_events':len(skipped), 'threads_failed':failed_threads,
            'threads_skipped':skipped_threads, 'threads_truncated':truncated_threads,
            'verification_safe':bool(safe),
            'oldest':min((m['ts'] for m in out), key=Decimal) if out else None,
            'newest':max((m['ts'] for m in out), key=Decimal) if out else None}
        return out

    @staticmethod
    def _cursor(body):
        metadata = body.get('response_metadata') or {}
        if not isinstance(metadata, dict) or not isinstance(metadata.get('next_cursor', ''), str):
            raise SourceError('slack', 'Slack returned unreadable pagination information.')
        return metadata.get('next_cursor', '').strip()

    async def read_channel(self, channel_id: str) -> dict:
        messages = await self.messages(channel_id)
        # One read resolves the actual workspace domain, including when it was not configured.
        if messages:
            try:
                response = await self._get(PERMALINK_METHOD, {'channel':channel_id, 'message_ts':messages[0]['ts']})
                link = urlsplit(response.get('permalink') or '')
                if (link.scheme == 'https' and re.fullmatch(r'[a-zA-Z0-9-]+\.slack\.com', link.netloc)
                        and link.path == urlsplit(permalink(link.netloc[:-10], channel_id, messages[0]['ts'])).path):
                    for message in messages:
                        message['permalink'] = permalink(link.netloc[:-10], channel_id, message['ts'])
                else:
                    self.last_coverage['notes'].append('Message permalinks were unavailable.')
            except (ValueError, SourceError) as exc:
                if isinstance(exc, SourceError) and exc.code in {'access_denied','stale_source'}:
                    raise
                self.last_coverage['notes'].append('Message permalinks were unavailable; the text read was preserved.')
        return {'messages':messages, 'coverage':self.last_coverage, 'snapshot':snapshot(messages)}


def permalink(workspace: str, channel_id: str, ts: str) -> str:
    """Rebuild a message link without a second request. Slack's own format."""
    if not re.fullmatch(r'[a-zA-Z0-9-]+', workspace or '') or not re.fullmatch(r'[A-Za-z0-9]+', channel_id):
        return ''
    whole, _, fraction = timestamp(str(ts)).partition('.')
    return f"https://{workspace}.slack.com/archives/{channel_id}/p{whole}{fraction.ljust(6, '0')}"


def transcript(channel_name: str, messages: list, workspace: str, channel_id: str) -> list:
    """One message identity per excerpt, splitting long text without losing its provenance."""
    out = []
    for raw in messages:
        message = message_record(raw)
        if message.get('deleted') or message.get('excluded') or not message.get('text'):
            continue
        # Already-normalized records carry edited_ts instead of Slack's nested edited field.
        message['edited_ts'] = raw.get('edited_ts') or message['edited_ts']
        stamp = time.strftime('%Y-%m-%d %H:%M', time.localtime(float(message.get('ts', 0) or 0)))
        who = message.get('user') or message.get('bot_id') or 'unknown'
        prefix = '    reply ' if message.get('in_thread') else ''
        header = f'{prefix}[{stamp}] {who}: '
        text, pieces = message['text'], []
        size = max(200, LIMITS.chunk_chars-len(header))
        while text:
            end = min(len(text), size)
            if end < len(text):
                boundary = max(text.rfind('\n', size//2, end), text.rfind(' ', size//2, end))
                if boundary >= 0:
                    end = boundary+1
            pieces.append(text[:end]); text = text[end:]
        link = raw.get('permalink') or permalink(workspace, channel_id, message['ts'])
        for part, piece in enumerate(pieces, 1):
            index = len(out)+1
            out.append({'path':'slack/'+channel_name, 'start':index, 'end':index,
                'text':header+piece, 'symbols':channel_name, 'split':len(pieces)>1, 'url':link,
                'metadata':{'version':2, 'channel_id':channel_id, 'ts':message['ts'],
                    'thread_ts':message['thread_ts'], 'edited_ts':message['edited_ts'],
                    'author':who, 'header':header, 'part':part, 'parts':len(pieces)}})
    return out
