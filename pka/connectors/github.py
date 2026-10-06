"""Fixed-host GET-only GitHub adapter. No arbitrary URL, shell or write tool."""
import asyncio
import base64
from collections import deque
from pathlib import PurePosixPath
import re
import time
from urllib.parse import quote
import httpx
from pka import applog
from pka.config import LIMITS, validate_selection
from pka.connectors.base import SourceError

EXTENSIONS = {'.py','.js','.jsx','.ts','.tsx','.java','.go','.rs','.cs','.php','.rb',
              '.c','.h','.cpp','.hpp','.kt','.swift','.vue','.svelte','.sql','.md','.mdx',
              '.rst','.txt','.html','.css','.scss','.json','.toml','.yaml','.yml','.ini',
              '.xml','.sh','.ps1','.bat','.graphql','.gql','.tf','.gradle','.properties'}
NAMES = {'dockerfile','makefile','procfile','gemfile','rakefile','license','readme'}
EXCLUDED_DIRS = {'node_modules','vendor','.git','.venv','venv','dist','build','coverage',
                 '__pycache__','.next','.idea','.vscode','target','bin','obj'}


def dependency_dir(path: str) -> bool:
    """True when this directory is itself a dependency or generated directory."""
    return any(x.lower() in EXCLUDED_DIRS for x in PurePosixPath(path).parts)


def dependency_path(path: str) -> bool:
    """True when this file sits inside a dependency or generated directory."""
    return any(x.lower() in EXCLUDED_DIRS for x in PurePosixPath(path).parts[:-1])


def exclusion(path: str, size: int, mode: str = '100644') -> str:
    p = PurePosixPath(path)
    if path.startswith('/') or '\\' in path or '..' in p.parts:
        return 'unsafe_path'
    if mode not in {'100644','100755'}:
        return 'symlink_or_submodule'
    if any(x.lower() in EXCLUDED_DIRS for x in p.parts[:-1]):
        return 'generated_or_dependency_directory'
    name = p.name.lower()
    if (name.startswith('.env') or name in {'id_rsa','id_ed25519','.npmrc','.pypirc'}
        or any(x in name for x in ('credential','secret')) or p.suffix.lower() in {'.pem','.key','.p12','.pfx'}):
        return 'potential_secret_file'
    if name.endswith(('.lock','-lock.json','.min.js','.min.css','.map')) or name in {'package-lock.json','yarn.lock'}:
        return 'generated_or_lock_file'
    if p.suffix.lower() not in EXTENSIONS and name not in NAMES:
        return 'unsupported_type'
    if size > LIMITS.max_file_bytes:
        return 'file_size_limit'
    return ''


