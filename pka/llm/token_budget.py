"""Local token estimates; never upload prompts or fetch data during generation.

GPT-OSS ordinary text uses the o200k vocabulary and pattern from OpenAI's
tiktoken 0.12.0 (MIT; see LICENSE.tokenizer). The bundled public vocabulary is
checked against the upstream SHA-256 before use. Hosted chat/schema overhead
is not exposed, so reservations include a margin and remain labelled estimates.
"""
import base64
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path

VOCABULARY = Path(__file__).with_name('o200k_base.tiktoken.gz')
VOCABULARY_SHA256 = '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'
# Identical to tiktoken's o200k_base / o200k_harmony ordinary-text pattern.
PATTERN = '|'.join([
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r'\p{N}{1,3}', r' ?[^\s\p{L}\p{N}]+[\r\n/]*',
    r'\s*[\r\n]+', r'\s+(?!\S)', r'\s+',
])


@lru_cache(maxsize=1)
def encoding():
    import tiktoken
    raw = gzip.decompress(VOCABULARY.read_bytes())
    if hashlib.sha256(raw).hexdigest() != VOCABULARY_SHA256:
        raise ValueError('Tokenizer vocabulary checksum mismatch')
    ranks = {base64.b64decode(token):int(rank) for token,rank in
             (line.split() for line in raw.splitlines() if line)}
    return tiktoken.Encoding(name='pka_o200k_ordinary',pat_str=PATTERN,
                            mergeable_ranks=ranks,special_tokens={})


def estimate(request, target):
    """Include schema, framing margin and the entire requested output allowance."""
    if target.provider == 'groq' and target.model in {'openai/gpt-oss-120b','openai/gpt-oss-20b'}:
        try:
            from pka.llm.groq import prepare
            tokenizer = encoding()
            messages, schema, _ = prepare(request)
            # Count the content the model sees, not HTTP's extra JSON escaping.
            count = sum(len(tokenizer.encode_ordinary(message['content'])) + 32
                        for message in messages)
            count += len(tokenizer.encode_ordinary(json.dumps(schema,ensure_ascii=False)))
            reserved = math.ceil(count * 1.1) + 128 + request.max_output_tokens
            return reserved, 'o200k_with_margin'
        except (ImportError, OSError, ValueError, KeyError, TypeError):
            # Offline and older installations stay operational using the old
            # conservative estimate; missing/corrupt assets never trigger downloads.
            pass
    reserved = math.ceil(len(json.dumps([request.messages,request.schema],ensure_ascii=False).encode()) / 3)
    return reserved + request.max_output_tokens, 'byte_estimate'
