"""Acceptance-runner regression tests with stub clients; these are not live evidence."""
import asyncio
from contextlib import asynccontextmanager
import copy
import json
from types import SimpleNamespace

import pytest

from pka import acceptance
from pka.connectors.base import SourceError
from pka.index import Index
from pka.mcp_client import connect as real_connect

COMMIT = 'a' * 40
BLOB = 'b' * 40
SETTINGS = {'repo': 'acme/shop', 'branch': 'main', 'jira': {'project': 'ENG'},
            'slack': {'workspace': 'acme', 'channels': [{'id': 'C001', 'name': 'engineering'}]}}


class Client:
    def __init__(self):
        self.session = self
        self.slack_reads = []
        self.file_reads = []
        self.issue_count = 2
        self.messages = [{'text': 'PRIVATE_MESSAGE_BODY', 'ts': '1720000000.000001'}]
        self.write_tool = False
        self.github_error = None
        self.slow = False
        self.bad_issue = False
        self.bad_blob = False
        self.tools = [SimpleNamespace(annotations=SimpleNamespace(readOnlyHint=True, destructiveHint=False))]

    async def list_tools(self):
        if self.slow:
            await asyncio.sleep(5)
        if self.write_tool:
            self.tools[0].annotations.readOnlyHint = False
        return SimpleNamespace(tools=self.tools)

    async def check_access(self):
        if self.github_error:
            raise self.github_error
        return {'head': COMMIT, 'repo': 'acme/shop', 'branch': 'main'}

    async def begin_snapshot(self):
        return {'commit': COMMIT, 'entries': 2, 'tree_incomplete': False}

    async def list_files(self, cursor):
        if cursor == 0:
            return {'files': [{'path': '.env', 'skip': 'secret', 'sha': BLOB}], 'next_cursor': 1}
        return {'files': [{'path': 'README.md', 'skip': '', 'sha': BLOB}], 'next_cursor': None}

    async def read_file(self, path):
        self.file_reads.append(path)
        return {'text': 'PRIVATE_SOURCE_BODY', 'bytes': 19, 'sha': 'c' * 40 if self.bad_blob else BLOB}

    async def jira_check_access(self):
        return {'account': 'PRIVATE_ACCOUNT_ID'}

    async def jira_projects(self):
        return [{'key': 'ENG'}]

    async def jira_begin_read(self):
        return {'project': 'ENG', 'issues': self.issue_count, 'blocks': self.issue_count}

    async def jira_issues(self, cursor):
        if not self.issue_count:
            return {'blocks': [], 'next_cursor': None}
        key = 'OTHER-1' if self.bad_issue else 'ENG-' + str(cursor + 1)
        return {'blocks': [{'path': 'jira/' + key, 'text': 'PRIVATE_ISSUE_BODY',
                            'url': 'https://acme.atlassian.net/browse/' + key}],
                'next_cursor': 1 if cursor == 0 else None}

    async def jira_check_issues_access(self, keys):
        return {'checked': len(keys)}

    async def slack_channels(self):
        return [{'id': 'C001'}, {'id': 'C999'}]

    async def slack_messages(self, channel_id):
        self.slack_reads.append(channel_id)
        return self.messages


@pytest.fixture
def configured(monkeypatch):
    for key in ('GITHUB_TOKEN', 'JIRA_EMAIL', 'JIRA_API_TOKEN', 'SLACK_USER_TOKEN'):
        monkeypatch.setenv(key, 'DO_NOT_EXPOSE_' + key)
    monkeypatch.setenv('JIRA_SITE', 'https://acme.atlassian.net')
    client = Client()

    @asynccontextmanager
    async def connection(settings, demo=False):
        assert demo is False
        assert settings['repo'] == SETTINGS['repo']
        yield client

    monkeypatch.setattr(acceptance, 'connect', connection)
    return client


def test_all_sources_read_selected_scope_and_report_no_content(configured):
    report = asyncio.run(acceptance.run_checks(copy.deepcopy(SETTINGS)))
    assert report['task_complete'] is True
    assert [r['status'] for r in report['results']] == ['passed'] * 3
    assert configured.file_reads == ['README.md']
    assert configured.slack_reads == ['C001']
    encoded = json.dumps(report)
    for hidden in ('PRIVATE_', 'DO_NOT_EXPOSE_', 'README.md', 'ENG-1'):
        assert hidden not in encoded
    jira = report['results'][1]
    assert next(c for c in jira['checks'] if c['name'] == 'scoped_issue_read')['issues'] == 2