class GitHubSource:
    def __init__(self, repo: str, branch: str, token: str = '', transport=None):
        self.repo, self.branch = validate_selection(repo, branch)
        self.token = token
        self.transport = transport
        self.commit = ''
        self.entries = []
        self.allowed = {}
        self.truncated = False

    async def _get(self, path: str, params=None):
        # All callers construct paths; callers never supply an arbitrary URL.
        headers = {'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',
                   'User-Agent':'ProjectKnowledgeAssistant/0.1'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        url = 'https://api.github.com/repos/' + self.repo + '/' + path
        async with httpx.AsyncClient(transport=self.transport, timeout=30, follow_redirects=False, trust_env=False) as client:
            for attempt in range(3):
                t0 = time.perf_counter()
                try:
                    r = await client.get(url, headers=headers, params=params)
                except httpx.RequestError:
                    if attempt == 2:
                        raise SourceError('network', 'GitHub could not be reached. Check your connection and retry.') from None
                    await asyncio.sleep(2 ** attempt)
                    continue
                limited = r.status_code == 429 or (r.status_code == 403 and (
                    r.headers.get('x-ratelimit-remaining') == '0' or 'retry-after' in r.headers))
                if limited:
                    try:
                        wait = float(r.headers.get('retry-after', '0'))
                        if wait <= 0:
                            wait = max(1, float(r.headers.get('x-ratelimit-reset', time.time()+60)) - time.time())
                    except ValueError:
                        wait = 60
                    if wait <= 5 and attempt < 2:
                        await asyncio.sleep(max(1, wait))
                        continue
                    applog.failure('github.rate_limited', path=path, wait_s=int(wait),
                                   limit=r.headers.get('x-ratelimit-limit'))
                    raise SourceError('rate_limit', f'GitHub rate limit reached. Retry in approximately {max(1, int(wait))} seconds.')
                if r.status_code in {401,403,404}:
                    applog.failure('github.denied', path=path, status=r.status_code,
                                   token='configured' if self.token else 'none')
                    raise SourceError('access_denied', 'Repository, branch or commit is unavailable. Check selection, token expiry and Contents read permission.')
                if r.status_code >= 500 and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if r.status_code != 200:
                    applog.failure('github.http', path=path, status=r.status_code)
                    raise SourceError('github_http', f'GitHub returned HTTP {r.status_code}. No snapshot was accepted.')
                applog.event('github.request', path=path[:80], status=r.status_code,
                             remaining=r.headers.get('x-ratelimit-remaining'),
                             limit=r.headers.get('x-ratelimit-limit'),
                             ms=int((time.perf_counter()-t0)*1000))
                try:
                    return r.json()
                except ValueError:
                    raise SourceError('invalid_response', 'GitHub returned an invalid response.') from None
        raise SourceError('network', 'GitHub request failed.')

    async def rate_budget(self) -> dict:
        """Read the remaining request allowance. This endpoint does not consume quota itself.

        Returns an empty dict when the allowance cannot be read, so a scan is never blocked by
        the check failing.
        """
        headers = {'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',
                   'User-Agent':'ProjectKnowledgeAssistant/0.1'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        async with httpx.AsyncClient(transport=self.transport, timeout=30, follow_redirects=False, trust_env=False) as client:
            try:
                r = await client.get('https://api.github.com/rate_limit', headers=headers)
            except httpx.RequestError:
                return {}
            if r.status_code != 200:
                return {}
            try:
                core = r.json()['resources']['core']
                return {'limit':int(core['limit']),'remaining':int(core['remaining']),'reset':int(core['reset'])}
            except (ValueError, KeyError, TypeError):
                return {}

    async def check_access(self, commit: str = '') -> dict:
        result = await self._get('commits/' + quote(self.branch, safe=''))
        head = result.get('sha', '')
        if not re.fullmatch('[0-9a-f]{40}', head):
            raise SourceError('invalid_response', 'GitHub did not return a valid commit.')
        if commit and commit != head:
            if not re.fullmatch('[0-9a-f]{40}', commit):
                raise SourceError('scope', 'Invalid commit identifier.')
            await self._get('commits/' + commit)
        return {'head':head, 'repo':self.repo, 'branch':self.branch}

    async def begin_snapshot(self) -> dict:
        result = await self._get('commits/' + quote(self.branch, safe=''))
        self.commit = result['sha']
        if not re.fullmatch('[0-9a-f]{40}', self.commit):
            raise SourceError('invalid_response', 'Invalid commit returned.')
        root = result['commit']['tree']['sha']
        tree = await self._get('git/trees/' + root, {'recursive':'1'})
        entries = tree.get('tree', [])
        self.truncated = False
        self.dependency_files = 0
        if tree.get('truncated'):
            # Trees do not have page numbers. Traverse non-recursive subtrees when truncated.
            entries = []
            queue = deque([('',root)])
            requests = 0
            while queue and len(entries) < LIMITS.max_entries and requests < LIMITS.max_tree_requests:
                prefix, sha = queue.popleft()
                part = await self._get('git/trees/' + sha)
                requests += 1
                self.truncated |= bool(part.get('truncated'))
                for e in part.get('tree', []):
                    e = {**e, 'path':prefix + e['path']}
                    if e['type'] == 'tree':
                        # Do not spend tree requests inside node_modules, .venv and friends.
                        if not dependency_dir(e['path']):
                            queue.append((e['path']+'/',e['sha']))
                        continue
                    if dependency_path(e['path']):
                        self.dependency_files += 1
                        continue
                    if len(entries) >= LIMITS.max_entries:
                        self.truncated = True
                        break
                    entries.append(e)
            self.truncated |= bool(queue)
        # Discard dependency directories before applying the entry cap. GitHub returns the tree
        # in path order, so a repository that commits .venv or node_modules would otherwise spend
        # the whole cap on files that are excluded anyway and the real source, which sorts later,
        # would never be reached.
        self.entries = []
        self.allowed = {}
        for e in entries:
            if e['type'] == 'tree':
                continue
            if dependency_path(e['path']):
                self.dependency_files += 1
                continue
            if len(self.entries) >= LIMITS.max_entries:
                self.truncated = True
                break
            item = {'path':e['path'],'size':e.get('size',0),'sha':e['sha'],
                    'skip':exclusion(e['path'], e.get('size',0), e.get('mode',''))}
            self.entries.append(item)
            if not item['skip']:
                self.allowed[item['path']] = item
        self.entries.sort(key=lambda x: (0 if PurePosixPath(x['path']).name.lower().startswith('readme') else 1, x['path']))
        # One request per readable file. Check the allowance before spending any of it, so an
        # allowance that cannot cover the scan is reported instead of being used up on a
        # partial index that is then discarded.
        needed = min(len(self.allowed), LIMITS.max_files)
        budget = await self.rate_budget()
        applog.event('github.snapshot', commit=self.commit[:12], candidates=len(self.entries),
                     readable=len(self.allowed), dependency_files=self.dependency_files,
                     truncated=self.truncated, needed=needed,
                     remaining=budget.get('remaining'), limit=budget.get('limit'))
        if budget and budget['remaining'] < needed:
            minutes = max(1, int((budget['reset'] - time.time()) // 60) + 1)
            advice = ('Add a read-only GITHUB_TOKEN to .env and restart to raise the hourly allowance to 5000, '
                      'or wait for the reset.') if budget['limit'] <= 60 else 'Wait for the reset, then scan again.'
            raise SourceError('rate_limit',
                              f'This scan needs about {needed} GitHub requests but {budget["remaining"]} of '
                              f'{budget["limit"]} remain for the next {minutes} minutes. ' + advice)
        return {'commit':self.commit,'entries':len(self.entries),'tree_incomplete':self.truncated,
                'dependency_files':self.dependency_files,'requests_needed':needed,
                'requests_remaining':budget.get('remaining'),'request_limit':budget.get('limit')}

    async def list_files(self, cursor: int = 0) -> dict:
        if not self.commit or cursor < 0:
            raise SourceError('scope', 'Start a snapshot before listing files.')
        end = cursor + 200
        return {'files':self.entries[cursor:end], 'next_cursor':end if end < len(self.entries) else None}

    async def read_file(self, path: str) -> dict:
        if path not in self.allowed:
            raise SourceError('scope', 'File is outside the selected snapshot or excluded by policy.')
        e = self.allowed[path]
        blob = await self._get('git/blobs/' + e['sha'])
        if blob.get('size',0) > LIMITS.max_file_bytes:
            return {'skip':'file_size_limit'}
        if blob.get('encoding') != 'base64':
            return {'skip':'unsupported_encoding'}
        try:
            content = base64.b64decode(blob['content'])
            if len(content) > LIMITS.max_file_bytes:
                return {'skip':'file_size_limit'}
            text = content.decode('utf-8-sig')
        except (ValueError, UnicodeError):
            return {'skip':'non_utf8'}
        if '\x00' in text:
            return {'skip':'binary'}
        if max((len(line) for line in text.splitlines()), default=0) > LIMITS.chunk_chars:
            return {'skip':'overlong_line'}
        return {'text':text,'bytes':len(content),'sha':e['sha']}
