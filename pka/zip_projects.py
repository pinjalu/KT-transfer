"""Validate uploaded ZIPs and retain bounded source snapshots in one workspace."""
from collections import Counter
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import uuid
import zipfile
import zlib

from pka.config import LIMITS
from pka.connectors.github import exclusion
from pka.connectors.local import PRIVATE_DIRS

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024


def storage(index_path):
    return Path(index_path).with_suffix('.uploads').resolve()


def discard(index_path, root):
    """Only remove a generated snapshot directly inside this workspace's upload store."""
    root = Path(root)
    parent = storage(index_path)
    if (root.parent.resolve() != parent or not re.fullmatch(r'[0-9a-f]{32}', root.name)
            or root.is_symlink() or root.resolve().parent != parent):
        raise ValueError('Invalid upload storage path.')
    if root.exists():
        shutil.rmtree(root)


def _path(info):
    raw = info.orig_filename
    parts = raw.rstrip('/').split('/')
    reserved = r'(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?'
    if (not raw or len(raw) > 500 or '\\' in raw or ':' in raw
            or any(ord(c) < 32 for c in raw)
            or any(p in {'', '.', '..'} or p.endswith((' ', '.')) or re.fullmatch(reserved, p) for p in parts)):
        raise ValueError('The ZIP contains an unsafe filename or folder path.')
    mode = info.external_attr >> 16
    if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ValueError('ZIP links and special files are not supported.')
    if info.flag_bits & 1:
        raise ValueError('Password-protected ZIP files are not supported. Upload an unencrypted ZIP.')
    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise ValueError('Use a ZIP with standard Deflate compression.')
    return parts


def prepare(stream, filename, index_path):
    """Extract supported text only; never extractall, execute code or use uploaded paths as roots."""
    if (not filename.lower().endswith('.zip') or not filename[:-4].strip(' .') or len(filename) > 200 or
            any(c in filename for c in '/\\:') or any(ord(c) < 32 for c in filename)):
        raise ValueError('Choose a project file ending in .zip.')
    parent = storage(index_path)
    parent.mkdir(parents=True, exist_ok=True)
    root = parent / uuid.uuid4().hex
    root.mkdir()
    content = root / 'source'
    content.mkdir()
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) > LIMITS.max_entries:
                raise ValueError(f'The ZIP has too many entries. Limit: {LIMITS.max_entries:,}.')
            if sum(i.file_size for i in entries) > MAX_EXPANDED_BYTES:
                raise ValueError('The ZIP expands beyond the 100 MB limit.')
            paths, seen = [], {}
            for info in entries:
                parts = _path(info)
                key = '/'.join(parts).casefold()
                if key in seen:
                    raise ValueError('The ZIP contains duplicate filenames (including case differences).')
                seen[key] = info.is_dir()
                paths.append((info, parts))
            for key in seen:
                parts = key.split('/')
                if any(seen.get('/'.join(parts[:n])) is False for n in range(1, len(parts))):
                    raise ValueError('The ZIP contains conflicting file and folder paths.')
            files = [(info, parts) for info, parts in paths if not info.is_dir()]
            # GitHub downloads wrap everything in repo-branch/; remove that one wrapper.
            wrapped = bool(files) and all(len(p) > 1 and p[0] == files[0][1][0] for _, p in files)
            skipped, used, accepted = Counter(), 0, 0
            files.sort(key=lambda item: (not PurePosixPath(item[0].filename).name.lower().startswith('readme'), item[0].filename))
            for info, parts in files:
                relative = '/'.join(parts[1:] if wrapped else parts)
                reason = exclusion(info.filename, info.file_size) or exclusion(relative, info.file_size)
                if any(p.lower() in PRIVATE_DIRS | {'__macosx'} for p in parts[:-1]):
                    reason = 'private_or_metadata_directory'
                if relative.startswith(('jira/', 'slack/')):
                    reason = 'reserved_source_path'
                if not reason and (accepted >= LIMITS.max_files or used + info.file_size > LIMITS.max_total_bytes):
                    reason = 'scan_size_limit'
                if reason:
                    skipped[reason] += 1
                    continue
                with archive.open(info) as source:
                    data = source.read(LIMITS.max_file_bytes + 1)
                if len(data) != info.file_size or len(data) > LIMITS.max_file_bytes:
                    raise ValueError('The ZIP contains inconsistent file sizes.')
                try:
                    text = data.decode('utf-8-sig')
                except UnicodeError:
                    skipped['non_utf8'] += 1
                    continue
                if '\x00' in text:
                    skipped['binary'] += 1
                    continue
                if not text.strip():
                    skipped['empty_file'] += 1
                    continue
                if max((len(line) for line in text.splitlines()), default=0) > LIMITS.chunk_chars:
                    skipped['overlong_line'] += 1
                    continue
                target = content.joinpath(*relative.split('/'))
                if not target.resolve().is_relative_to(content.resolve()):
                    raise ValueError('The ZIP contains an unsafe path.')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                used += len(data)
                accepted += 1
            if not accepted:
                raise ValueError('The ZIP contains no supported source code or text documentation to read.')
        return {'repo':'zip:' + content.as_posix(), 'root':str(root), 'filename':filename,
                'files':accepted, 'skipped':dict(skipped), 'bytes':used}
    except (zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, OSError, EOFError) as exc:
        discard(index_path, root)
        raise ValueError('The ZIP could not be read. Upload a valid, unencrypted project ZIP.') from exc
    except BaseException:
        discard(index_path, root)
        raise
