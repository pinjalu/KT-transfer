from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import re
from urllib.parse import urlsplit
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env', override=False)
IST = timezone(timedelta(hours=5, minutes=30))


def now() -> str:
    return datetime.now(IST).isoformat(timespec='seconds')


GITHUB_HOSTS = {'github.com', 'www.github.com', 'api.github.com'}
URL_SCHEMES = {'http', 'https', 'git', 'ssh'}


def normalise_repo(raw: str) -> str:
    """Reduce a pasted github.com address to owner/repository.

    A github.com host may be followed by anything the website puts after the repository name,
    such as /tree/main or /blob/main/app.py; only the first two path segments are kept.
    Input without a host must already be exactly owner/repository, so a stray path such as
    a/b/c is still refused rather than silently truncated.
    """
    text = raw.strip().strip("<>\"'").strip()
    host = ''
    if text.startswith('git@'):
        host, _, text = text[4:].partition(':')
        host = host.lower()
    elif '://' in text:
        parts = urlsplit(text)
        if parts.scheme.lower() not in URL_SCHEMES:
            raise ValueError('Enter a github.com address or OWNER/REPOSITORY.')
        host, text = (parts.hostname or '').lower(), parts.path
    else:
        head, _, rest = text.partition('/')
        if head.lower() in GITHUB_HOSTS:
            host, text = head.lower(), rest
    if host and host not in GITHUB_HOSTS:
        raise ValueError('Only github.com repositories can be read. Enter OWNER/REPOSITORY.')
    text = text.split('?')[0].split('#')[0]
    segments = [x for x in text.split('/') if x]
    if host == 'api.github.com' and segments[:1] == ['repos']:
        segments = segments[1:]
    if host and len(segments) > 2:
        segments = segments[:2]
    if len(segments) != 2:
        raise ValueError('Enter OWNER/REPOSITORY, such as acme/shop, or paste the repository address.')
    owner, name = segments
    if name.lower().endswith('.git'):
        name = name[:-4]
    return owner + '/' + name


def validate_selection(repo: str, branch: str) -> tuple[str, str]:
    repo, branch = normalise_repo(repo), branch.strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Enter OWNER/REPOSITORY, such as acme/shop, or paste the repository address.')
    if any(x in {'.', '..'} for x in repo.split('/')):
        raise ValueError('Invalid repository.')
    if not branch or len(branch) > 200 or re.search(r'[\x00-\x20~^:?*\[\\]', branch) or '..' in branch or '@{' in branch or branch.startswith('/') or branch.endswith('/'):
        raise ValueError('Enter a valid branch name, such as main or feature/login.')
    return repo, branch


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 256 * 1024
    max_total_bytes: int = 5 * 1024 * 1024
    max_files: int = 500
    max_entries: int = 20000
    max_tree_requests: int = 200
    chunk_chars: int = 1800
    context_chars: int = 7200
    max_sources: int = 5
    slack_max_channels: int = 20
    slack_max_messages: int = 600
    slack_max_pages: int = 10
    slack_max_threads: int = 40
    jira_max_issues: int = 300
    jira_max_pages: int = 10
    jira_max_comments: int = 20

LIMITS = Limits()


def data_dir() -> Path:
    p = Path(os.getenv('PKA_DATA_DIR', str(ROOT / 'data')))
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_dir() -> Path:
    p = Path(os.getenv('PKA_LOG_DIR', str(data_dir() / 'logs')))
    p.mkdir(parents=True, exist_ok=True)
    return p


KEEP_LOGS = 20
