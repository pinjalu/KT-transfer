"""Read-only Jira adapter. Lists the projects a token can see and reads the one chosen.

Nothing here can create, edit, transition or delete an issue. Only reading endpoints are ever
called, and the site address is checked before use so a mistyped or hostile value cannot point
this at a private network address.

A project is read only when its key matches the one saved. The account can usually see more
than that, and the difference is the point: Atlassian decides what is reachable, the saved key
decides what is actually read.
"""
import asyncio
import base64
import hashlib
import ipaddress
import re
from urllib.parse import urlparse

import httpx

from pka.config import LIMITS
from pka.connectors.base import SourceError

MYSELF = '/rest/api/3/myself'
PROJECTS = '/rest/api/3/project/search'
SEARCH = '/rest/api/3/search/jql'
SEARCH_LEGACY = '/rest/api/3/search'
FIELDS = 'summary,description,status,issuetype,priority,labels,assignee,reporter,created,updated,comment,parent,*all'

REASONS = {
    401: 'Jira rejected the email and API token. Check that the token was created by the same '
         'Atlassian account as the email, and that it has not been revoked.',
    403: 'That Atlassian account is not allowed to read this project.',
    404: 'That Jira site or project could not be found.',
}


def check_site(site: str) -> str:
    """Accept only a plain https address, so this can never be aimed at a private address."""
    site = (site or '').strip().rstrip('/')
    parsed = urlparse(site)
    if parsed.scheme != 'https' or not parsed.netloc:
        raise SourceError('jira', 'The Jira site must be a full https address, such as '
                                  'https://yourcompany.atlassian.net.')
    if parsed.path or parsed.query:
        raise SourceError('jira', 'Give the Jira site address only, with no path after it.')
    host = parsed.hostname or ''
    if '.' not in host:
        raise SourceError('jira', 'That does not look like a Jira site address.')
    try:
        if ipaddress.ip_address(host).is_private:
            raise SourceError('jira', 'A private network address cannot be used as a Jira site.')
    except ValueError:
        pass
    if host in {'localhost'} or host.endswith('.local'):
        raise SourceError('jira', 'A local address cannot be used as a Jira site.')
    return site


def adf_text(node) -> str:
    """Flatten Atlassian's rich document format into plain readable lines."""
    if node is None:
        return ''
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return ''.join(adf_text(x) for x in node)
    if not isinstance(node, dict):
        return ''
    kind = node.get('type')
    if kind == 'text':
        text = node.get('text', '')
        for mark in node.get('marks') or []:
            link = (mark.get('attrs') or {}).get('href') if mark.get('type') == 'link' else None
            if link and link != text:
                text += ' (' + link + ')'
        return text
    if kind == 'hardBreak':
        return '\n'
    inner = adf_text(node.get('content'))
    if kind in {'tableCell', 'tableHeader'}:
        return inner.strip() + '\t'
    if kind in {'inlineCard', 'blockCard'}:
        return str((node.get('attrs') or {}).get('url') or '')
    if kind in {'media', 'mediaInline'}:
        return '[Attachment content not imported]'
    if kind in {'paragraph', 'heading', 'listItem', 'blockquote', 'codeBlock', 'tableRow'}:
        return inner.rstrip() + '\n'
    if kind == 'mention':
        return '@' + (node.get('attrs') or {}).get('text', 'someone')
    return inner


