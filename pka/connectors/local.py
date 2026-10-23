"""Bounded, read-only snapshots of an explicitly selected folder. Never runs project code."""
import asyncio
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from pka.config import LIMITS
from pka.connectors.base import SourceError
from pka.connectors.github import dependency_dir, exclusion

PREFIX = 'local:'
PRIVATE_DIRS = {'.ssh', '.aws', '.azure', '.config', '.codex', '.agents', '.cache', '.npm', 'logs'}


def is_local(repo):
    return str(repo or '').startswith(PREFIX)


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _plain_path(path):
    # Include every ancestor, so a Windows junction cannot widen the selected scope.
    for part in reversed((path, *path.parents)):
        if _linked(part.lstat()):
            raise SourceError('access_denied', 'Linked folders, junctions and symbolic links are not read. Choose the actual folder.')


def local_selection(raw):
    text = raw.strip().strip('"\'').strip()
    if text.lower().startswith('file:'):
        parsed = urlsplit(text)
        if parsed.scheme.lower() != 'file' or parsed.netloc not in {'', 'localhost'} or parsed.query or parsed.fragment:
            raise ValueError('Use a local folder path or file:/// link on this computer.')
        text = unquote(parsed.path)
        if os.name == 'nt' and len(text) > 3 and text[0] == '/' and text[2] == ':':
            text = text[1:]
    if not text or '\x00' in text or text.startswith(('\\\\', '//')):
        raise ValueError('Choose a local folder on this computer. Network and device paths are not supported.')
    path = Path(text)
    if not path.is_absolute() or '..' in path.parts or (os.name == 'nt' and ':' in str(path)[2:]):
        raise ValueError('Enter an absolute folder path, such as D:\\Projects\\my-app.')
    try:
        _plain_path(path)
        if not path.is_dir() or path == Path(path.anchor):
            raise ValueError('Choose a project folder, not a file or an entire drive.')
        resolved = path.resolve(strict=True)
        if os.name == 'nt':
            # Mapped network drives are not local folders either.
            import ctypes
            if ctypes.windll.kernel32.GetDriveTypeW(str(resolved.anchor)) == 4:
                raise ValueError('Choose a folder on a local drive, not a mapped network drive.')
        return PREFIX + resolved.as_posix(), 'working-tree'
    except (OSError, SourceError):
        raise ValueError('The folder is unavailable or uses a symbolic link/junction. Choose an accessible actual folder.') from None


