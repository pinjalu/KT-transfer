"""One continuous application log for debugging.

Everything the application does lands in a single file so a problem can be followed from
startup through configuration, scanning, retrieval and the model call without piecing
together separate sources.

What is deliberately never written here: the GitHub token, any source excerpt text, and any
answer text. Question text is withheld by default and included only when PKA_LOG_QUESTIONS=1
is set, because a question can quote private code. Everything else, including file paths,
counts, HTTP status codes, rate allowances and timings, is recorded in full.
"""
from logging.handlers import RotatingFileHandler
import logging
import os

LOGGER = logging.getLogger('pka')
LOGGER.addHandler(logging.NullHandler())
_configured = False


def log_questions() -> bool:
    return os.getenv('PKA_LOG_QUESTIONS', '') == '1'


def setup(path=None, level: str = '') -> str:
    """Attach the rolling file handler. Safe to call more than once."""
    global _configured
    from pka.config import log_dir
    target = str(path or log_dir() / 'pka.log')
    if _configured:
        return target
    handler = RotatingFileHandler(target, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-5s %(message)s'))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(getattr(logging, (level or os.getenv('PKA_LOG_LEVEL', 'INFO')).upper(), logging.INFO))
    LOGGER.propagate = False
    _configured = True
    return target


def _format(name: str, fields: dict) -> str:
    parts = []
    for k, v in fields.items():
        if v is None:
            continue
        text = str(v).replace('\n', ' ').replace('\r', ' ')
        if len(text) > 400:
            text = text[:400] + '...'
        parts.append(f'{k}={text}')
    return f'{name:<18} ' + ' '.join(parts)


def event(name: str, **fields) -> None:
    LOGGER.info(_format(name, fields))


def warn(name: str, **fields) -> None:
    LOGGER.warning(_format(name, fields))


def failure(name: str, **fields) -> None:
    LOGGER.error(_format(name, fields))


def exception(name: str, exc: BaseException, **fields) -> None:
    """Record an unexpected error with its traceback, which is ours and holds no user data."""
    LOGGER.error(_format(name, {**fields, 'type': type(exc).__name__, 'msg': exc}), exc_info=exc)


def question_fields(question: str) -> dict:
    """Describe a question without disclosing it unless logging of questions is enabled."""
    fields = {'chars': len(question), 'words': len(question.split())}
    if log_questions():
        fields['question'] = question
    return fields
