"""Live, read-only connector acceptance. No source content is persisted or printed."""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time

from pka.config import LIMITS, ROOT, now
from pka.connectors.base import SourceError
from pka.connectors.slack import transcript
from pka.mcp_client import connect
from pka import credentials

SOURCES = ('github', 'jira', 'slack')
ERROR_MESSAGES = {
    'access_denied': 'The service rejected access. Reconnect the account and check its read permissions.',
    'network': 'The service could not be reached. Check the network and retry.',
    'rate_limit': 'The service rate limit prevented the check. Retry after its allowance resets.',
    'mcp': 'The local MCP connection failed. Check the Python environment and retry.',
    'scope': 'The selected scope was refused. Check the saved repository, project or channel selection.',
}


class CheckFailure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise CheckFailure(message)


def load_settings(database: Path) -> dict:
    """Read the saved selection without creating, migrating or changing the app database."""
    if not database.exists():
        return {}
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
    settings = json.loads(row[0]) if row else {}
    if not isinstance(settings, dict):
        raise ValueError('Invalid saved settings.')
    return settings


def missing_setup(source, settings):
    if source == 'github':
        return [] if settings.get('repo') and settings.get('branch') else ['repository and branch']
    if source == 'jira':
        missing = [name for name in ('JIRA_SITE', 'JIRA_EMAIL', 'JIRA_API_TOKEN') if not credentials.getenv(name, '').strip()]
        if not (settings.get('jira') or {}).get('project'):
            missing.append('selected Jira project')
        return missing
    missing = [] if credentials.getenv('SLACK_USER_TOKEN', '').strip() else ['SLACK_USER_TOKEN']
    channels = (settings.get('slack') or {}).get('channels') or []
    if not channels or any(not isinstance(c, dict) or not c.get('id') for c in channels):
        missing.append('selected Slack channels')
    return missing


def record(result, name, **evidence):
    result['checks'].append({'name': name, 'status': 'passed', **evidence})


async def pages(fetch, key, limit):
    """Bound page traversal and reject repeated/backwards cursors."""
    cursor, items = 0, []
    for _ in range(limit):
        page = await fetch(cursor)
        require(isinstance(page, dict) and isinstance(page.get(key), list), 'A connector returned an invalid page.')
        items.extend(page[key])
        after = page.get('next_cursor')
        if after is None:
            return items
        require(type(after) is int and after > cursor, 'A connector returned a repeated or invalid cursor.')
        cursor = after
    raise CheckFailure('A connector exceeded the acceptance page limit.')


