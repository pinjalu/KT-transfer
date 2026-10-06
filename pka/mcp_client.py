from contextlib import asynccontextmanager
from datetime import timedelta
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pka.config import ROOT
from pka.connectors.base import SourceError

TOOL_NAMES = {'github_check_access','github_begin_snapshot','github_list_files','github_read_file'}

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

@asynccontextmanager
async def connect(settings: dict, demo: bool = False):
    # Only explicit app/connector environment is added to the SDK's minimal environment.
    env = {'PKA_REPO':settings['repo'],'PKA_BRANCH':settings['branch'],
           'PKA_DEMO':'1' if demo else '0','GITHUB_TOKEN':'' if demo else os.getenv('GITHUB_TOKEN',''),
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