class JiraSource:
    """Lists and reads Jira issues with an account's API token."""

    def __init__(self, site: str, email: str, token: str, transport=None):
        if not (site and email and token):
            raise SourceError('jira', 'Add the Jira site, email and API token before reading.')
        self.site = check_site(site)
        self.transport = transport
        self.auth = base64.b64encode(f'{email}:{token}'.encode()).decode()

    async def _get(self, path: str, params=None) -> dict:
        if path not in {MYSELF, PROJECTS, SEARCH, SEARCH_LEGACY} and not re.fullmatch(
                r'/rest/api/3/issue/[A-Za-z][A-Za-z0-9_]{0,40}-[0-9]+/comment', path):
            raise SourceError('jira', 'That Jira endpoint is not permitted.')
        headers = {'Authorization': 'Basic ' + self.auth, 'Accept': 'application/json',
                   'User-Agent': 'ProjectKnowledgeAssistant/0.1'}
        async with httpx.AsyncClient(transport=self.transport, timeout=30,
                                     follow_redirects=False, trust_env=False) as client:
            for attempt in range(3):
                try:
                    response = await client.get(self.site + path, headers=headers, params=params)
                except httpx.RequestError:
                    if attempt == 2:
                        raise SourceError('network', 'Jira could not be reached. Check your connection.') from None
                    await asyncio.sleep(2 ** attempt)
                    continue
                if response.status_code == 429:
                    wait = int(response.headers.get('retry-after', '5') or 5)
                    if wait <= 10 and attempt < 2:
                        await asyncio.sleep(wait)
                        continue
                    raise SourceError('rate_limit', f'Jira asked us to wait {wait} seconds. Try again shortly.')
                if response.status_code in REASONS:
                    raise SourceError('access_denied', REASONS[response.status_code])
                # An unauthenticated request to a listing comes back as 200 with nothing in it,
                # so without this header an empty result is indistinguishable from a refusal.
                if response.headers.get('x-seraph-loginreason') == 'AUTHENTICATED_FAILED':
                    raise SourceError('access_denied', REASONS[401])
                if response.status_code >= 500 and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if response.status_code != 200:
                    raise SourceError('jira', f'Jira returned HTTP {response.status_code}.')
                try:
                    return response.json()
                except ValueError:
                    raise SourceError('jira', 'Jira returned an unreadable response.') from None
        raise SourceError('network', 'Jira request failed.')

    async def check_access(self) -> dict:
        """Confirm the credentials actually sign in, before anything else is believed.

        Jira answers a listing from an anonymous caller with an empty list and a 200, so an
        empty result on its own means nothing. This endpoint refuses outright instead.
        """
        me = await self._get(MYSELF)
        return {'name': me.get('displayName', ''), 'account': me.get('accountId', '')}

    async def projects(self) -> list:
        """Every project this account can see. Reading one still needs its key to be saved."""
        await self.check_access()
        found, start, pages = [], 0, 0
        while pages < LIMITS.jira_max_pages:
            body = await self._get(PROJECTS, {'maxResults': 50, 'startAt': start})
            for project in body.get('values', []):
                found.append({'key': project.get('key', ''), 'name': project.get('name', ''),
                              'type': project.get('projectTypeKey', '')})
            if body.get('isLast', True) or not body.get('values'):
                break
            start += len(body.get('values', []))
            pages += 1
        found.sort(key=lambda p: p['key'])
        return found

    async def issues(self, project_key: str) -> list:
        """Issues in one project, oldest first, with their comments."""
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,40}', project_key or ''):
            raise SourceError('jira', 'That project key could not be recognised.')
        # The key is checked above, so it cannot carry anything into the query.
        jql = f'project = "{project_key}" ORDER BY created ASC'
        collected, token, pages = [], '', 0
        legacy, incomplete, uncertain = False, False, False
        seen_tokens = set()
        while pages < LIMITS.jira_max_pages and len(collected) < LIMITS.jira_max_issues:
            params = {'jql': jql, 'maxResults': 50, 'fields': FIELDS, 'expand':'names'}
            if legacy:
                params['startAt'] = len(collected)
            elif token:
                params['nextPageToken'] = token
            try:
                body = await self._get(SEARCH_LEGACY if legacy else SEARCH, params)
            except SourceError as exc:
                if exc.code != 'jira':
                    raise
                # Older sites still serve the previous search endpoint.
                params.pop('nextPageToken', None)
                params['startAt'] = len(collected)
                body = await self._get(SEARCH_LEGACY, params)
                legacy = True
            batch = body.get('issues')
            if not isinstance(batch, list):
                raise SourceError('jira', 'Jira returned an unreadable issue page.')
            room = LIMITS.jira_max_issues - len(collected)
            for issue in batch[:room]:
                await self.complete_issue(issue, project_key, body.get('names'))
                collected.append(issue)
            incomplete |= len(batch) > room
            token = body.get('nextPageToken', '')
            pages += 1
            if legacy and isinstance(body.get('total'), int):
                more = params['startAt'] + len(batch) < body['total']
            else:
                more = bool(token) or body.get('isLast') is False
                uncertain |= 'isLast' not in body and not token
            if not more:
                break
            if (not batch or pages >= LIMITS.jira_max_pages or len(collected) >= LIMITS.jira_max_issues
                    or (not legacy and (not token or token in seen_tokens))):
                incomplete = True
                break
            seen_tokens.add(token)
        missing_comments = unknown_comments = comments = 0
        for issue in collected:
            field = (issue.get('fields') or {}).get('comment') or {}
            included = (field.get('comments') or [])[:LIMITS.jira_max_comments]
            comments += len(included)
            total = field.get('total')
            if len(field.get('comments') or []) > len(included) or (isinstance(total, int) and total > len(included)):
                missing_comments += 1
            elif not isinstance(total, int):
                unknown_comments += 1
        shortened = sum(bool(issue_block(self.site, issue)['truncated']) for issue in collected)
        notes = []
        if incomplete:
            notes.append('More issues may exist: an issue/page limit or pagination gap stopped the read.')
        if missing_comments:
            notes.append(f'{missing_comments} issue(s) have comments that were not included.')
        if shortened:
            notes.append(f'{shortened} issue(s) had text shortened to the per-issue size limit.')
        partial = bool(notes)
        if unknown_comments:
            notes.append(f'Comment totals were not supplied for {unknown_comments} issue(s); comment coverage is unknown.')
        if uncertain:
            notes.append('Jira did not confirm the final issue page; issue coverage is unknown.')
        self.last_coverage = {'state':'partial' if partial else 'unknown' if notes else 'complete',
            'notes':notes, 'issues':len(collected), 'pages':pages, 'comments':comments,
            'issues_missing_comments':missing_comments, 'issues_shortened':shortened,
            'custom_text_fields':sum(len(custom_text_fields(i)) for i in collected),
            'comment_pages':sum(i.get('_comment_pages', 0) for i in collected)}
        return collected

    async def complete_issue(self, issue, project_key, names=None):
        """Finish visible comments; never follow URLs supplied by a Jira response."""
        key = issue.get('key', '')
        if not re.fullmatch(re.escape(project_key) + r'-[0-9]+', key, re.I):
            raise SourceError('scope', 'Jira returned an issue outside the selected project.')
        issue['_field_names'] = {**(names or {}), **(issue.get('names') or {})}
        fields = issue.get('fields')
        if not isinstance(fields, dict):
            raise SourceError('jira', 'Jira returned unreadable issue fields.')
        field = fields.get('comment') or {}
        embedded, total = field.get('comments'), field.get('total')
        # A complete embedded page avoids an unnecessary request. Missing totals are
        # never treated as proof that the embedded comments are the complete set.
        if (isinstance(embedded, list) and type(total) is int and total >= 0
                and field.get('startAt', 0) == 0 and len(embedded) == total):
            return
        comments, seen, start, previous_total = [], set(), 0, None
        for page in range(LIMITS.jira_max_comment_pages):
            body = await self._get(f'/rest/api/3/issue/{key}/comment',
                {'startAt':start, 'maxResults':min(100, LIMITS.jira_max_comments-len(comments)),
                 'orderBy':'created'})
            batch, total = body.get('comments'), body.get('total')
            if not isinstance(batch, list) or body.get('startAt', start) != start:
                raise SourceError('jira', 'Jira returned an unreadable comment page.')
            if type(total) is int:
                if total < start + len(batch) or previous_total is not None and total != previous_total:
                    raise SourceError('jira', 'Jira comments changed during pagination. Retry the read.')
                previous_total = total
            for comment in batch:
                cid = comment.get('id')
                if cid is None or str(cid) in seen:
                    raise SourceError('jira', 'Jira comment pagination repeated or omitted an identifier. Retry the read.')
                seen.add(str(cid))
            comments.extend(batch[:LIMITS.jira_max_comments-len(comments)])
            issue['_comment_pages'] = page + 1
            start += len(batch)
            if type(total) is int and total >= 0 and start >= total:
                break
            if not batch or len(comments) >= LIMITS.jira_max_comments:
                break
        fields['comment'] = {'comments':comments, 'total':total, 'startAt':0}

    async def check_issues_access(self, project_key: str, issue_keys: list[str], snapshots=None) -> dict:
        """Check issue security and the continued visibility of saved issue/comment text."""
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,40}', project_key or ''):
            raise SourceError('scope', 'No valid Jira project was selected.')
        keys = sorted(set(issue_keys))
        if len(keys) > LIMITS.jira_max_issues or any(
                not re.fullmatch(re.escape(project_key) + r'-[0-9]+', key, re.I) for key in keys):
            raise SourceError('scope', 'An issue is outside the selected Jira project.')
        if snapshots is not None and (set(snapshots) != set(keys) or any(
                not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value)
                for value in snapshots.values())):
            raise SourceError('scope', 'Saved Jira content does not match the selected issues.')
        await self.check_access()  # Search can otherwise return an anonymous empty result.
        visible = set()
        for start in range(0, len(keys), 50):
            batch = keys[start:start+50]
            params = {'jql': 'project = "' + project_key + '" AND key IN (' +
                      ','.join('"'+key+'"' for key in batch) + ')',
                      'fields': FIELDS if snapshots is not None else 'key', 'maxResults': 50,
                      'expand':'names'}
            seen = set()
            while True:
                body = await self._get(SEARCH, params)
                if not isinstance(body.get('issues'), list):
                    raise SourceError('jira', 'Jira access could not be verified.')
                visible.update(i.get('key', '').upper() for i in body['issues'])
                if snapshots is not None:
                    for issue in body['issues']:
                        key = issue.get('key', '')
                        if key not in snapshots:
                            raise SourceError('jira', 'Jira access returned an unexpected issue.')
                        await self.complete_issue(issue, project_key, body.get('names'))
                        current = hashlib.sha256('\n'.join(
                            block['text'] for block in issue_blocks(self.site, issue)).encode()).hexdigest()
                        if current != snapshots[key]:
                            # Issue-level access alone cannot authorize a previously visible
                            # comment. A content or visibility change requires a new read.
                            raise SourceError('stale_source', 'Saved Jira content changed or is no longer fully visible. Read the project again.')
                token = body.get('nextPageToken')
                if not token:
                    if body.get('isLast') is False:
                        raise SourceError('jira', 'Jira access results were incomplete.')
                    break
                if token in seen or len(seen) >= LIMITS.jira_max_pages:
                    raise SourceError('jira', 'Jira access results were incomplete.')
                seen.add(token)
                params['nextPageToken'] = token
        if any(key.upper() not in visible for key in keys):
            raise SourceError('access_denied', 'A saved Jira issue was deleted or is no longer accessible. Read the project again.')
        return {'checked': len(keys)}


