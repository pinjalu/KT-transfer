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


# Questions used to find out where irrelevance tops out in a particular snapshot, so the
# cut-off below which a semantic match is discarded can be derived for whatever was scanned
# rather than hardcoded from one project.
#
# They are everyday subjects on purpose. None of them names a programming idea, a file type or
# a tool, so none of them can accidentally be about the repository being measured, whatever
# that repository is. The highest score any of them reaches is this snapshot's definition of
# "no connection at all", and the real cut-off is set above it with a margin.
PROBES = (
    'recipe for banana bread with walnuts',
    'what is the capital city of France',
    'purple elephant tractor symphony',
    'the rules of cricket explained for beginners',
    'how to repot a houseplant that has outgrown its pot',
    'weather forecast for the weekend by the coast',
    'quasar nebula zebras',
    'a short history of the bicycle',
)
# How far above the observed ceiling of irrelevance the cut-off sits.
#
# The first value tried here was 1.2, which was wrong and was caught by measuring rather than
# by reasoning. On the measured snapshot the probes top out at 0.524 and the weakest genuine
# question reaches 0.579, so anything above about 1.105 starts refusing questions the project
# can actually answer. A fifth above the ceiling landed at 0.629 and threw away real work.
#
# 1.05 keeps the cut-off clear of irrelevance while leaving room for a repository whose gap is
# narrower than this one's. The two ways of being wrong are not equally bad: a margin that is
# too small lets a weak match through, where the lexical half of the search and the visible
# excerpt still give the reader a chance to judge it, while a margin that is too large refuses
# a question the project could have answered and the reader never learns it was there.
CALIBRATION_MARGIN = 1.05


def model() -> str:
    """The embedding model to use, or an empty string when semantic retrieval is off."""
    return os.getenv('PKA_EMBED_MODEL', '').strip()


def enabled() -> bool:
    return bool(model())


def signature() -> str:
    """Include preprocessing so old, unprefixed vectors cannot be mixed in."""
    return model() + ('|search-prefix-v1' if model().split(':')[0] == 'nomic-embed-text' else '|v1')


def query_texts(texts):
    return ['search_query: ' + text for text in texts] if model().split(':')[0] == 'nomic-embed-text' else texts


def document_texts(texts):
    return ['search_document: ' + text for text in texts] if model().split(':')[0] == 'nomic-embed-text' else texts


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
    return sum(a * b for a, b in zip(left, right)) if len(left) == len(right) else 0.0


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
