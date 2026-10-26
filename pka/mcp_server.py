"""The only MCP server process; its selected scope is fixed at launch.

Every platform is reached the same way. The repository, the Jira project and the list of Slack
channels are all read from the environment when this process starts, so a tool argument can
never reach something the user did not choose: a channel outside the saved list is refused here
rather than trusted because the caller asked for it.

Credentials live only in this process. The web application passes them in at launch and never
holds a token in the request path again.

Every tool is registered whether or not its credentials are present, because the client checks
the tool set against a fixed allowlist and a set that changes with configuration could not be
checked that way. A platform that cannot be reached refuses when it is called instead.
"""
import logging
import os
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pka.connectors.base import SourceError
from pka.config import LIMITS
from pka.connectors.github import GitHubSource
from pka.connectors.local import LocalSource, is_local
from pka.connectors.fixture import FixtureSource
from pka.connectors.jira import JiraSource, issue_blocks
from pka.connectors.slack import SlackSource

logging.disable(logging.CRITICAL)
server = FastMCP('Project Knowledge — read only', log_level='CRITICAL')
DEMO = os.getenv('PKA_DEMO') == '1'
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)

# Scope for this run. Fixed here, never taken from a tool argument.
JIRA_PROJECT = os.getenv('PKA_JIRA_PROJECT', '')
SLACK_CHANNELS = {c for c in os.getenv('PKA_SLACK_CHANNELS', '').split(',') if c}
JIRA_PAGE = 25

_built = {}
_jira_blocks = []


def github():
    """Build the repository reader on first use, so listing a platform needs no repository yet.

    Nothing is constructed at import any more. The channel and project listings run before a
    repository has been chosen, and a server that insisted on one at startup could not serve
    them at all.
    """
    if 'github' not in _built:
        _built['github'] = FixtureSource() if DEMO else GitHubSource(
            os.getenv('PKA_REPO',''), os.getenv('PKA_BRANCH',''), os.getenv('GITHUB_TOKEN',''))
    return _built['github']


def local():
    if DEMO or not is_local(os.getenv('PKA_REPO', '')):
        raise SourceError('scope', 'No local folder was selected for this connector.')
    if 'local' not in _built:
        _built['local'] = LocalSource(os.environ['PKA_REPO'])
    return _built['local']


def jira() -> JiraSource:
    """Build the Jira reader on first use, so a missing token refuses one call, not startup."""
    if DEMO:
        raise SourceError('jira', 'Example mode does not connect to Jira.')
    if 'jira' not in _built:
        _built['jira'] = JiraSource(os.getenv('JIRA_SITE',''), os.getenv('JIRA_EMAIL',''),
                                    os.getenv('JIRA_API_TOKEN',''))
    return _built['jira']


def slack() -> SlackSource:
    """Build the Slack reader on first use, for the same reason."""
    if DEMO:
        raise SourceError('slack', 'Example mode does not connect to Slack.')
    if 'slack' not in _built:
        _built['slack'] = SlackSource(os.getenv('SLACK_USER_TOKEN',''))
    return _built['slack']


async def attempt(work):
    try:
        return {'ok':True,'data':await work()}
    except SourceError as exc:
        return {'ok':False,'code':exc.code,'error':str(exc)}
    except Exception:
        return {'ok':False,'code':'connector','error':'Connector failed. No upstream response or credentials were logged.'}


async def guarded_on(build, name, **kwargs):
    """Call one method on a platform built on demand; a build failure is reported, not raised."""
    async def work():
        return await getattr(build(), name)(**kwargs)
    return await attempt(work)

@server.tool(annotations=READ_ONLY)
async def github_check_access(commit: str = '') -> dict:
    """Check access and branch head for the one explicitly selected repository."""
    return await guarded_on(github, 'check_access', commit=commit)

@server.tool(annotations=READ_ONLY)
async def github_begin_snapshot(reusable: dict[str, str] | None = None) -> dict:
    """Resolve the selected branch to one commit and enumerate its files."""
    if reusable and len(reusable) > LIMITS.max_files:
        return {'ok':False, 'code':'scope', 'error':'Too many reusable files.'}
    # Demo fixtures do not need request budgeting.
    return await guarded_on(github, 'begin_snapshot', **({'reusable':reusable} if reusable and not DEMO else {}))

