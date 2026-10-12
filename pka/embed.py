"""Optional semantic retrieval through a local embedding model.

Lexical search cannot match "how do I run this" against a line that says uvicorn, because the
two share no words. The project's own vocabulary and the synonym list in index.py close some
of that gap, and for this project they close most of it, but neither can close all of it: a
word has to exist somewhere for either to find it.

So this adds the other half. Chunks are turned into vectors once per scan, a question is
turned into a vector when it is asked, and the nearest chunks join the lexical candidates in
the same reciprocal rank fusion. Lexical retrieval keeps its place rather than being replaced,
because it is exact where this is approximate: asked for SCRUM-17 or for a function by name,
word matching wins and should.

It is off unless PKA_EMBED_MODEL names a model, and it fails quietly. An embedding model that
is not installed, an Ollama that is not running, a request that times out: each one logs and
leaves lexical retrieval doing exactly what it did before. Nothing here is allowed to cost a
scan or an answer.
"""
import array
import os
import time

import httpx

from pka import applog

ENDPOINT = 'http://127.0.0.1:11434/api/embed'
BATCH = 32
TIMEOUT = 120
# A vector per chunk is cheap, but a vector per chunk for a 500 file repository is not free
# either, so the same ceiling the scan uses applies here.
MAX_CHUNKS = 4000


def model() -> str:
    """The embedding model to use, or an empty string when semantic retrieval is off."""
    return os.getenv('PKA_EMBED_MODEL', '').strip()


def enabled() -> bool:
    return bool(model())


def pack(vector) -> bytes:
    return array.array('f', vector).tobytes()


def unpack(blob: bytes):
    out = array.array('f')
    out.frombytes(blob)
    return out


def similarity(left, right) -> float:
    """Cosine similarity, which is the dot product once both sides are unit length.

    Vectors are normalised on the way in, so this is only the dot product and the length
    division does not have to happen on every comparison of every query against every chunk.
    """
    return sum(a * b for a, b in zip(left, right))


def normalise(vector):
    total = sum(x * x for x in vector) ** 0.5
    if not total:
        return vector
    return [x / total for x in vector]


async def vectors(texts: list[str]) -> list | None:
    """Embed these texts, or return None if semantic retrieval is unavailable for any reason.

    None means "carry on lexically", never an error. Every caller treats it that way, which is
    what makes this safe to leave switched on.
    """
    name = model()
    if not name or not texts:
        return None
    started = time.perf_counter()
    out = []
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, trust_env=False) as client:
            for position in range(0, len(texts), BATCH):
                batch = texts[position:position + BATCH]
                response = await client.post(ENDPOINT, json={'model': name, 'input': batch})
                if response.status_code != 200:
                    applog.failure('embed.http', status=response.status_code, model=name,
                                   texts=len(texts))
                    return None
                found = response.json().get('embeddings')
                if not isinstance(found, list) or len(found) != len(batch):
                    applog.failure('embed.bad_shape', model=name, asked=len(batch),
                                   got=0 if not isinstance(found, list) else len(found))
                    return None
                out.extend(normalise(v) for v in found)
    except (httpx.RequestError, ValueError, KeyError, TypeError) as exc:
        applog.failure('embed.unavailable', model=name, type=type(exc).__name__,
                       secs=round(time.perf_counter() - started, 1))
        return None
    applog.event('embed.done', model=name, texts=len(texts),
                 dimensions=len(out[0]) if out else 0,
                 secs=round(time.perf_counter() - started, 1))
    return out
