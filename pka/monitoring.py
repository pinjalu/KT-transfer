"""Content-free operational events, isolated by workspace and bounded on disk.

Only explicitly allowed identifiers, enums and numeric counters are written.
Never pass request bodies, credentials, prompts, sources or exception messages.
"""
import json
import math
import re
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 5
_lock = threading.RLock()
_context = ContextVar('pka_monitoring', default=None)
_strings = {'provider', 'model', 'feature', 'status', 'code', 'reason', 'method',
            'route', 'job', 'job_id', 'attempt_id', 'generation_id', 'mode', 'level'}
_numbers = {'http_status', 'elapsed_seconds', 'input_tokens', 'output_tokens',
            'estimated_tokens', 'retry_after_seconds', 'actor_id', 'source_count',
            'attempt_count', 'files', 'chunks', 'count', 'done', 'total', 'chars',
            'words', 'hits', 'seconds', 'bytes', 'topics', 'failed_topics', 'secs',
            'scan_id', 'answer_id', 'sources', 'found', 'dropped', 'sections',
            'issues', 'channels', 'blocks', 'max_sources'}
_booleans = {'synthetic', 'diagnostic', 'enabled', 'confirmed', 'approved', 'cache_hit'}


def path(index_path=None):
    if index_path is not None:
        return Path(index_path).parent / 'logs' / 'activity.jsonl'
    context = _context.get()
    if context:
        return context[0]
    from pka.config import log_dir
    return log_dir() / 'activity.jsonl'


@contextmanager
def request_scope(index_path):
    token = _context.set((path(index_path), uuid.uuid4().hex))
    try:
        yield
    finally:
        _context.reset(token)


def event(name, *, index_path=None, **fields):
    """Best-effort append. Log failure must never fail an application operation."""
    try:
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', name):
            return False
        record = {'time': datetime.now(timezone.utc).isoformat(timespec='milliseconds'), 'event': name}
        context = _context.get()
        if context:
            record['request_id'] = context[1]
        for key, value in fields.items():
            if key in _strings and isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_.:/-]{1,120}', value):
                record[key] = value
            elif key in _numbers and type(value) in (int, float) and math.isfinite(value):
                record[key] = value
            elif key in _booleans and type(value) is bool:
                record[key] = value
        line = json.dumps(record, ensure_ascii=True, allow_nan=False) + '\n'
        target = path(index_path)
        with _lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.stat().st_size + len(line.encode()) > MAX_BYTES:
                for number in range(BACKUPS, 0, -1):
                    source = target if number == 1 else target.with_name(target.name + f'.{number-1}')
                    destination = target.with_name(target.name + f'.{number}')
                    if source.exists():
                        source.replace(destination)
            with target.open('a', encoding='utf-8') as output:
                output.write(line)
        return True
    except (OSError, ValueError, TypeError, OverflowError):
        return False
