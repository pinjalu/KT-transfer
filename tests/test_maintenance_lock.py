import pytest

from pka.__main__ import main
from pka.runtime_lock import data_lock


def test_password_reset_cannot_mutate_data_during_backup_or_server_use(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    def unexpected(*args): pytest.fail('Must refuse the active data directory before asking for a password.')
    monkeypatch.setattr('getpass.getpass', unexpected)
    with data_lock(tmp_path), pytest.raises(SystemExit) as exc:
        main(['--reset-password'])
    assert exc.value.code == 2
    assert not (tmp_path / 'index.auth.sqlite3').exists()
