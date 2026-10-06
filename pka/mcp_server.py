"""The only MCP server process; its selected scope is fixed at launch."""
import logging
import os
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pka.connectors.base import SourceError
from pka.connectors.github import GitHubSource
from pka.connectors.fixture import FixtureSource

logging.disable(logging.CRITICAL)
server = FastMCP('Project Knowledge — read only', log_level='CRITICAL')
source = FixtureSource() if os.getenv('PKA_DEMO') == '1' else GitHubSource(
    os.environ['PKA_REPO'], os.environ['PKA_BRANCH'], os.getenv('GITHUB_TOKEN',''))
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)

async def guarded(method, **kwargs):
    try:
        return {'ok':True,'data':await method(**kwargs)}
    except SourceError as exc:
        return {'ok':False,'code':exc.code,'error':str(exc)}
    except Exception:
        return {'ok':False,'code':'connector','error':'Connector failed. No upstream response or credentials were logged.'}

@server.tool(annotations=READ_ONLY)
async def github_check_access(commit: str = '') -> dict:
    """Check access and branch head for the one explicitly selected repository."""
    return await guarded(source.check_access, commit=commit)

@server.tool(annotations=READ_ONLY)
async def github_begin_snapshot() -> dict:
    """Resolve the selected branch to one commit and enumerate its files."""
    return await guarded(source.begin_snapshot)

@server.tool(annotations=READ_ONLY)
async def github_list_files(cursor: int = 0) -> dict:
    """Read one manifest page, restricted to the current snapshot."""
    return await guarded(source.list_files, cursor=cursor)

@server.tool(annotations=READ_ONLY)
async def github_read_file(path: str) -> dict:
    """Read one allowed file from the resolved commit; never execute it."""
    return await guarded(source.read_file, path=path)

if __name__ == '__main__':
    server.run(transport='stdio')