@server.tool(annotations=READ_ONLY)
async def github_list_files(cursor: int = 0) -> dict:
    """Read one manifest page, restricted to the current snapshot."""
    return await guarded_on(github, 'list_files', cursor=cursor)

@server.tool(annotations=READ_ONLY)
async def github_read_file(path: str) -> dict:
    """Read one allowed file from the resolved commit; never execute it."""
    return await guarded_on(github, 'read_file', path=path)


@server.tool(annotations=READ_ONLY)
async def local_check_access(commit: str = '') -> dict:
    """Check the selected local folder's current bounded snapshot."""
    return await guarded_on(local, 'check_access', commit=commit)


@server.tool(annotations=READ_ONLY)
async def local_begin_snapshot() -> dict:
    """Snapshot the local folder pinned at process launch. Never execute project code."""
    return await guarded_on(local, 'begin_snapshot')


@server.tool(annotations=READ_ONLY)
async def local_list_files(cursor: int = 0) -> dict:
    """List one page of the selected local snapshot."""
    return await guarded_on(local, 'list_files', cursor=cursor)


@server.tool(annotations=READ_ONLY)
async def local_read_file(path: str) -> dict:
    """Read an allowed file whose digest still matches the local snapshot."""
    return await guarded_on(local, 'read_file', path=path)

@server.tool(annotations=READ_ONLY)
async def jira_check_access() -> dict:
    """Confirm the Jira credentials actually sign in before anything they return is believed."""
    return await guarded_on(jira, 'check_access')

@server.tool(annotations=READ_ONLY)
async def jira_check_issues_access(issue_keys: list[str], snapshots: dict[str, str] | None = None) -> dict:
    """Revalidate saved issues against the project fixed at server launch."""
    return await guarded_on(jira, 'check_issues_access', project_key=JIRA_PROJECT, issue_keys=issue_keys, snapshots=snapshots)

@server.tool(annotations=READ_ONLY)
async def jira_list_projects() -> dict:
    """List the projects this account can see. Reading one still needs it chosen at launch."""
    return await guarded_on(jira, 'projects')

@server.tool(annotations=READ_ONLY)
async def jira_begin_read() -> dict:
    """Read the one project chosen at launch and hold its issues as readable blocks."""
    async def work():
        if not JIRA_PROJECT:
            raise SourceError('scope', 'No Jira project was chosen for this run.')
        reader = jira()
        issues = await reader.issues(JIRA_PROJECT)
        _jira_blocks.clear()
        _jira_blocks.extend(block for issue in issues for block in issue_blocks(reader.site, issue))
        return {'project':JIRA_PROJECT,'issues':len(issues),'blocks':len(_jira_blocks),
                'coverage':getattr(reader, 'last_coverage', None)}
    return await attempt(work)

@server.tool(annotations=READ_ONLY)
async def jira_list_issues(cursor: int = 0) -> dict:
    """One page of issue blocks from the snapshot, bounded the way the file manifest is."""
    async def work():
        start = max(0, int(cursor))
        page = _jira_blocks[start:start+JIRA_PAGE]
        after = start + JIRA_PAGE
        return {'blocks':page,'next_cursor':after if after < len(_jira_blocks) else None}
    return await attempt(work)

@server.tool(annotations=READ_ONLY)
async def slack_list_channels() -> dict:
    """List the channels this account can see. Reading one still needs the saved allowlist."""
    return await guarded_on(slack, 'channels')

@server.tool(annotations=READ_ONLY)
async def slack_check_channel_access(channel_id: str, snapshot_digest: str = '') -> dict:
    """Verify history access without importing messages or widening the saved allowlist."""
    if channel_id not in SLACK_CHANNELS:
        return {'ok':False,'code':'scope','error':'That channel is not in the saved allowlist.'}
    return await guarded_on(slack, 'check_channel_access', channel_id=channel_id, snapshot_digest=snapshot_digest)

@server.tool(annotations=READ_ONLY)
async def slack_read_channel(channel_id: str, include_coverage: bool = False) -> dict:
    """Read one channel. A channel outside the allowlist fixed at launch is refused here."""
    if channel_id not in SLACK_CHANNELS:
        return {'ok':False,'code':'scope',
                'error':'That channel is not in the allowlist saved for this run.'}
    return await guarded_on(slack, 'read_channel' if include_coverage else 'messages', channel_id=channel_id)

if __name__ == '__main__':
    server.run(transport='stdio')
