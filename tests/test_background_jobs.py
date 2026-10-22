"""Job lifecycle checks with controlled connector/model waits, never live accounts."""
import asyncio
from contextlib import asynccontextmanager
import json

import httpx
import pytest

from pka import credentials
from pka.connectors.base import SourceError
from pka.connectors.fixture import FixtureSource
from pka.connectors.jira import issue_block
from pka.index import Index
from pka.service import Service
from pka.web import create_app


def run(coro):
    return asyncio.run(coro)


class ControlledSource(FixtureSource):
    pause = ''
    failure = None
    calls = 0
    denied_channel = ''

    async def checkpoint(self, kind):
        self.calls += 1
        if self.pause == kind:
            self.entered.set()
            await self.release.wait()
        if self.failure:
            raise self.failure

    async def begin_snapshot(self):
        await self.checkpoint('scan')
        return await super().begin_snapshot()

    async def jira_begin_read(self):
        await self.checkpoint('jira')
        return {'issues':1, 'blocks':1}

    async def jira_issues(self, cursor=0):
        return {'blocks':[issue_block('https://acme.atlassian.net',
                {'key':'ENG-1','fields':{'summary':'Authentication verifies passwords before creating sessions'}})],
                'next_cursor':None}

    async def slack_messages(self, channel_id):
        await self.checkpoint('slack')
        if channel_id == self.denied_channel:
            raise SourceError('network', 'Channel temporarily unavailable.')
        return [{'ts':'1700000000.0','user':'U1','text':'Authentication verifies passwords before creating sessions.'}]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_EMBED_MODEL', '')
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(credentials, 'ENV_PATH', tmp_path/'unused.env')
    for key in ('JIRA_SITE','JIRA_EMAIL','JIRA_API_TOKEN','SLACK_USER_TOKEN'):
        monkeypatch.setenv(key, 'fixture-only')
    source = ControlledSource()
    @asynccontextmanager
    async def factory(settings, demo=False):
        yield source
    index = Index(tmp_path/'index.sqlite3')
    index.configure({'repo':'acme/shop','branch':'main'})
    svc = Service(index, demo=True, connector_factory=factory)
    run(svc.scan())
    index.configure_source('jira', {'project':'ENG'})
    index.configure_slack({'workspace':'acme','channels':[{'id':'C1','name':'eng'}]})
    return svc, source, factory


@pytest.mark.parametrize('kind', ['scan','jira','slack','overview'])
def test_cancel_while_queued_never_starts_work_or_loses_snapshot(setup, kind):
    svc, source, _ = setup
    before, calls = svc.index.revision, source.calls
    async def scenario():
        job_id = svc.start_job(kind)
        assert svc.job_status()['state'] == 'queued'
        with pytest.raises(SourceError, match='Another task'):
            svc.start_job(kind)
        svc.cancel_job(job_id)
        await svc.task
        assert svc.job_status()['state'] == 'cancelled'
        assert not svc.busy()
    run(scenario())
    assert svc.index.revision == before and source.calls == calls
    assert svc.index.active_scan()
    assert svc.index.latest_job()['state'] == 'cancelled'


@pytest.mark.parametrize('kind', ['scan','jira','slack','overview'])
def test_cancel_during_request_finishes_safely_and_unlocks(setup, kind):
    svc, source, _ = setup
    if kind == 'jira':
        run(svc.read_jira('ENG'))
    if kind == 'slack':
        run(svc.read_slack('acme', svc.index.settings()['slack']['channels']))
    imported = svc.index.source_import(kind) if kind in {'jira','slack'} else None
    async def scenario():
        source.entered, source.release = asyncio.Event(), asyncio.Event()
        source.pause = kind
        if kind == 'overview':
            svc.demo = False
            async def model(question, sources):
                source.entered.set()
                await source.release.wait()
                return {'statements':[], 'missing_information':'NEVER_PUBLISH_CANCELLED_RESULT'}
            svc.generator = model
        job_id = svc.start_job(kind)
        await asyncio.wait_for(source.entered.wait(), 2)
        svc.cancel_job(job_id)
        assert svc.job_status()['state'] == 'cancelling'
        assert svc.busy()
        source.release.set()
        await asyncio.wait_for(svc.task, 3)
        assert svc.job_status()['state'] == 'cancelled'
        assert svc.job_status()['can_retry']
        assert not svc.busy()
    run(scenario())
    if imported:
        assert svc.index.source_import(kind) == imported
    if kind == 'overview':
        scan = svc.index.active_scan()
        assert 'NEVER_PUBLISH_CANCELLED_RESULT' not in json.dumps(svc.index.overview(scan['commit']))


