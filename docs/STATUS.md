# Implementation and verification record

Delivery: Stage 1 local prototype. Recorded on 5 October 2026 (IST).

## Implemented

GitHub.com connector with explicit repository/branch scope; real MCP stdio server and client; immutable commit snapshots; file policy and size limits; manifest cursor pages and Git tree fallback; source-aware chunking; SQLite FTS5 retrieval with word expansion; Ollama structured answers; exact source links; browser configuration, scan progress, cancellation, sources and manual feedback; freshness/access checks; sanitised errors; interrupted-scan recovery; isolated example mode; PowerShell setup and troubleshooting.

Jira and Slack modules are labelled disabled placeholders. No Jira or Slack tools are registered. No project-overview workflow, multiple-user accounts, automatic scheduled sync or semantic embeddings are implemented.

## Executed checks

| Check | Outcome | What it establishes |
|---|---|---|
| pytest suite | 38 passed | Behaviour against local fixtures and HTTP mocks, including actual MCP subprocess calls |
| Real HTTP example-mode smoke check | Passed | Start app, serve UI assets, scan via MCP, retrieve, produce a simulated answer and save separate feedback |
| Example smoke counts | 3 files read, 1 skipped, 3 retrieved sources | Expected fixture coverage; not a real project scan |
| Dependency installation and `pip check` | Passed on Linux / Python 3.12.14 | The installed test environment has no declared dependency conflicts |
| CPython 3.10 / Windows AMD64 binary-only pip resolution | Passed | Declared version and wheel compatibility; not Windows runtime execution |
| Python 3.10 syntax parsing | All 17 Python files passed | The source does not require Python 3.11+ syntax |
| JavaScript syntax check | Passed | Browser script parses under Node; not a graphical browser test |
| Official dependency/API documentation | Reviewed | Requirements and API choices are recorded in DEPENDENCIES.md |

The suite covers scope validation; excluded and unsafe paths; function boundaries and line preservation; ordinary-language retrieval; correct commit/line links; separate quality/source feedback and stale-feedback rejection; no-evidence answers; deleted-file replacement; partial and failed scans; restart recovery; access revocation and changed branch heads; cancellation; GET-only requests; manifest pagination; truncated-tree fallback; 401/403/404, long rate limits, redirects and transient retries; registered MCP read-only tools; MCP error preservation; bounded Ollama requests, untrusted context and unknown-citation rejection; local HTTP boundaries; and retaining sources when Ollama fails.

One dependency emitted a deprecation warning: Starlette's test client currently supports HTTPX but recommends its newer HTTPX2 transport. It did not fail a test. The application itself uses the pinned HTTPX client and MCP v1 SDK. Review dependency upgrades together rather than changing one pin blindly.

## Not executed here

- A scan against a real GitHub account/repository, including organisation approval and actual token expiry. No repository or credentials were supplied.
- A response from the user's real Ollama/qwen3:1.7b installation. No local Ollama service/model was provided in this runtime.
- Measured semantic answer accuracy or response times on the user's i5 / 16 GB Windows machine.
- Windows/Python 3.10 runtime execution.
- Graphical browser rendering and click verification. Browser installation in this environment failed because the download was not a valid archive. The real HTTP flow and JavaScript syntax were checked instead.

No simulated check is represented as a live-account or model-accuracy test. Valid source identifiers establish that citations refer to supplied excerpts; they do not establish that the model interpreted them correctly. Prompt-injection tests verify prompt separation and absence of tools, not immunity of the model to malicious text.

## Before expanding to Stage 2

Run START_HERE_WINDOWS.md using the chosen repository. Verify a scan, compare several real Ollama answers with the underlying code, test an unsupported question, and check refresh after a branch update. Review quality and source sufficiency separately. Keep the later implementation stages in ROADMAP.md until this live acceptance is complete.
