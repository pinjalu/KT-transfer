"""Verified offline backups; restore to a new directory without replacing live data."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tempfile
import zipfile

from pka.config import data_dir, now
from pka.runtime_lock import data_lock

MAX_FILES = 128
MAX_BYTES = 2 * 1024 ** 3
MANIFEST = 'manifest.json'


def permitted(name):
    return bool(re.fullmatch(
        r'index\.(?:sqlite3|auth\.sqlite3|credentials\.dpapi)|'
        r'index\.users/[2-9][0-9]*/(?:index\.sqlite3|credentials\.dpapi)|'
        r'index\.users/1[0-9]+/(?:index\.sqlite3|credentials\.dpapi)', name))


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(root):
    files = []
    for folder, directories, names in os.walk(root, followlinks=False):
        base = Path(folder)
        for name in list(directories):
            path = base / name
            relative = path.relative_to(root).as_posix()
            expected = relative == 'index.users' or bool(re.fullmatch(r'index\.users/[0-9]+', relative))
            if not expected:
                directories.remove(name)
            elif path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ValueError('Backup refuses linked workspace directories.')
        for name in names:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if not permitted(relative):
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('Backup refuses linked data files.')
            files.append((relative, path))
    if not {'index.sqlite3', 'index.auth.sqlite3'} <= {name for name, _ in files}:
        raise ValueError('The data directory must contain the live project and account databases.')
    if len(files) > MAX_FILES or sum(p.stat().st_size for _, p in files) > MAX_BYTES:
        raise ValueError('The backup exceeds this release\'s file or size limit.')
    return sorted(files)


def snapshot_database(source, target):
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as incoming:
        with closing(sqlite3.connect(target)) as outgoing:
            incoming.backup(outgoing)
            if outgoing.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise ValueError('A database failed its integrity check. Backup was not published.')


def verify_archive(archive):
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)) or not 3 <= len(names) <= MAX_FILES + 1:
            raise ValueError('Backup contains duplicate entries or an invalid file count.')
        if MANIFEST not in names or bundle.getinfo(MANIFEST).file_size > 65536:
            raise ValueError('Backup manifest is missing or too large.')
        if sum(item.file_size for item in infos) > MAX_BYTES:
            raise ValueError('Backup exceeds the supported uncompressed size.')
        for item in infos:
            if item.is_dir() or item.filename != MANIFEST and not permitted(item.filename):
                raise ValueError('Backup contains an unexpected path.')
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Backup contains a symbolic link.')
        manifest = json.loads(bundle.read(MANIFEST))
        if not isinstance(manifest, dict) or manifest.get('format') != 'pka-backup-v1':
            raise ValueError('Unsupported backup format.')
        entries = manifest.get('files')
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise ValueError('Invalid backup file manifest.')
        expected = {item.get('path') for item in entries if isinstance(item.get('path'), str)}
        if (len(expected) != len(entries) or expected != set(names) - {MANIFEST}
                or not {'index.sqlite3', 'index.auth.sqlite3'} <= expected):
            raise ValueError('Backup file list does not match its manifest.')
        for item in entries:
            if type(item.get('size')) is not int or item['size'] != bundle.getinfo(item['path']).file_size:
                raise ValueError('Backup file size does not match its manifest.')
            digest = hashlib.sha256()
            with bundle.open(item['path']) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != item.get('sha256'):
                raise ValueError('Backup checksum mismatch. Do not restore this archive.')
        return manifest


def create_backup(directory, output):
    root, output = Path(directory).resolve(), Path(output).resolve()
    if output.is_relative_to(root):
        raise ValueError('Choose a backup destination outside the live data directory.')
    if output.exists():
        raise ValueError('Backup destination already exists. Choose a new filename.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with data_lock(root), tempfile.TemporaryDirectory(prefix='.pka-backup-', dir=output.parent) as temporary:
        stage = Path(temporary).resolve()
        entries = []
        for name, source in source_files(root):
            target = stage.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith('.sqlite3'):
                snapshot_database(source, target)
            else:
                shutil.copyfile(source, target)
            entries.append({'path': name, 'size': target.stat().st_size, 'sha256': checksum(target)})
        manifest = {'format': 'pka-backup-v1', 'created_at': now(), 'files': entries,
                    'credential_scope': 'Original Windows account and DPAPI keys required for saved credentials.'}
        candidate = stage / 'backup.zip'
        with zipfile.ZipFile(candidate, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            for item in entries:
                bundle.write(stage / item['path'], item['path'])
            bundle.writestr(MANIFEST, json.dumps(manifest, sort_keys=True))
        verify_archive(candidate)
        # An exclusive destination preserves any existing backup, including a
        # filename another process creates after the initial existence check.
        with output.open('xb') as destination, candidate.open('rb') as incoming:
            shutil.copyfileobj(incoming, destination)
            destination.flush()
            os.fsync(destination.fileno())
        verify_archive(output)
        return manifest


def restore_backup(archive, destination):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Restore requires a new directory. Existing data is never overwritten.')
    destination = destination.resolve()
    manifest = verify_archive(archive)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pka-restore-', dir=destination.parent) as temporary:
        stage = Path(temporary).resolve() / 'data'
        stage.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            for item in manifest['files']:
                target = stage.joinpath(*PurePosixPath(item['path']).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(item['path']) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                # Recheck extracted bytes to reject a file changed between verification and extraction.
                if checksum(target) != item['sha256']:
                    raise ValueError('Backup changed during restore.')
                if item['path'].endswith('.sqlite3'):
                    with closing(sqlite3.connect(target)) as db:
                        if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                            raise ValueError('Restored database failed its integrity check.')
                else:
                    from pka.vault import Vault
                    Vault(target).read()  # Refuse unusable encrypted credentials before publication.
        with closing(sqlite3.connect(stage / 'index.auth.sqlite3')) as db:
            # Restoring a backup must not revive old login sessions or bootstrap codes.
            db.execute('DELETE FROM sessions')
            db.execute('DELETE FROM bootstrap')
            db.commit()
        if destination.exists():
            raise ValueError('Restore destination was created by another process.')
        stage.rename(destination)
    return {'restored_files': len(manifest['files']), 'sessions_revoked': True, 'destination': str(destination)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create', help='Stop the app, then create a verified live-data backup.')
    create.add_argument('--data-dir', type=Path)
    create.add_argument('--output', type=Path, required=True)
    verify = commands.add_parser('verify', help='Check manifest, paths, lengths and all file checksums.')
    verify.add_argument('archive', type=Path)
    restore = commands.add_parser('restore', help='Restore into a new directory; never overwrite live data.')
    restore.add_argument('archive', type=Path)
    restore.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'create':
            result = create_backup(args.data_dir or data_dir(), args.output)
            print(f'Backup verified: {len(result["files"])} files. Saved to {args.output}')
        elif args.command == 'verify':
            result = verify_archive(args.archive)
            print(f'Backup verified: {len(result["files"])} files; created {result.get("created_at", "unknown")}.')
        else:
            result = restore_backup(args.archive, args.destination)
            print(f'Restored {result["restored_files"]} files into {result["destination"]}. All saved sessions revoked.')
        return 0
    except (OSError, RuntimeError, ValueError, sqlite3.Error, zipfile.BadZipFile, KeyError) as exc:
        print(f'Backup operation failed: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
