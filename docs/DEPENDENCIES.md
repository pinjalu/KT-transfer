# Dependency and API compatibility record

Checked against official package metadata and documentation on 5 October 2026. Python 3.10.9 meets the declared minimums below. The provided source uses Python 3.10 syntax. Actual runtime tests for this delivery used Linux/Python 3.12.14; Windows 3.10 execution is a remaining local acceptance check.

| Package | Pin | Declared Python requirement | Official source |
|---|---|---|---|
| MCP Python SDK | 1.30.0 | >=3.10 | https://pypi.org/project/mcp/1.30.0/ |
| FastAPI | 0.142.2 | >=3.10 | https://pypi.org/project/fastapi/0.142.2/ |
| Uvicorn | 0.34.3 | >=3.9 | https://pypi.org/project/uvicorn/0.34.3/ |
| HTTPX | 0.28.1 | >=3.8 | https://pypi.org/project/httpx/0.28.1/ |
| python-dotenv | 1.2.1 | >=3.9 | https://pypi.org/project/python-dotenv/1.2.1/ |
| Pydantic | 2.13.5 | >=3.9 | https://pypi.org/project/pydantic/2.13.5/ |
| pytest, development only | 8.4.2 | >=3.9 | https://pypi.org/project/pytest/8.4.2/ |

MCP 1.30 is pinned intentionally to the supported v1 maintenance API used here (`FastMCP`, `ClientSession`, `stdio_client`). MCP v2 has breaking API changes; upgrading the SDK alone is not safe. The official 1.30 documentation states that v1 continues to receive critical bug fixes and security patches: https://py.sdk.modelcontextprotocol.io/v1/ .

Direct dependencies are pinned. Transitive dependencies are selected by pip for the actual operating system and Python version. A pip binary-only resolution for CPython 3.10 / Windows AMD64 succeeded with the application and test requirements. This checks package metadata and wheel availability, not execution on Windows. Environment-marker-specific dependencies must still resolve on the actual Windows interpreter; `pip check` and the included tests are part of local setup.

SQLite comes with Python. The application requires the FTS5 extension; the included `pka.doctor` checks it. No separate database service or vector database is needed. SQLite FTS5 documentation: https://www.sqlite.org/fts5.html .

## GitHub API choices

Official Git Trees documentation: https://docs.github.com/en/rest/git/trees . Recursive trees can be truncated. The connector then walks non-recursive subtrees within explicit limits; it does not incorrectly treat a truncated tree as complete. Tree endpoints are not page-number APIs. The MCP manifest exposes local cursor pages of 200 files after enumeration.

Git blob documentation: https://docs.github.com/en/rest/git/blobs . Text is read through blob SHAs from the selected commit tree. Fine-grained tokens need repository Contents read permission. Redirects are not followed and token-bearing requests go only to the fixed GitHub API host.

Rate-limit guidance: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api . The connector handles Retry-After and rate-limit reset headers with short bounded waits, plus bounded transient retries. Longer waits are shown to the user for manual retry. Public unauthenticated scans are subject to much smaller quotas; full scans normally make roughly one request per file plus commit/tree requests.

Token setup: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens . Select one repository, Contents read-only, and the required metadata permission. Organisation policies may add an approval requirement.

## Ollama API choices

Chat endpoint: https://docs.ollama.com/api/chat . The app uses `POST /api/chat` with `stream: false`, `think: false`, a JSON schema in `format`, bounded generation options and your installed model name. Thinking control: https://docs.ollama.com/capabilities/thinking . Structured output: https://docs.ollama.com/capabilities/structured-outputs .

This delivery does not bundle Ollama or the model and did not execute the user's `qwen3:1.7b` installation. Current Ollama must support these documented fields. If an older installation rejects them, update Ollama and rerun the local checks. There is no cloud-model fallback.
