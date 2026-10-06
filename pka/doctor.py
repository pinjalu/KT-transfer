"""Print connection checks without printing credentials, source data or HTTP bodies."""
import asyncio
import os
import sqlite3
import sys
import httpx
from pka.config import data_dir
from pka.connectors.base import SourceError
from pka.index import Index
from pka.mcp_client import connect

async def main():
    print('Python:',sys.version.split()[0])
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE VIRTUAL TABLE fts_check USING fts5(text)')
    print('SQLite FTS5: available')
    model=os.getenv('OLLAMA_MODEL','qwen3:1.7b')
    try:
        async with httpx.AsyncClient(timeout=10,trust_env=False) as client:
            r=await client.get('http://127.0.0.1:11434/api/tags')
            r.raise_for_status()
            names=[m.get('name') for m in r.json().get('models',[])]
        print('Ollama model:',model,'— installed' if model in names else '— not found; run ollama pull '+model)
    except (httpx.HTTPError,ValueError):
        print('Ollama: unavailable. Start the Ollama desktop application or run ollama serve.')
    cfg=Index(data_dir()/'index.sqlite3').settings()
    print('GitHub token:', 'configured' if os.getenv('GITHUB_TOKEN') else 'not configured (public repositories only)')
    if not cfg:
        print('GitHub: save a repository and branch in the browser first.')
        return
    try:
        async with connect(cfg) as source:
            status=await source.check_access()
        print('GitHub read access: OK; branch commit:',status['head'])
    except SourceError as exc:
        print('GitHub:',str(exc))

if __name__=='__main__':asyncio.run(main())
