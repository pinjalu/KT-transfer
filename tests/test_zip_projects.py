"""ZIP ingestion, workspace boundaries and real scan/answer integration on disposable data."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import stat
import struct
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from auth_helpers import OwnerClient, PASSWORD
from pka.auth_web import cookie_name
from pka import zip_projects
from pka.config import source_url
from pka.connectors.local import LocalSource
from pka.mcp_client import connect
from pka.web import create_app


def archive(files=None):
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in (files or {
            'shop-main/README.md':'# Shop\nLogin verifies a password before creating a session.\nRun python app.py.\n',
            'shop-main/app.py':'def login(password):\n    return check_password(password)\n',
        }).items():
            z.writestr(name, content)
    return stream.getvalue()


@asynccontextmanager
async def factory(cfg, demo=False):
    yield LocalSource(cfg['repo'])


async def model(question, sources):
    return {'statements':[{'text':'Login verifies a password before creating a session.',
                           'source_ids':[sources[0]['source_id']]}], 'missing_information':''}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path/'data'))
    monkeypatch.setenv('PKA_LOG_DIR', str(tmp_path/'logs'))
    value = create_app(db_path=tmp_path/'index.sqlite3', connector_factory=factory)
    value.state.service.generator = model
    return value


def upload(client, payload=None, name='shop.zip', **kwargs):
    return client.post('/api/zip/upload', params={'filename':name},
                       content=archive() if payload is None else payload,
                       headers={'content-type':'application/zip', **kwargs})


def wait_scan(client):
    for _ in range(200):
        status = client.get('/api/status').json()
        if not status['busy']:
            assert status['ready'], status
            return status
        time.sleep(.01)
    pytest.fail('Background scan did not finish.')


def test_zip_scan_answers_overview_citations_and_restart(app, tmp_path):
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as client:
        response = upload(client)
        assert response.status_code == 200, response.text
        status = wait_scan(client)
        assert status['settings']['project_name'] == 'shop'
        assert status['settings']['source_kind'] == 'zip'
        assert status['scan']['read'] == 2
        answer = client.post('/api/ask', json={'question':'How does login verify passwords?'}).json()
        assert answer['statements'] and answer['sources']
        assert all('&source=zip' in s['url'] for s in answer['sources'])
        source = client.get('/api/local-source', params={'path':'app.py', 'snapshot':status['scan']['commit']})
        assert source.status_code == 200 and source.json()['source_kind'] == 'zip'
        assert 'check_password' in source.text
        assert client.post('/api/overview').status_code == 200
        wait_scan(client)
        overview = client.get('/api/overview').json()
        assert overview['available'] and not overview['overview']['plain_language_update_available']
        from pka.plain_language import STYLE_VERSION
        assert overview['overview']['explanation_style'] == STYLE_VERSION
        older = dict(overview['overview'])
        older['explanation_style'] = 'plain-language-v1'
        app.state.service.index.save_overview(status['scan']['id'], status['scan']['commit'], older)
        assert client.get('/api/overview').json()['overview']['plain_language_update_available']
        coverage = client.get('/api/import-coverage').json()['sources']
        assert coverage['zip']['available'] and 'github' not in coverage
        commit = status['scan']['commit']
    restarted = create_app(db_path=tmp_path/'index.sqlite3', connector_factory=factory)
    with OwnerClient(restarted, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as client:
        status = client.get('/api/status').json()
        assert status['awaiting_project'] and status['stored_project']['source_kind'] == 'zip'
        assert client.post('/api/zip/resume').json()['reconnected']
        assert client.get('/api/status').json()['scan']['commit'] == commit


def test_member_uploads_are_isolated_and_cannot_select_host_paths(app):
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as owner:
        assert upload(owner).status_code == 200
        owner_status = wait_scan(owner)
        app.state.auth.create_member('member', PASSWORD)
        token = app.state.auth.login('member', PASSWORD, 'http://localhost:8000')
        with TestClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'},
                        cookies={cookie_name(app.state.auth):token}) as member:
            assert member.post('/api/zip/resume').status_code == 409
            assert upload(member, archive({'member.py':'def member_only():\n    return 42\n'}), name='member.zip').status_code == 200
            member_status = wait_scan(member)
            assert member_status['settings']['repo'] != owner_status['settings']['repo']
            assert member.get('/api/local-source', params={'path':'app.py', 'snapshot':owner_status['scan']['commit']}).status_code == 409
            source = member.get('/api/local-source', params={'path':'member.py', 'snapshot':member_status['scan']['commit']})
            assert source.status_code == 200 and 'member_only' in source.text
            assert member.post('/api/config', json={'source_kind':'local', 'local_path':owner_status['settings']['repo'][4:]}).status_code == 403
            assert member.post('/api/config', json={'source_kind':'zip', 'repo':owner_status['settings']['repo']}).status_code == 422
        assert owner.get('/api/status').json()['settings']['project_name'] == 'shop'


def test_upload_auth_headers_size_and_failed_replacement_preserve_project(app, monkeypatch):
    with TestClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as client:
        assert upload(client).status_code == 401
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as client:
        assert upload(client, **{'x-pka-request':''}).status_code == 403
        assert upload(client, origin='https://elsewhere.example').status_code == 403
        assert upload(client).status_code == 200
        before = wait_scan(client)
        assert upload(client, b'not a zip').status_code == 422
        assert upload(client, name='project.txt').status_code == 422
        assert client.get('/api/status').json()['settings'] == before['settings']
        assert len(list(zip_projects.storage(app.state.service.index.path).iterdir())) == 1
        monkeypatch.setattr(zip_projects, 'MAX_UPLOAD_BYTES', 64)
        assert upload(client).status_code == 413
        assert upload(client, **{'content-length':'0'}).status_code == 413
        assert client.get('/api/status').json()['scan']['commit'] == before['scan']['commit']


def test_replacement_removes_old_snapshot_and_old_citations(app):
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request':'1'}) as client:
        assert upload(client).status_code == 200
        before = wait_scan(client)
        old = Path(before['settings']['repo'][4:])
        assert upload(client, archive({'new.py':'def new_project():\n    return True\n'}), name='new.zip').status_code == 200
        status = wait_scan(client)
        assert status['settings']['project_name'] == 'new' and not old.exists()
        assert client.get('/api/local-source', params={'path':'app.py', 'snapshot':before['scan']['commit']}).status_code == 409
        assert client.post('/api/config', json={'repo':'acme/shop', 'branch':'main'}).status_code == 200
        assert not client.get('/api/status').json()['settings'].get('local')


@pytest.mark.parametrize('name', ['../escape.py', '/absolute.py', 'C:/drive.py', 'a\\b.py',
                                  'safe/../../escape.py', 'file.py:stream', 'CON.py', 'folder./file.py'])
def test_rejects_unsafe_paths_without_leaving_files(tmp_path, name):
    payload = archive({name:'print(1)'})
    # Windows ZipInfo normalizes backslashes when writing, so put the raw unsafe
    # bytes back into both headers to exercise an archive from another writer.
    if '\\' in name:
        payload = payload.replace(name.replace('\\', '/').encode(), name.encode())
    with pytest.raises(ValueError, match='unsafe'):
        zip_projects.prepare(BytesIO(payload), 'test.zip', tmp_path/'index.sqlite3')
    assert list(zip_projects.storage(tmp_path/'index.sqlite3').iterdir()) == []
    assert not (tmp_path/'escape.py').exists()


def test_rejects_links_duplicates_conflicts_empty_and_expansion_bombs(tmp_path, monkeypatch):
    link = zipfile.ZipInfo('link.py')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    for files in ({link:'../outside.py'}, {'App.py':'a', 'app.py':'b'},
                  {'app.py':'a', 'app.py/nested.py':'b'}, {'only.png':b'\x00\x01'}, {'empty.md':'  \n'}):
        with pytest.raises(ValueError):
            zip_projects.prepare(BytesIO(archive(files)), 'test.zip', tmp_path/'index.sqlite3')
    monkeypatch.setattr(zip_projects, 'MAX_EXPANDED_BYTES', 100)
    with pytest.raises(ValueError, match='expands'):
        zip_projects.prepare(BytesIO(archive({'big.py':'x' * 101})), 'test.zip', tmp_path/'index.sqlite3')
    assert list(zip_projects.storage(tmp_path/'index.sqlite3').iterdir()) == []


def test_encrypted_and_corrupt_files_do_not_leave_a_snapshot(tmp_path):
    payload = bytearray(archive({'app.py':'print(42)\n'}))
    central = payload.index(b'PK\x01\x02')
    encrypted = bytearray(payload)
    struct.pack_into('<H', encrypted, 6, struct.unpack_from('<H', encrypted, 6)[0] | 1)
    struct.pack_into('<H', encrypted, central + 8, struct.unpack_from('<H', encrypted, central + 8)[0] | 1)
    with pytest.raises(ValueError, match='Password-protected'):
        zip_projects.prepare(BytesIO(encrypted), 'test.zip', tmp_path/'index.sqlite3')
    # Flip the CRC in the directory without altering any source file bytes.
    payload[central + 16] ^= 0x01
    with pytest.raises(ValueError, match='could not be read'):
        zip_projects.prepare(BytesIO(payload), 'test.zip', tmp_path/'index.sqlite3')
    assert list(zip_projects.storage(tmp_path/'index.sqlite3').iterdir()) == []


def test_exclusions_limits_and_wrapper_removal(tmp_path, monkeypatch):
    monkeypatch.setattr(zip_projects, 'LIMITS', replace(zip_projects.LIMITS, max_files=2))
    payload = archive({'repo/README.md':'# Hello\n', 'repo/app.py':'print(1)\n', 'repo/z.py':'print(2)\n',
                       'repo/.env':'SECRET=value', 'repo/.aws/config.py':'secret',
                       'repo/node_modules/test.js':'secret', 'repo/image.png':b'\x00'})
    result = zip_projects.prepare(BytesIO(payload), 'my project.zip', tmp_path/'index.sqlite3')
    folder = Path(result['repo'][4:])
    assert sorted(p.name for p in folder.iterdir()) == ['README.md', 'app.py']
    assert result['files'] == 2 and sum(result['skipped'].values()) == 5
    assert result['skipped']['scan_size_limit'] == 1
    assert source_url(result['repo'], 'abc', 'app.py', 2).endswith('&source=zip#L2')


def test_uploaded_zip_uses_real_mcp_reader(tmp_path):
    result = zip_projects.prepare(BytesIO(archive()), 'shop.zip', tmp_path/'index.sqlite3')
    async def read():
        async with connect({'repo':result['repo'], 'branch':'uploaded-snapshot'}) as source:
            await source.begin_snapshot()
            entries = await source.list_files()
            assert {f['path'] for f in entries['files']} == {'README.md', 'app.py'}
            assert 'check_password' in (await source.read_file('app.py'))['text']
    asyncio.run(read())