def test_failed_scan_has_explicit_retry_and_new_attempt_id(setup):
    svc, source, _ = setup
    async def scenario():
        source.failure = SourceError('network', 'Network temporarily unavailable.')
        first = svc.start_job('scan')
        await svc.task
        job = svc.job_status()
        assert job['state'] == 'failed' and job['code'] == 'network'
        assert job['can_retry'] and job['error']
        calls = source.calls
        await asyncio.sleep(0)
        assert source.calls == calls, 'Retries must require an explicit request'
        source.failure = None
        second = svc.start_job('scan', retry_id=first)
        assert second != first
        with pytest.raises(SourceError):
            svc.cancel_job(first)
        await svc.task
        assert svc.job_status()['state'] == 'succeeded'
        assert svc.job_status()['attempt'] == 2 and svc.job['retry_of'] == first
        assert not svc.job_status()['can_retry'] and not svc.job_error
        with pytest.raises(SourceError):
            svc.start_job('scan', retry_id=first)
    run(scenario())


def test_partial_slack_read_can_be_retried_after_channel_recovers(setup):
    svc, source, _ = setup
    svc.index.configure_slack({'workspace':'acme','channels':[{'id':'C1','name':'eng'},{'id':'C2','name':'ops'}]})
    async def scenario():
        source.denied_channel = 'C2'
        job_id = svc.start_job('slack')
        await svc.task
        assert svc.job_status()['state'] == 'partial'
        assert svc.job_status()['can_retry']
        source.denied_channel = ''
        svc.start_job('slack', retry_id=job_id)
        await svc.task
        assert svc.job_status()['state'] == 'succeeded'
        assert svc.index.settings()['slack']['import_report']['failed'] == 0
    run(scenario())


@pytest.mark.parametrize('state', ['queued','running','cancelling'])
def test_restart_marks_unfinished_job_interrupted_without_restarting_it(setup, state):
    svc, source, factory = setup
    job = svc._new_job('overview')
    job['state'] = state
    svc.index.save_job(job)
    revision, calls = svc.index.revision, source.calls
    reopened = Index(svc.index.path)
    reopened.recover()
    other = Service(reopened, demo=True, connector_factory=factory)
    assert other.job_status()['state'] == 'interrupted'
    assert other.job_status()['can_retry']
    assert other.task is None and other.index.revision == revision and source.calls == calls


@pytest.mark.parametrize('kind', ['scan','jira','slack','overview'])
def test_retry_refuses_changed_source_selection(setup, kind):
    svc, _, _ = setup
    async def scenario():
        job_id = svc.start_job(kind)
        svc.cancel_job(job_id)
        await svc.task
        if kind == 'jira':
            svc.index.configure_source('jira', {'project':'OPS'})
        elif kind in {'slack','overview'}:
            svc.index.configure_slack({'workspace':'acme','channels':[]})
        else:
            svc.index.configure({'repo':'acme/other','branch':'main'})
        assert not (svc.job_status() or {}).get('can_retry')
        with pytest.raises(SourceError):
            svc.start_job(kind, retry_id=job_id)
    run(scenario())


def test_api_job_controls_survive_navigation_and_reject_duplicate_stale_requests(setup):
    old, source, factory = setup
    app = create_app(False, old.index.path, connector_factory=factory)
    svc = app.state.service
    async def scenario():
        source.pause = 'scan'
        source.entered, source.release = asyncio.Event(), asyncio.Event()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost:8000',
                                     headers={'X-PKA-Request':'1'}) as client:
            await client.post('/api/config',json={'repo':'acme/shop','branch':'main'})
            response = await client.post('/api/scan')
            assert response.status_code == 200
            job_id = response.json()['job_id']
            await source.entered.wait()
            assert (await client.post('/api/scan')).status_code == 409
            assert (await client.get('/architecture')).status_code == 200
            status = (await client.get('/api/status')).json()
            assert status['job']['id'] == job_id and status['job']['state'] == 'running'
            assert 'scope' not in status['job'] and 'files' not in (status['job']['progress'] or {})
            assert (await client.post(f'/api/jobs/{job_id+1}/cancel')).status_code == 409
            assert (await client.post(f'/api/jobs/{job_id}/cancel')).status_code == 200
            assert (await client.get('/api/status')).json()['job']['state'] == 'cancelling'
            source.release.set()
            await svc.task
            assert (await client.get('/api/status')).json()['job']['state'] == 'cancelled'
            response = await client.post(f'/api/jobs/{job_id}/retry')
            assert response.status_code == 200 and response.json()['job_id'] != job_id
            await svc.task
            assert (await client.get('/api/status')).json()['job']['state'] == 'succeeded'
            assert (await client.post(f'/api/jobs/{job_id}/retry')).status_code == 409
    run(scenario())


def test_cancellation_after_embedding_does_not_report_scan_success(setup, monkeypatch):
    svc, _, _ = setup
    monkeypatch.setattr('pka.service.embed.enabled', lambda: True)
    async def embedding(scan_id):
        svc.cancel_job(svc.job['id'])
        return 0
    svc.embed_snapshot = embedding
    async def scenario():
        svc.start_job('scan')
        await svc.task
        assert svc.job_status()['state'] == 'cancelled'
        assert svc.index.active_scan() is None
    run(scenario())


def test_job_history_is_bounded_and_keeps_the_latest_record(setup):
    svc, _, _ = setup
    for _ in range(35):
        svc._new_job('scan')
    with svc.index.db() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 30
    assert svc.index.latest_job()['id'] == svc.job['id']
