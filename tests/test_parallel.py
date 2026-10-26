"""Concurrency, bounded reads, publication order and cancellation without live services."""
import asyncio
import threading
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest

from pka import embed, service as module
from pka.config import LIMITS, now
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource, FILES, COMMIT
from pka.index import Index, chunk_file
from pka.parallel import concurrency, process_parallel
from pka.service import Service


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_EMBED_MODEL', '')
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('PKA_LOG_DIR', str(tmp_path / 'logs'))
    monkeypatch.setenv('PKA_READ_CONCURRENCY', '3')
    monkeypatch.setenv('PKA_EMBED_CONCURRENCY', '2')
    monkeypatch.setenv('PKA_OVERVIEW_CONCURRENCY', '2')
    index = Index(tmp_path / 'index.sqlite3')
    index.configure({'repo':'acme/shop', 'branch':'main'})
    source = FixtureSource()

    @asynccontextmanager
    async def factory(settings, demo=False):
        yield source

    return Service(index, connector_factory=factory), source


@pytest.mark.parametrize('value,expected', [('bad',2), ('0',1), ('-1',1), ('99',4), ('3',3)])
def test_concurrency_settings_are_bounded(monkeypatch, value, expected):
    monkeypatch.setenv('TEST_PARALLEL', value)
    assert concurrency('TEST_PARALLEL', 2, 4) == expected


def test_scan_overlaps_reads_and_keeps_manifest_order(setup):
    svc, source = setup
    original = source.read_file
    active = peak = 0

    async def read(path):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(.03 if path == 'README.md' else .001)
            return await original(path)
        finally:
            active -= 1

    source.read_file = read
    asyncio.run(svc.scan())
    scan = svc.index.latest()
    assert scan['status'] == 'complete'
    assert peak == 3 and active == 0
    assert [f['path'] for f in scan['files']] == list(FILES) + ['.env']
    assert scan['read'] == 3 and scan['bytes'] == sum(len(t.encode()) for t in FILES.values())


@pytest.mark.parametrize('limit_kind', ['files', 'bytes'])
def test_scan_reserves_allowance_before_parallel_calls(setup, monkeypatch, limit_kind):
    svc, source = setup
    first_bytes = len(FILES['README.md'].encode())
    limits = replace(LIMITS, max_files=1) if limit_kind == 'files' else replace(LIMITS, max_total_bytes=first_bytes)
    monkeypatch.setattr(module, 'LIMITS', limits)
    original, calls = source.read_file, []

    async def read(path):
        calls.append(path)
        return await original(path)

    source.read_file = read
    asyncio.run(svc.scan())
    assert calls == ['README.md']
    assert svc.index.latest()['read'] == 1
    assert svc.index.latest()['status'] == 'partial'


def test_skipped_parallel_read_releases_reserved_allowance(setup, monkeypatch):
    svc, source = setup
    monkeypatch.setattr(module, 'LIMITS', replace(LIMITS, max_files=2))
    original = source.read_file

    async def read(path):
        return {'skip':'non_utf8'} if path == 'README.md' else await original(path)

    source.read_file = read
    asyncio.run(svc.scan())
    assert svc.index.latest()['read'] == 2


@pytest.mark.parametrize('failure', ['cancelled', 'access_denied'])
def test_scan_drains_inflight_reads_without_publishing_failed_snapshot(setup, failure):
    svc, source = setup
    original, finished = source.read_file, []

    async def read(path):
        try:
            if path == 'README.md':
                if failure == 'cancelled':
                    svc.cancel.set()
                else:
                    raise SourceError(failure, 'Read access revoked')
            await asyncio.sleep(.01)
            return await original(path)
        finally:
            finished.append(path)

    source.read_file = read
    asyncio.run(svc.scan())
    assert not svc.index.active_scan()
    assert svc.index.latest()['status'] == ('cancelled' if failure == 'cancelled' else 'failed')
    assert finished


