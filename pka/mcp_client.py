from contextlib import asynccontextmanager
from datetime import timedelta
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pka.config import ROOT
from pka.connectors.base import SourceError

TOOL_NAMES = {'github_check_access','github_begin_snapshot','github_list_files','github_read_file',
              'jira_check_access','jira_list_projects','jira_begin_read','jira_list_issues',
              'slack_list_channels','slack_read_channel'}

def source_error_in(exc):
    """Support AnyIO exception groups on both Python 3.10 and newer runtimes."""
    if isinstance(exc, SourceError):
        return exc
    for child in getattr(exc, 'exceptions', ()):
        found = source_error_in(child)
        if found:
            return found
    return None

class ConnectorClient:
    def __init__(self, session):
        self.session = session
    async def call(self, tool: str, **kwargs):
        if tool not in TOOL_NAMES:
            raise SourceError('scope', 'Tool is not on the read-only allowlist.')
        result = await self.session.call_tool(tool, kwargs)
        if result.isError:
            raise SourceError('mcp', 'MCP tool failed.')
        data = result.structuredContent
        if data is None:
            data = json.loads(next(c.text for c in result.content if c.type == 'text'))
        if not data.get('ok'):
            raise SourceError(data.get('code','mcp'),data.get('error','Connector failed.'))
        return data['data']
    async def check_access(self, commit=''):
        return await self.call('github_check_access', commit=commit)
    async def begin_snapshot(self):
        return await self.call('github_begin_snapshot')
    async def list_files(self, cursor=0):
        return await self.call('github_list_files', cursor=cursor)
    async def read_file(self, path):
        return await self.call('github_read_file', path=path)
    async def jira_check_access(self):
        return await self.call('jira_check_access')
    async def jira_projects(self):
        return await self.call('jira_list_projects')
    async def jira_begin_read(self):
        return await self.call('jira_begin_read')
    async def jira_issues(self, cursor=0):
        return await self.call('jira_list_issues', cursor=cursor)
    async def slack_channels(self):
        return await self.call('slack_list_channels')
    async def slack_messages(self, channel_id):
        return await self.call('slack_read_channel', channel_id=channel_id)

@asynccontextmanager
async def connect(settings: dict, demo: bool = False):
    # Every platform's scope is pinned here, at launch, the same way the repository is. The
    # server refuses anything outside it, so a tool argument cannot widen what is readable.
    project = '' if demo else str((settings.get('jira') or {}).get('project') or '')
    channels = '' if demo else ','.join(
        str(c.get('id','')) for c in ((settings.get('slack') or {}).get('channels') or []))
    # Only explicit app/connector environment is added to the SDK's minimal environment.
    # Credentials are handed to the child process and stay there; the request path never
    # touches a token again.
    env = {'PKA_REPO':settings['repo'],'PKA_BRANCH':settings['branch'],
           'PKA_DEMO':'1' if demo else '0','GITHUB_TOKEN':'' if demo else os.getenv('GITHUB_TOKEN',''),
           'PKA_JIRA_PROJECT':project,'PKA_SLACK_CHANNELS':channels,
           'JIRA_SITE':'' if demo else os.getenv('JIRA_SITE',''),
           'JIRA_EMAIL':'' if demo else os.getenv('JIRA_EMAIL',''),
           'JIRA_API_TOKEN':'' if demo else os.getenv('JIRA_API_TOKEN',''),
           'SLACK_USER_TOKEN':'' if demo else os.getenv('SLACK_USER_TOKEN',''),
           'PYTHONPATH':str(ROOT),'PYTHONIOENCODING':'utf-8'}
    if 'SYSTEMROOT' in os.environ:
        env['SYSTEMROOT'] = os.environ['SYSTEMROOT']
    params = StdioServerParameters(command=sys.executable,args=['-m','pka.mcp_server'],env=env,cwd=str(ROOT))
    try:
        with open(os.devnull, 'w') as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=180)) as session:
                    await session.initialize()
                    actual = {t.name for t in (await session.list_tools()).tools}
                    if actual != TOOL_NAMES:
                        raise SourceError('scope','Unexpected MCP tool set; connection refused.')
                    yield ConnectorClient(session)
    except Exception as exc:
        safe = source_error_in(exc)
        if safe:
            raise safe from None
        raise SourceError('mcp','The local MCP connection failed or timed out. Restart the app and retry.') from None
