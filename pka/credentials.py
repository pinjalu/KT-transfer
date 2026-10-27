"""Store platform credentials in the authenticated Windows account's local vault.

The rule this follows is that a credential never reaches source code, a model prompt or a log.
Production uses a per-account DPAPI vault selected by request context. The legacy .env path
remains for development/test callers without a vault. The interface is told only whether a
credential is set, never what it is.

Only names a platform actually declares in the registry can be written. Without that allowlist
a form post could set PATH or PYTHONPATH, and the next scan spawns a subprocess, so an
arbitrary environment write would be an arbitrary code execution.
"""
import os
from contextvars import ContextVar
from contextlib import contextmanager

from pka.config import ROOT
from pka.connectors import registry

MAX_VALUE = 500
ENV_PATH = ROOT / '.env'
_file_path = None
_file_values = {}
active_vault = ContextVar('pka_credential_vault', default=None)


@contextmanager
def using(vault):
    token = active_vault.set(vault)
    try:
        yield
    finally:
        active_vault.reset(token)


@contextmanager
def owner_credentials(index_path):
    """Explicit local diagnostic CLI context; never select this from an HTTP parameter."""
    from pathlib import Path
    from pka.vault import Vault
    path = Path(index_path).with_suffix('.credentials.dpapi')
    with using(Vault(path) if path.exists() else None):
        yield


def getenv(name, default=''):
    vault = active_vault.get()
    if vault is not None and name in writable():
        return vault.read().get(name, default)
    return os.getenv(name, default)


def writable() -> set:
    """Every credential name the registry declares. Nothing else may be written."""
    names = {name for p in registry.PLATFORMS for name in p['credentials']}
    # a token obtained by clicking Connect is stored the same way a typed one is
    names |= {p['oauth']['token_name'] for p in registry.PLATFORMS if p.get('oauth')}
    names |= {'GEMINI_API_KEY', 'GROQ_API_KEY'}
    return names


def refresh() -> None:
    """Re-read the credential lines from .env so an edit made by hand takes effect.

    The file is read once at startup, so editing it in an editor used to do nothing until the
    application was restarted, while saving the same value through the interface worked at once.
    Only names the registry declares are refreshed, so this can never reach PATH or any other
    setting that happens to live in the same file.
    """
    global _file_path, _file_values
    if active_vault.get() is not None:
        active_vault.get().read()  # Fail closed if the current user's vault cannot be unlocked.
        return
    if _file_path != ENV_PATH:
        _file_path, _file_values = ENV_PATH, {}
    allowed = writable()
    try:
        lines = ENV_PATH.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        lines = []
    except OSError:
        return
    current = {}
    for line in lines:
        if '=' not in line or line.lstrip().startswith('#'):
            continue
        name, _, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if name in allowed:
            current[name] = value
            if value:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)
    for name, previous in _file_values.items():
        if name not in current and os.getenv(name) == previous:
            os.environ.pop(name, None)
    _file_values = current


def source_fingerprint(name: str) -> str:
    """Local identity marker only; never expose this or credential values in API output."""
    import hashlib
    import json
    names = {'github': ('GITHUB_TOKEN',), 'jira': ('JIRA_SITE', 'JIRA_EMAIL', 'JIRA_API_TOKEN'),
             'slack': ('SLACK_USER_TOKEN',)}[name]
    return hashlib.sha256(json.dumps([getenv(key, '') for key in names]).encode()).hexdigest()


def status() -> dict:
    refresh()
    return {name: bool(getenv(name, '')) for name in sorted(writable())}


def _check(name: str, value: str) -> str:
    if name not in writable():
        raise ValueError('Unknown credential name.')
    value = value.strip()
    if len(value) > MAX_VALUE:
        raise ValueError(name + ' is too long.')
    if '\n' in value or '\r' in value or '\x00' in value:
        # A newline would end the line and let the rest be read as another setting.
        raise ValueError(name + ' may not contain a line break.')
    return value


def _reject_duplicates(checked: dict) -> None:
    """Two credentials of one platform are never the same value.

    Pasting the client id into the secret box as well is an easy mistake, and the platform only
    reports it much later as a refused connection, which reads like the secret is wrong rather
    than like the wrong thing was pasted.
    """
    for platform in registry.PLATFORMS:
        names = platform['credentials']
        # Only judge a platform this save actually touches. A pre-existing problem elsewhere
        # must not block an unrelated credential from being stored.
        if len(names) < 2 or not any(name in checked for name in names):
            continue
        effective = {name: checked.get(name, getenv(name, '')) for name in names}
        seen = {}
        for name, value in effective.items():
            if not value:
                continue
            if value in seen:
                raise ValueError(seen[value] + ' and ' + name + ' cannot be the same value. '
                                 'They are two different things on the platform, so check you copied each one.')
            seen[value] = name


def save(values: dict) -> list:
    """Save in the selected vault (legacy .env outside a vault); return names, never values."""
    checked = {name: _check(name, str(value)) for name, value in values.items()}
    if not checked:
        return []
    if {'GEMINI_API_KEY','GROQ_API_KEY'} & checked.keys() and active_vault.get() is None:
        raise ValueError('AI API keys require the signed-in account\'s secure credential vault.')
    _reject_duplicates(checked)
    if active_vault.get() is not None:
        active_vault.get().save(checked)
        return sorted(checked)
    lines = ENV_PATH.read_text(encoding='utf-8').splitlines() if ENV_PATH.exists() else []
    seen = set()
    out = []
    for line in lines:
        key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else ''
        if key in checked:
            if key not in seen:
                out.append(key + '=' + checked[key])
                seen.add(key)
            continue
        out.append(line)
    for name, value in checked.items():
        if name not in seen:
            out.append(name + '=' + value)
    ENV_PATH.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')
    for name, value in checked.items():
        if value:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)
    return sorted(checked)