def prepare_embeddings(svc, monkeypatch):
    monkeypatch.setenv('PKA_EMBED_MODEL', 'fixture')
    monkeypatch.setattr(embed, 'BATCH', 1)
    scan = {'id':1, 'repo':'acme/shop', 'commit':COMMIT, 'status':'complete', 'finished':now()}
    chunks = [chunk_file(f'file{n}.py', f'def function{n}():\n    return {n}')[0] for n in range(6)]
    svc.index.activate(1, chunks, scan)

    async def calibrate(scan_id):
        return 0

    svc.calibrate = calibrate
    return svc.index.unembedded(1)


def test_embedding_overlap_preserves_chunk_vector_pairs(setup, monkeypatch):
    svc, _ = setup
    rows = prepare_embeddings(svc, monkeypatch)
    active = peak = 0

    async def vectors(texts):
        nonlocal active, peak
        active += 1
        peak = max(active, peak)
        number = int(texts[0][4])
        try:
            await asyncio.sleep(.02 if number % 2 == 0 else .001)
            return [[float(number), 1.0]]
        finally:
            active -= 1

    monkeypatch.setattr(embed, 'vectors', vectors)
    assert asyncio.run(svc.embed_snapshot(1)) == 6
    assert peak == 2 and active == 0
    with svc.index.db() as db:
        saved = {row['chunk_id']:list(embed.unpack(row['vector'])) for row in db.execute('SELECT * FROM vectors')}
    assert saved == {row['id']:[float(n),1.0] for n,row in enumerate(rows)}


@pytest.mark.parametrize('mode', ['unavailable', 'cancel', 'revoked'])
def test_embedding_stops_scheduling_and_rejects_late_writes(setup, monkeypatch, mode):
    svc, _ = setup
    prepare_embeddings(svc, monkeypatch)
    calls, finished = [], []

    async def vectors(texts):
        calls.append(texts[0])
        try:
            if len(calls) == 1:
                await asyncio.sleep(0)
                if mode == 'unavailable':
                    return None
                if mode == 'cancel':
                    svc.cancel.set()
                else:
                    svc.index.invalidate()
            await asyncio.sleep(.01)
            return [[1.0,0.0]]
        finally:
            finished.append(texts[0])

    monkeypatch.setattr(embed, 'vectors', vectors)
    if mode == 'revoked':
        with pytest.raises(SourceError, match='changed'):
            asyncio.run(svc.embed_snapshot(1))
    else:
        asyncio.run(svc.embed_snapshot(1))
    assert len(calls) == 2 and len(finished) == 2
    assert svc.index.embedded(1) == (1 if mode == 'unavailable' else 0)


def prepare_overview(svc, monkeypatch):
    asyncio.run(svc.scan())
    topics = module.TOPICS[:3]
    monkeypatch.setattr(module, 'topics_for', lambda present: topics)
    sources = svc.index.search('login', svc.index.active_scan())
    monkeypatch.setattr(svc.index, 'search_many', lambda *args, **kwargs: sources)
    return topics


@pytest.mark.parametrize('action,message', [('cancel','cancelled'), ('revoke','changed')])
def test_overview_analysis_keeps_event_loop_responsive_and_honors_cancellation(setup, monkeypatch, action, message):
    svc, _ = setup
    prepare_overview(svc, monkeypatch)
    release = threading.Event()
    loop = None
    started = None

    def slow_analysis(index, scan):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5), 'Analysis blocked the event loop'
        return []

    monkeypatch.setattr(module, 'derive_facts', slow_analysis)
    monkeypatch.setattr(module, 'build_diagrams', lambda *args: pytest.fail('Cancelled analysis continued'))

    async def scenario():
        nonlocal loop, started
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        task = asyncio.create_task(svc.build_overview())
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            # This coroutine must run while the analysis worker is still blocked.
            assert not task.done()
            if action == 'cancel':
                svc.cancel.set()
            else:
                svc.index.invalidate()
        finally:
            release.set()
        with pytest.raises(SourceError, match=message):
            await task
        assert svc.index.overview(COMMIT) is None

    asyncio.run(scenario())


