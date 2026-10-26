"""Compare bounded pipelines with disposable fixtures; optionally measure local embeddings."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pka import embed
from pka.connectors.fixture import FixtureSource, FILES, COMMIT
from pka.index import Index
from pka.parallel import process_parallel
from pka.service import Service


class DelayedFiles(FixtureSource):
    async def begin_snapshot(self):
        return {'commit':COMMIT, 'entries':24, 'tree_incomplete':False}

    async def list_files(self, cursor=0):
        return {'files':[{'path':f'file{n}.md','size':len(FILES['README.md'].encode()),'skip':''}
                         for n in range(24)], 'next_cursor':None}

    async def read_file(self, path):
        await asyncio.sleep(.04)
        text = FILES['README.md']
        return {'text':text,'bytes':len(text.encode()),'sha':'b'*40}


@asynccontextmanager
async def source(settings, demo=False):
    yield DelayedFiles()


async def scan_trial(folder, limit):
    os.environ['PKA_READ_CONCURRENCY'] = str(limit)
    os.environ['PKA_EMBED_MODEL'] = ''
    index = Index(folder / f'scan-{limit}.sqlite3')
    index.configure({'repo':'fixture/benchmark','branch':'main'})
    svc = Service(index, demo=True, connector_factory=source)
    started = time.perf_counter()
    await svc.scan()
    elapsed = time.perf_counter() - started
    assert index.latest()['status'] == 'complete'
    return {'concurrency':limit,'seconds':round(elapsed,3),'files':index.latest()['read']}


async def embedding_trial(limit):
    # Same bounded input in each run; only timing/counts are printed.
    batches = [[(f'File {batch}-{n}: def authenticate(user): verify_password(user); create_session(user).\n' * 12)
                for n in range(8)] for batch in range(4)]
    count = 0

    async def save(batch, vectors):
        nonlocal count
        if not vectors or len(vectors) != len(batch):
            raise RuntimeError('Local embedding model did not return every vector.')
        count += len(vectors)

    started = time.perf_counter()
    await process_parallel(batches, embed.vectors, save, limit)
    return {'concurrency':limit,'seconds':round(time.perf_counter()-started,3),'vectors':count}


async def main(with_ollama):
    configured_model = embed.model()
    with tempfile.TemporaryDirectory(prefix='pka-parallel-') as directory:
        folder = Path(directory)
        os.environ['PKA_DATA_DIR'] = str(folder)
        os.environ['PKA_LOG_DIR'] = str(folder / 'logs')
        trials = [await scan_trial(folder, limit) for limit in (1,4)]
        print(json.dumps({'file_reads':'SIMULATED 40ms I/O per file; real scan/index pipeline',
                          'trials':trials,'speedup':round(trials[0]['seconds']/trials[1]['seconds'],2)}), flush=True)
        if with_ollama:
            if not configured_model:
                raise RuntimeError('Configure PKA_EMBED_MODEL before benchmarking Ollama.')
            os.environ['PKA_EMBED_MODEL'] = configured_model
            if not await embed.vectors(['Warm up the local embedding model.']):
                raise RuntimeError('The configured embedding model is unavailable.')
            # Counterbalance run order to expose warm-up/cache effects.
            trials = [await embedding_trial(limit) for limit in (1,2,2,1)]
            sequential = sum(t['seconds'] for t in trials if t['concurrency'] == 1)
            parallel = sum(t['seconds'] for t in trials if t['concurrency'] == 2)
            print(json.dumps({'embeddings':'real Ollama, synthetic text','model':configured_model,
                              'trials':trials,'speedup':round(sequential/parallel,2)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ollama', action='store_true', help='Also benchmark the idle local embedding model.')
    asyncio.run(main(parser.parse_args().ollama))
