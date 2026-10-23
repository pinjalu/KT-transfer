"""Windows credential encryption and failure-safe migration; disposable secrets only."""
import os

import pytest

from pka import credentials
from pka.vault import Vault

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Deployment uses Windows current-user DPAPI')


def test_encrypted_persistence_and_tamper_detection(tmp_path):
    path = tmp_path/'credentials.dpapi'
    Vault(path).save({'GITHUB_TOKEN':'private-fixture-token'})
    assert b'private-fixture-token' not in path.read_bytes()
    assert Vault(path).read() == {'GITHUB_TOKEN':'private-fixture-token'}
    content = bytearray(path.read_bytes())
    content[-1] ^= 1
    path.write_bytes(content)
    with pytest.raises(RuntimeError, match='could not unlock'):
        Vault(path).read()


def test_migration_removes_complete_multiline_secrets_and_preserves_settings(tmp_path, monkeypatch):
    env = tmp_path/'.env'
    env.write_text('# local configuration\nOLLAMA_MODEL=fixture\nexport GITHUB_TOKEN="private\nfixture"\n', encoding='utf-8')
    monkeypatch.setenv('GITHUB_TOKEN', 'old-process-secret')
    vault = Vault(tmp_path/'credentials.dpapi')
    vault.migrate(env, {'GITHUB_TOKEN'})
    assert vault.read() == {'GITHUB_TOKEN':'private\nfixture'}
    assert env.read_text() == '# local configuration\nOLLAMA_MODEL=fixture\n'
    assert 'GITHUB_TOKEN' not in os.environ
    vault.migrate(env, {'GITHUB_TOKEN'})
    assert vault.read()['GITHUB_TOKEN'] == 'private\nfixture'


def test_failed_encryption_keeps_original_plaintext_configuration(tmp_path, monkeypatch):
    import pka.vault as module
    env = tmp_path/'.env'
    original = b'GITHUB_TOKEN=original-fixture\nOLLAMA_MODEL=fixture\n'
    env.write_bytes(original)
    def failure(*args, **kwargs):
        raise RuntimeError('Encryption unavailable')
    monkeypatch.setattr(module, 'protect', failure)
    with pytest.raises(RuntimeError):
        Vault(tmp_path/'credentials.dpapi').migrate(env, {'GITHUB_TOKEN'})
    assert env.read_bytes() == original


def test_context_save_never_changes_host_or_other_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN', 'host-fixture')
    first, second = Vault(tmp_path/'first.dpapi'), Vault(tmp_path/'second.dpapi')
    first.save({'GITHUB_TOKEN':'first-fixture'})
    with credentials.using(second):
        assert not credentials.status()['GITHUB_TOKEN']
        credentials.save({'GITHUB_TOKEN':'second-fixture'})
        assert credentials.getenv('GITHUB_TOKEN') == 'second-fixture'
        credentials.save({'GITHUB_TOKEN':''})
        assert not credentials.getenv('GITHUB_TOKEN')
    assert first.read()['GITHUB_TOKEN'] == 'first-fixture'
    assert os.environ['GITHUB_TOKEN'] == 'host-fixture'


def test_diagnostic_cli_uses_owner_vault_and_restores_context(tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN', 'host-fixture')
    Vault(tmp_path/'index.credentials.dpapi').save({'GITHUB_TOKEN':'encrypted-owner-fixture'})
    with credentials.owner_credentials(tmp_path/'index.sqlite3'):
        assert credentials.getenv('GITHUB_TOKEN') == 'encrypted-owner-fixture'
    assert credentials.getenv('GITHUB_TOKEN') == 'host-fixture'