async def check_github(client, settings, result):
    access = await client.check_access()
    require(bool(re.fullmatch(r'[0-9a-f]{40}', access.get('head', ''))), 'GitHub did not return a valid branch commit.')
    require((access.get('repo'), access.get('branch')) == (settings['repo'], settings['branch']),
            'GitHub returned a different repository or branch.')
    record(result, 'repository_access')
    snapshot = await client.begin_snapshot()
    require(bool(re.fullmatch(r'[0-9a-f]{40}', snapshot.get('commit', ''))), 'GitHub did not pin a valid snapshot.')
    files = await pages(client.list_files, 'files', LIMITS.max_entries // 200 + 1)
    require(len(files) == snapshot.get('entries'), 'GitHub manifest count did not match the snapshot.')
    record(result, 'snapshot_manifest', commit=snapshot['commit'], entries=len(files),
           tree_incomplete=bool(snapshot.get('tree_incomplete')))
    if snapshot.get('tree_incomplete'):
        result['warnings'].append('The manifest was truncated by the connector. This is a sample read, not a full scan.')
    candidates = [f for f in files if not f.get('skip')][:3]
    for candidate in candidates:
        file = await client.read_file(candidate['path'])
        if file.get('skip') or not file.get('text', '').strip():
            continue
        require(file.get('sha') == candidate.get('sha'), 'The read file did not match its pinned blob.')
        record(result, 'pinned_file_read', bytes=file.get('bytes'), sampled_files=1)
        return
    result['status'] = 'incomplete'
    result['message'] = 'Access worked, but no non-empty supported file was read from the first three candidates.'


async def check_jira(client, settings, result):
    access = await client.jira_check_access()
    require(bool(access.get('account')), 'Jira did not return an authenticated account.')
    record(result, 'authenticated_account')
    project = settings['jira']['project']
    projects = await client.jira_projects()
    require(any(p.get('key') == project for p in projects), 'The selected Jira project was not visible.')
    record(result, 'selected_project_visible')
    snapshot = await client.jira_begin_read()
    require(snapshot.get('project') == project, 'Jira read a different project.')
    max_blocks = LIMITS.jira_max_issues * (LIMITS.jira_max_issue_chars // (LIMITS.chunk_chars//2) + 1)
    require(type(snapshot.get('blocks')) is int and 0 <= snapshot['blocks'] <= max_blocks,
            'The Jira excerpt count was outside the configured limits.')
    blocks = await pages(client.jira_issues, 'blocks', max_blocks // 25 + 1)
    require(len(blocks) == snapshot['blocks'], 'The Jira excerpt count did not match its read result.')
    keys = []
    for block in blocks:
        key = block.get('path', '').removeprefix('jira/')
        require(bool(re.fullmatch(re.escape(project) + r'-[0-9]+', key, re.I)), 'An issue was outside the selected Jira project.')
        require(block.get('url') == os.environ['JIRA_SITE'].strip().rstrip('/') + '/browse/' + key,
                'A Jira issue citation did not match the selected site.')
        require(isinstance(block.get('text'), str) and bool(block['text'].strip()), 'A Jira issue had no readable text.')
        keys.append(key)
    keys = sorted(set(keys))
    require(len(keys) == snapshot.get('issues'), 'The Jira issue count did not match its read result.')
    record(result, 'scoped_issue_read', issues=len(keys), citations_checked=len(blocks))
    if not blocks:
        result['status'] = 'incomplete'
        result['message'] = 'Access worked, but the project had no visible issues to validate a content read.'
        return
    checked = await client.jira_check_issues_access(keys)
    require(checked.get('checked') == len(keys), 'Jira did not revalidate every returned issue.')
    record(result, 'issue_access_rechecked', issues=len(keys))


async def check_slack(client, settings, result):
    channels = await client.slack_channels()
    visible = {c.get('id') for c in channels}
    selected = (settings.get('slack') or {}).get('channels') or []
    require(all(c['id'] in visible for c in selected), 'A selected Slack channel was not visible.')
    record(result, 'selected_channels_visible', channels=len(selected))
    total = 0
    workspace = (settings.get('slack') or {}).get('workspace') or ''
    for channel in selected:
        read = await client.slack_read(channel['id']) if hasattr(client, 'slack_read') else None
        messages = read['messages'] if read else await client.slack_messages(channel['id'])
        require(isinstance(messages, list), 'Slack did not return a message list.')
        for message in messages:
            require(isinstance(message, dict) and isinstance(message.get('text'), str) and message['text'].strip(),
                    'Slack returned an unreadable message.')
            require(bool(re.fullmatch(r'[0-9]+\.[0-9]+', str(message.get('ts', '')))), 'Slack returned an invalid message timestamp.')
        total += len(messages)
        record(result, 'scoped_channel_read', channel_id=channel['id'], messages=len(messages),
               thread_replies=sum(bool(m.get('in_thread')) for m in messages))
        if messages and (workspace or all(m.get('permalink') for m in messages)):
            blocks = transcript(channel.get('name', channel['id']), messages, workspace, channel['id'])
            require(bool(blocks) and all(re.fullmatch(r'https://[a-zA-Z0-9-]+\.slack\.com/archives/'+re.escape(channel['id'])+r'/p\d+', b['url']) for b in blocks), 'Slack citation construction failed.')
            record(result, 'message_citations_built', blocks=len(blocks))
        if read and messages:
            require(bool(read.get('snapshot')), 'Slack did not return a message snapshot.')
            verified = await client.slack_check_channel_access(channel['id'], snapshot_digest=read['snapshot'])
            require(verified.get('snapshot') == read['snapshot'], 'Slack messages changed or could not be rechecked.')
            record(result, 'message_snapshot_rechecked', channel_id=channel['id'])
        if messages and not workspace and not all(m.get('permalink') for m in messages):
            result['warnings'].append('Some Slack message links were unavailable. Set the workspace name or retry the read.')
    if not total:
        result['status'] = 'incomplete'
        result['message'] = 'History access worked, but no readable messages were available to validate a content read.'


async def run_source(source, settings, timeout=180):
    result = {'source': source, 'status': 'passed', 'checks': [], 'warnings': []}
    missing = missing_setup(source, settings)
    if missing:
        result.update(status='blocked', message='Configure: ' + ', '.join(missing) + '.')
        return result
    started = time.monotonic()

    async def exercise():
        # These defaults allow independent Jira/Slack checks before GitHub is configured.
        scoped = {'repo': '', 'branch': '', **settings}
        invalid = None
        async with connect(scoped, demo=False) as client:
            # The shared connection converts exceptions from its caller to MCP errors.
            # Keep our validation result until the subprocess has closed normally.
            try:
                tools = (await client.session.list_tools()).tools
                require(bool(tools) and all(t.annotations and t.annotations.readOnlyHint is True and
                            t.annotations.destructiveHint is not True for t in tools),
                        'The MCP server exposed a tool without read-only annotations.')
                record(result, 'read_only_mcp_tools', tools=len(tools))
                await {'github': check_github, 'jira': check_jira, 'slack': check_slack}[source](client, scoped, result)
            except CheckFailure as exc:
                invalid = exc
        if invalid:
            raise invalid

    try:
        await asyncio.wait_for(exercise(), timeout=timeout)
    except asyncio.TimeoutError:
        result.update(status='failed', error_code='timeout', message='The live check exceeded its time limit.')
    except CheckFailure as exc:
        result.update(status='failed', error_code='validation', message=str(exc))
    except SourceError as exc:
        # Do not serialize exception text, HTTP response bodies or an untrusted upstream code.
        code = exc.code if exc.code in ERROR_MESSAGES else 'connector'
        result.update(status='failed', error_code=code, message=ERROR_MESSAGES.get(code, 'The connector could not complete the read. Check the connection in the app.'))
    except Exception:
        result.update(status='failed', error_code='unexpected', message='The acceptance check encountered an unexpected error. No response data was recorded.')
    result['elapsed_seconds'] = round(time.monotonic() - started, 2)
    return result


async def run_checks(settings, sources=SOURCES, timeout=180):
    report = {'task_id': '5.1', 'mode': 'live MCP connections', 'started_at': now(),
              'coverage': 'Scoped reads only. GitHub samples one file; Jira and Slack use the configured connector limits. No model or UI acceptance.',
              'results': []}
    for source in sources:
        report['results'].append(await run_source(source, settings, timeout))
    report['finished_at'] = now()
    report['status'] = 'passed' if all(r['status'] == 'passed' for r in report['results']) else 'incomplete'
    report['task_complete'] = set(sources) == set(SOURCES) and report['status'] == 'passed'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=('all',) + SOURCES, default='all')
    parser.add_argument('--timeout', type=float, default=180, help='Maximum seconds per source (5 to 600).')
    parser.add_argument('--output', type=Path, help='JSON report path. Defaults to data/acceptance/.')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 5 <= args.timeout <= 600:
        parser.error('--timeout must be between 5 and 600 seconds.')
    data = Path(os.getenv('PKA_DATA_DIR', str(ROOT / 'data')))
    try:
        settings = load_settings(data / 'index.sqlite3')
    except (sqlite3.Error, OSError, ValueError):
        print('Could not read the saved application settings. Open Connections and save your selection first.')
        return 1
    selected = SOURCES if args.source == 'all' else (args.source,)
    with credentials.owner_credentials(data / 'index.sqlite3'):
        report = asyncio.run(run_checks(settings, selected, args.timeout))
    output = args.output or data / 'acceptance' / ('connections-' + now().replace(':', '-') + '.json')
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    except OSError:
        print('The checks finished, but the report could not be saved. Choose a writable --output path.')
        return 1
    for result in report['results']:
        print(f'{result["source"]}: {result["status"]}. ' + result.get('message', ''))
        for warning in result['warnings']:
            print('  Note: ' + warning)
    print('Report:', output)
    print('Task 5.1:', 'complete' if report['task_complete'] else 'not complete')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