def custom_text_fields(issue):
    """Keep visible custom text under its actual Jira label, without assuming field IDs."""
    result = []
    names = issue.get('_field_names') or issue.get('names') or {}
    for key, value in sorted((issue.get('fields') or {}).items()):
        if not re.fullmatch(r'customfield_[0-9]+', key):
            continue
        if isinstance(value, str) or isinstance(value, dict) and value.get('type') == 'doc':
            text = adf_text(value).strip()
        elif isinstance(value, list) and all(isinstance(v, str) for v in value):
            text = '\n'.join(value).strip()
        else:
            continue
        if text:
            result.append((names.get(key) or key, text))
    return result


def issue_block(site: str, issue: dict) -> dict:
    """One issue as a readable block that cites its own Jira link."""
    fields = issue.get('fields') or {}
    key = issue.get('key', '')
    lines = [f"{key}: {fields.get('summary', '')}".strip()]
    status = ((fields.get('status') or {}).get('name') or '').strip()
    kind = ((fields.get('issuetype') or {}).get('name') or '').strip()
    priority = ((fields.get('priority') or {}).get('name') or '').strip()
    who = ((fields.get('assignee') or {}).get('displayName') or 'nobody').strip()
    reported = ((fields.get('reporter') or {}).get('displayName') or '').strip()
    lines.append(f"Type {kind or 'unknown'}, status {status or 'unknown'}, priority "
                 f"{priority or 'none'}, assigned to {who}.")
    if reported:
        lines.append(f"Reported by {reported} on {str(fields.get('created', ''))[:10]}.")
    labels = [str(x) for x in (fields.get('labels') or [])]
    if labels:
        lines.append('Labels: ' + ', '.join(labels) + '.')
    description = adf_text(fields.get('description')).strip()
    if description:
        lines.append('Description:')
        lines.append(description)
    for label, value in custom_text_fields(issue):
        lines.extend([label + ':', value])
    comments = ((fields.get('comment') or {}).get('comments') or [])[:LIMITS.jira_max_comments]
    for comment in comments:
        author = ((comment.get('author') or {}).get('displayName') or 'someone').strip()
        text = adf_text(comment.get('body')).strip()
        if text:
            lines.append(f"Comment by {author} on {str(comment.get('created', ''))[:10]}: {text}")
    text = '\n'.join(lines)
    return {'path': 'jira/' + key, 'start': 1, 'end': 1,
            'text': text[:LIMITS.jira_max_issue_chars], 'symbols': key + ' ' + str(fields.get('summary', '')),
            'split': len(text) > LIMITS.jira_max_issue_chars,
            'truncated': len(text) > LIMITS.jira_max_issue_chars,
            'url': site.rstrip('/') + '/browse/' + key}


def issue_blocks(site: str, issue: dict) -> list:
    """Index every retained character in bounded excerpts, all citing the same issue."""
    block = issue_block(site, issue)
    text = block['text']
    # Stable boundaries preserve ordinary words and all whitespace. A single very
    # long token still has to split to respect the retrieval context limit.
    result, offset = [], 0
    while offset < len(text):
        end = min(offset+LIMITS.chunk_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind('\n', offset+LIMITS.chunk_chars//2, end),
                           text.rfind(' ', offset+LIMITS.chunk_chars//2, end))
            if boundary >= 0:
                end = boundary + 1
        result.append({**block, 'text':text[offset:end],
                       'start':text.count('\n', 0, offset)+1,
                       'end':text.count('\n', 0, end)+1,
                       'split':len(text) > LIMITS.chunk_chars or block['split']})
        offset = end
    return result
