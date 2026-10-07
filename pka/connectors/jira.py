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
FIELDS = 'summary,description,status,issuetype,priority,labels,assignee,reporter,created,updated,comment,parent'

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
        return node.get('text', '')
    if kind == 'hardBreak':
        return '\n'
    inner = adf_text(node.get('content'))
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
        if path not in {MYSELF, PROJECTS, SEARCH, SEARCH_LEGACY}:
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
        while pages < LIMITS.jira_max_pages and len(collected) < LIMITS.jira_max_issues:
            params = {'jql': jql, 'maxResults': 50, 'fields': FIELDS}
            if token:
                params['nextPageToken'] = token
            try:
                body = await self._get(SEARCH, params)
            except SourceError as exc:
                if exc.code != 'jira':
                    raise
                # Older sites still serve the previous search endpoint.
                params.pop('nextPageToken', None)
                params['startAt'] = len(collected)
                body = await self._get(SEARCH_LEGACY, params)
            batch = body.get('issues', [])
            collected.extend(batch)
            token = body.get('nextPageToken', '')
            pages += 1
            if not batch or (not token and body.get('isLast', True)):
                break
        return collected[:LIMITS.jira_max_issues]


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
    comments = ((fields.get('comment') or {}).get('comments') or [])[:LIMITS.jira_max_comments]
    for comment in comments:
        author = ((comment.get('author') or {}).get('displayName') or 'someone').strip()
        text = adf_text(comment.get('body')).strip()
        if text:
            lines.append(f"Comment by {author} on {str(comment.get('created', ''))[:10]}: {text}")
    text = '\n'.join(lines)
    return {'path': 'jira/' + key, 'start': 1, 'end': 1,
            'text': text[:LIMITS.chunk_chars * 2], 'symbols': key + ' ' + str(fields.get('summary', '')),
            'split': len(text) > LIMITS.chunk_chars * 2,
            'url': site.rstrip('/') + '/browse/' + key}