def test_failed_source_does_not_prevent_other_sources_and_error_is_redacted(configured):
    configured.github_error = SourceError('access_denied', 'DO_NOT_EXPOSE_TOKEN upstream response')
    report = asyncio.run(acceptance.run_checks(SETTINGS))
    assert [r['status'] for r in report['results']] == ['failed', 'passed', 'passed']
    assert report['task_complete'] is False
    assert 'DO_NOT_EXPOSE' not in json.dumps(report)


def test_missing_setup_never_connects(monkeypatch):
    monkeypatch.delenv('SLACK_USER_TOKEN', raising=False)
    monkeypatch.setattr(acceptance, 'connect', lambda *a, **k: pytest.fail('Must not connect'))
    report = asyncio.run(acceptance.run_checks({}))
    assert all(r['status'] == 'blocked' for r in report['results'])
    assert not report['task_complete']


@pytest.mark.parametrize('source', ['jira', 'slack'])
def test_empty_data_is_incomplete_not_false_success(configured, source):
    configured.issue_count = 0
    configured.messages = []
    result = asyncio.run(acceptance.run_source(source, SETTINGS))
    assert result['status'] == 'incomplete'


@pytest.mark.parametrize('source,flag', [('jira', 'bad_issue'), ('github', 'bad_blob')])
def test_wrong_scope_or_blob_fails_validation(configured, source, flag):
    setattr(configured, flag, True)
    result = asyncio.run(acceptance.run_source(source, SETTINGS))
    assert result['status'] == 'failed'
    assert result['error_code'] == 'validation'


def test_write_tool_refuses_data_reads(configured):
    configured.write_tool = True
    result = asyncio.run(acceptance.run_source('github', SETTINGS))
    assert result['error_code'] == 'validation'
    assert not configured.file_reads


def test_timeout_is_bounded(configured):
    configured.slow = True
    result = asyncio.run(acceptance.run_source('github', SETTINGS, timeout=0.01))
    assert result['error_code'] == 'timeout'


def test_single_service_success_does_not_complete_all_source_task(configured):
    report = asyncio.run(acceptance.run_checks(SETTINGS, ('jira',)))
    assert report['status'] == 'passed'
    assert report['task_complete'] is False


def test_no_workspace_is_reported_without_changing_settings(configured):
    settings = copy.deepcopy(SETTINGS)
    settings['slack']['workspace'] = ''
    result = asyncio.run(acceptance.run_source('slack', settings))
    assert result['status'] == 'passed'
    assert result['warnings']
    assert settings['slack']['workspace'] == ''


def test_repeated_cursor_cannot_hang_or_pass():
    async def bad_page(cursor):
        return {'files': [], 'next_cursor': cursor}
    with pytest.raises(acceptance.CheckFailure, match='cursor'):
        asyncio.run(acceptance.pages(bad_page, 'files', 3))


def test_cli_reads_settings_without_modifying_index_and_saves_report(configured, tmp_path, monkeypatch, capsys):
    db = tmp_path / 'index.sqlite3'
    Index(db).configure(SETTINGS)
    original = db.read_bytes()
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    output = tmp_path / 'reports' / 'live.json'
    assert acceptance.main(['--output', str(output)]) == 0
    assert json.loads(output.read_text())['task_complete']
    assert db.read_bytes() == original
    assert 'DO_NOT_EXPOSE_' not in capsys.readouterr().out


def test_settings_missing_does_not_create_database(tmp_path):
    db = tmp_path / 'absent.sqlite3'
    assert acceptance.load_settings(db) == {}
    assert not db.exists()


@pytest.mark.parametrize('repo,expected', [('demo/example-shop', 'passed'), ('acme/wrong-repo', 'failed')])
def test_real_mcp_subprocess_and_validation_reporting(monkeypatch, repo, expected):
    @asynccontextmanager
    async def simulated_connection(settings, demo=False):
        assert demo is False  # The production runner never asks to switch to fixtures.
        async with real_connect(settings, demo=True) as client:
            yield client

    monkeypatch.setattr(acceptance, 'connect', simulated_connection)
    result = asyncio.run(acceptance.run_source('github', {'repo': repo, 'branch': 'main'}))
    assert result['status'] == expected
    if expected == 'failed':
        assert result['error_code'] == 'validation', 'Caller validation must not become a generic MCP failure.'