class LocalSource:
    def __init__(self, repo):
        if not is_local(repo):
            raise SourceError('scope', 'Select a local project folder first.')
        self.repo = repo
        self.root = Path(repo[len(PREFIX):])
        self.entries, self.allowed, self.commit = [], {}, ''

    def _root(self):
        try:
            _plain_path(self.root)
            if not self.root.is_absolute() or not self.root.is_dir() or self.root == Path(self.root.anchor):
                raise OSError()
        except OSError:
            raise SourceError('access_denied', 'The selected local folder is unavailable. Restore access or choose it again.') from None

    def _read(self, relative):
        parts = PurePosixPath(relative)
        if not relative or parts.is_absolute() or '..' in parts.parts or '\\' in relative or ':' in relative:
            raise SourceError('scope', 'File is outside the selected folder.')
        target = self.root.joinpath(*parts.parts)
        try:
            self._root()
            _plain_path(target)
            before = target.lstat()
            if not stat.S_ISREG(before.st_mode) or _linked(before):
                raise SourceError('scope', 'Only regular files in the selected folder are read.')
            reason = exclusion(relative, before.st_size)
            if reason:
                return {'skip':reason}
            with target.open('rb') as stream:
                opened = os.fstat(stream.fileno())
                _plain_path(target)
                if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                    raise SourceError('stale', 'A local file changed during the read. Refresh the folder.')
                content = stream.read(LIMITS.max_file_bytes + 1)
                after = os.fstat(stream.fileno())
                _plain_path(target)
                if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise SourceError('stale', 'A local file changed during the read. Refresh the folder.')
            if len(content) > LIMITS.max_file_bytes:
                return {'skip':'file_size_limit'}
            return {'content':content, 'bytes':len(content), 'sha':hashlib.sha256(content).hexdigest()}
        except OSError:
            raise SourceError('access_denied', 'A selected local file became unavailable. Check folder access and refresh.') from None

    def _snapshot(self):
        self._root()
        entries, pending, visited = [], [self.root], 0
        truncated = False
        while pending and not truncated:
            folder = pending.pop()
            try:
                _plain_path(folder)
                with os.scandir(folder) as children:
                    for child in children:
                        visited += 1
                        if visited > LIMITS.max_entries:
                            truncated = True
                            break
                        relative = Path(child.path).relative_to(self.root).as_posix()
                        info = child.stat(follow_symlinks=False)
                        if _linked(info):
                            entries.append({'path':relative, 'size':0, 'skip':'symlink_or_junction', 'sha':''})
                        elif stat.S_ISDIR(info.st_mode):
                            if not dependency_dir(relative) and child.name.lower() not in PRIVATE_DIRS:
                                pending.append(Path(child.path))
                        elif stat.S_ISREG(info.st_mode):
                            entries.append({'path':relative, 'size':info.st_size,
                                'skip':('reserved_source_path' if relative.startswith(('jira/', 'slack/'))
                                        else exclusion(relative, info.st_size)), 'sha':''})
            except OSError:
                raise SourceError('access_denied', 'A folder could not be listed. Check local folder access and refresh.') from None
        entries.sort(key=lambda e: (0 if PurePosixPath(e['path']).name.lower().startswith('readme') else 1, e['path']))
        used, count = 0, 0
        for entry in entries:
            if entry['skip']:
                continue
            if count >= LIMITS.max_files or used + entry['size'] > LIMITS.max_total_bytes:
                entry['skip'] = 'scan_size_limit'
                continue
            read = self._read(entry['path'])
            if read.get('skip'):
                entry['skip'] = read['skip']
                continue
            entry.update(size=read['bytes'], sha=read['sha'])
            used += read['bytes']
            count += 1
        digest = hashlib.sha256(json.dumps([str(self.root), truncated, entries], sort_keys=True).encode()).hexdigest()
        return digest, entries, truncated

    async def check_access(self, commit=''):
        digest, _, _ = await asyncio.to_thread(self._snapshot)
        return {'head':digest, 'repo':self.repo, 'branch':'working-tree'}

    async def begin_snapshot(self):
        self.commit, self.entries, truncated = await asyncio.to_thread(self._snapshot)
        self.allowed = {e['path']:e for e in self.entries if not e['skip']}
        return {'commit':self.commit, 'entries':len(self.entries), 'tree_incomplete':truncated}

    async def list_files(self, cursor=0):
        if not self.commit or cursor < 0:
            raise SourceError('scope', 'Start a local snapshot before listing files.')
        end = cursor + 200
        return {'files':self.entries[cursor:end], 'next_cursor':end if end < len(self.entries) else None}

    async def read_file(self, path):
        if path not in self.allowed:
            raise SourceError('scope', 'File is outside the selected snapshot or excluded by policy.')
        result = await asyncio.to_thread(self._read, path)
        if result.get('skip') or result['sha'] != self.allowed[path]['sha']:
            raise SourceError('stale', 'A local file changed during the scan. Refresh the folder to read a consistent snapshot.')
        try:
            text = result.pop('content').decode('utf-8-sig')
        except UnicodeError:
            return {'skip':'non_utf8'}
        if '\x00' in text:
            return {'skip':'binary'}
        if max((len(line) for line in text.splitlines()), default=0) > LIMITS.chunk_chars:
            return {'skip':'overlong_line'}
        return {**result, 'text':text}
