"""Backup and recovery checks use disposable databases and credentials only."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import zipfile

import pytest

from pka import backup
from pka.runtime_lock import data_lock


def database(path, auth=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE evidence(id INTEGER PRIMARY KEY, value TEXT)')
        db.execute("INSERT INTO evidence VALUES(1,'fixture project knowledge')")
        if auth:
            db.execute('CREATE TABLE sessions(token_hash TEXT)')
            db.execute("INSERT INTO sessions VALUES('old-fixture-session')")
            db.execute('CREATE TABLE bootstrap(token_hash TEXT)')
            db.execute("INSERT INTO bootstrap VALUES('old-fixture-setup')")
        db.commit()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'live-data'
    database(root / 'index.sqlite3')
    database(root / 'index.auth.sqlite3', auth=True)
    database(root / 'index.users' / '10' / 'index.sqlite3')
    (root / 'logs').mkdir()
    (root / 'logs' / 'pka.log').write_text('private log fixture')
    (root / '.env').write_text('unrelated-secret-fixture')
    (root / 'index.auth.setup-code').write_text('old-setup-code-fixture')
    return root


def rewrite(archive, output, transform):
    with zipfile.ZipFile(archive) as incoming:
        entries = {name: incoming.read(name) for name in incoming.namelist()}
    transform(entries)
    with zipfile.ZipFile(output, 'w') as bundle:
        for name, value in entries.items():
            bundle.writestr(name, value)


def test_backup_and_restore_preserve_knowledge_and_never_revive_sessions(source, tmp_path):
    archive = tmp_path / 'backup.zip'
    original = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob('*.sqlite3')}
    manifest = backup.create_backup(source, archive)
    assert len(manifest['files']) == 3
    assert backup.verify_archive(archive) == manifest
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {'manifest.json', 'index.sqlite3', 'index.auth.sqlite3', 'index.users/10/index.sqlite3'}
    destination = tmp_path / 'restored'
    result = backup.restore_backup(archive, destination)
    assert result['sessions_revoked']
    for name, previous in original.items():
        assert (source / name).read_bytes() == previous
        with closing(sqlite3.connect(destination / name)) as db:
            assert db.execute('SELECT value FROM evidence').fetchone() == ('fixture project knowledge',)
    with closing(sqlite3.connect(destination / 'index.auth.sqlite3')) as db:
        assert not db.execute('SELECT * FROM sessions').fetchall()
        assert not db.execute('SELECT * FROM bootstrap').fetchall()


def test_existing_backup_and_restore_destination_are_untouched(source, tmp_path):
    archive = tmp_path / 'backup.zip'
    backup.create_backup(source, archive)
    original = archive.read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        backup.create_backup(source, archive)
    assert archive.read_bytes() == original
    with pytest.raises(ValueError, match='new directory'):
        backup.restore_backup(archive, source)
    with pytest.raises(ValueError, match='outside'):
        backup.create_backup(source, source / 'backup.zip')


@pytest.mark.parametrize('kind', ['changed_bytes', 'traversal', 'missing_file', 'unknown_format', 'duplicate'])
def test_invalid_archives_cannot_create_a_restored_directory(source, tmp_path, kind):
    archive, damaged = tmp_path / 'good.zip', tmp_path / 'bad.zip'
    backup.create_backup(source, archive)
    def transform(entries):
        if kind == 'changed_bytes': entries['index.sqlite3'] += b'changed'
        elif kind == 'traversal': entries['../escape'] = b'outside'
        elif kind == 'missing_file': del entries['index.auth.sqlite3']
        elif kind == 'unknown_format': entries['manifest.json'] = b'{"format":"other"}'
    rewrite(archive, damaged, transform)
    if kind == 'duplicate':
        with zipfile.ZipFile(damaged, 'a') as bundle, pytest.warns(UserWarning):
            bundle.writestr('index.sqlite3', b'duplicate')
    with pytest.raises(ValueError):
        backup.restore_backup(damaged, tmp_path / 'restored')
    assert not (tmp_path / 'restored').exists()
    assert not (tmp_path / 'escape').exists()


def test_valid_checksum_does_not_make_an_invalid_database_restorable(source, tmp_path):
    archive, damaged = tmp_path / 'good.zip', tmp_path / 'bad.zip'
    backup.create_backup(source, archive)
    def transform(entries):
        entries['index.sqlite3'] = b'not a database'
        manifest = json.loads(entries['manifest.json'])
        item = next(item for item in manifest['files'] if item['path'] == 'index.sqlite3')
        item.update(size=len(entries['index.sqlite3']), sha256=hashlib.sha256(entries['index.sqlite3']).hexdigest())
        entries['manifest.json'] = json.dumps(manifest).encode()
    rewrite(archive, damaged, transform)
    with pytest.raises(sqlite3.DatabaseError):
        backup.restore_backup(damaged, tmp_path / 'restored')
    assert not (tmp_path / 'restored').exists()


def test_backup_refuses_a_running_server_data_directory(source, tmp_path):
    with data_lock(source):
        with pytest.raises(RuntimeError, match='in use'):
            backup.create_backup(source, tmp_path / 'backup.zip')
    assert not (tmp_path / 'backup.zip').exists()
    backup.create_backup(source, tmp_path / 'backup.zip')


def test_snapshot_includes_committed_wal_data(source, tmp_path):
    with closing(sqlite3.connect(source / 'index.sqlite3')) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute("INSERT INTO evidence VALUES(2,'committed WAL fixture')")
        db.commit()
        backup.create_backup(source, tmp_path / 'backup.zip')
    backup.restore_backup(tmp_path / 'backup.zip', tmp_path / 'restored')
    with closing(sqlite3.connect(tmp_path / 'restored' / 'index.sqlite3')) as db:
        assert db.execute('SELECT count(*) FROM evidence').fetchone()[0] == 2


@pytest.mark.skipif(os.name != 'nt', reason='Private deployment uses Windows DPAPI')
def test_credentials_remain_encrypted_and_restore_requires_working_keys(source, tmp_path, monkeypatch):
    from pka.vault import Vault
    Vault(source / 'index.credentials.dpapi').save({'GITHUB_TOKEN': 'private-backup-fixture'})
    archive = tmp_path / 'backup.zip'
    backup.create_backup(source, archive)
    with zipfile.ZipFile(archive) as bundle:
        assert b'private-backup-fixture' not in bundle.read('index.credentials.dpapi')
    backup.restore_backup(archive, tmp_path / 'restored')
    assert Vault(tmp_path / 'restored' / 'index.credentials.dpapi').read()['GITHUB_TOKEN'] == 'private-backup-fixture'
    def locked(*args, **kwargs): raise RuntimeError('Windows account keys unavailable')
    monkeypatch.setattr(Vault, 'read', locked)
    with pytest.raises(RuntimeError, match='keys unavailable'):
        backup.restore_backup(archive, tmp_path / 'unusable')
    assert not (tmp_path / 'unusable').exists()


def test_cli_reports_verified_output_without_printing_contents(source, tmp_path, capsys):
    archive = tmp_path / 'backup.zip'
    assert backup.main(['create', '--data-dir', str(source), '--output', str(archive)]) == 0
    assert backup.main(['verify', str(archive)]) == 0
    assert backup.main(['restore', str(archive), '--destination', str(tmp_path / 'restored')]) == 0
    output = capsys.readouterr().out
    assert 'verified' in output and 'fixture project knowledge' not in output