def test_overview_publishes_fast_topic_early_but_preserves_final_order(setup, monkeypatch):
    svc, _ = setup
    topics = prepare_overview(svc, monkeypatch)

    async def scenario():
        release, saved_fast = asyncio.Event(), asyncio.Event()
        original = svc.index.save_overview
        active = peak = 0

        def save(scan_id, commit, payload):
            original(scan_id, commit, payload)
            if [s['key'] for s in payload['sections']] == [topics[1]['key']]:
                saved_fast.set()

        async def model(question, sources):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                if question != topics[1]['ask']:
                    await release.wait()
                return {'statements':[], 'missing_information':'Fixture explanation'}
            finally:
                active -= 1

        svc.index.save_overview = save
        svc.generator = model
        task = asyncio.create_task(svc.build_overview())
        try:
            await asyncio.wait_for(saved_fast.wait(), 2)
            assert not task.done()
            saved = svc.index.overview(COMMIT)
            assert saved['topics_done'] == 1 and not saved['complete']
        finally:
            release.set()
        result = await asyncio.wait_for(task, 2)
        assert peak == 2 and active == 0
        assert [s['key'] for s in result['sections']] == [t['key'] for t in topics]
        assert result['complete']

    asyncio.run(scenario())


def test_overview_batches_query_vectors_before_any_generation(setup, monkeypatch):
    svc, _ = setup
    topics = prepare_overview(svc, monkeypatch)
    monkeypatch.setattr(svc.index, 'embedded', lambda scan_id: 1)
    calls = []

    async def vectors(texts):
        calls.append(('vectors', len(texts)))
        return [[1.0,0.0] for _ in texts]

    async def model(question, sources):
        calls.append(('model', 1))
        return {'statements':[], 'missing_information':'Fixture explanation'}

    monkeypatch.setattr(embed, 'vectors', vectors)
    svc.generator = model
    assert asyncio.run(svc.build_overview())['complete']
    assert calls == [('vectors', sum(len(t['queries']) for t in topics))] + [('model',1)] * 3


def test_revocation_during_calibration_cannot_save_stale_threshold(setup, monkeypatch):
    svc, _ = setup
    prepare_embeddings(svc, monkeypatch)
    svc.calibrate = Service.calibrate.__get__(svc)

    async def vectors(texts):
        if texts == list(embed.PROBES):
            svc.index.invalidate()
        return [[1.0,0.0] for _ in texts]

    monkeypatch.setattr(embed, 'vectors', vectors)
    with pytest.raises(SourceError, match='changed'):
        asyncio.run(svc.embed_snapshot(1))
    assert svc.index.embedded(1) == 0
    assert svc.index.calibration(1, 'fixture') is None


def test_overview_model_failure_preserves_other_completed_topics(setup, monkeypatch):
    svc, _ = setup
    topics = prepare_overview(svc, monkeypatch)

    async def model(question, sources):
        if question == topics[1]['ask']:
            raise SourceError('ollama', 'Fixture model failure')
        await asyncio.sleep(.001)
        return {'statements':[], 'missing_information':'Fixture explanation'}

    svc.generator = model
    result = asyncio.run(svc.build_overview())
    assert result['complete'] and len(result['sections']) == 3
    assert [bool(section['error']) for section in result['sections']] == [False,True,False]


def test_parallel_runner_drains_failure_and_stops_new_work():
    async def scenario():
        started, finished = [], []

        async def work(item):
            started.append(item)
            try:
                await asyncio.sleep(.001 if item == 0 else .02)
                if item == 0:
                    raise SourceError('network', 'Fixture failure')
                return item
            finally:
                finished.append(item)

        async def publish(item, value):
            pass

        with pytest.raises(SourceError):
            await process_parallel(range(10), work, publish, 2)
        assert started == [0,1] and sorted(finished) == [0,1]

    asyncio.run(scenario())
