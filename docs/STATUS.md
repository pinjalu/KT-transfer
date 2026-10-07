# Implementation and verification record

Delivery: Stage 2 local prototype. Recorded on 6 October 2026 (IST).

## Stage 1 live acceptance, 6 October 2026

Run on the target machine: Windows 11, Python 3.10.9, Intel i5, 16 GB RAM, Ollama with qwen3:1.7b.

| Check | Outcome |
|---|---|
| Real repository scanned at a pinned commit | 99 files read, 2 skipped, 0 failed, status complete |
| Real fine-grained token, Contents read-only | GitHub read access confirmed by pka.doctor |
| Real Ollama answer with inspectable sources | Answered in 62 seconds, citations resolved to supplied excerpts |
| Unauthenticated rate ceiling | Reproduced at 60 requests per hour; preflight now reports it before spending the allowance |
| Repository that commits its virtual environment | Reproduced; dependency directories are now discarded before the entry cap |

Three defects were found and fixed during acceptance. A repository that commits a dependency
directory indexed nothing at all, because the tree was truncated at the entry cap before the
exclusion rules ran. The unauthenticated rate ceiling was spent on a scan that could never
finish. The repository field rejected a pasted address. A continuous debug log at
data/logs/pka.log was added because none of these left any trace on disk.

## Implemented

GitHub.com connector with explicit repository/branch scope; real MCP stdio server and client; immutable commit snapshots; file policy and size limits; manifest cursor pages and Git tree fallback; source-aware chunking; SQLite FTS5 retrieval with word expansion; Ollama structured answers; exact source links; browser configuration, scan progress, cancellation, sources and manual feedback; freshness/access checks; sanitised errors; interrupted-scan recovery; isolated example mode; PowerShell setup and troubleshooting.

Stage 2 project overview: five topics, each retrieved and explained separately so a weak
section cannot borrow confidence from a strong one, each carrying its own excerpts and its own
statement of what is missing. A topic with no matching evidence is recorded as having none
rather than dropped. A suggested reading order is derived from the indexed file paths and
labelled as derived, not model-written. The overview is cached against the commit, survives a
refresh that lands on the same commit, and is cleared when the repository changes.

Slack reading with a user token: the channels an account can see are listed, the ones chosen
are saved as an allowlist, and only those are read. Messages are stored beside the code in the
same index, so one question can be answered from both. Each block cites a Slack permalink
rather than a code line. Reading again replaces what was read before, so a deleted message or a
channel dropped from the list cannot linger in answers. Only three Slack methods are ever
called, all reads, against a fixed host.

Not implemented for Slack: resolving user ids to names, which needs the users:read permission
this deliberately does not request; incremental reading since a timestamp; and the Slack bot
token mode, which remains a placeholder. Jira reading: the projects an account can see are listed, one project is chosen, and its
issues are read with summary, type, status, priority, assignee, labels, description and
comments. Atlassian rich text is flattened to plain lines. Each issue cites its own browse
link. Reading again replaces what was read before, and leaves the code and Slack content
alone. Only three Jira endpoints are ever called, all reads, and the site address is checked
so it cannot be aimed at a private network address.

Not verified against a live Jira: the credentials supplied during development were rejected by
Atlassian with AUTHENTICATED_FAILED, so every Jira check here is against mocked responses. No
fixture result should be read as evidence that a real Jira site behaves the same way. The Slack
bot token mode remains a placeholder. Multiple-user accounts, automatic scheduled sync and semantic embeddings are not
implemented.

## Executed checks

| Check | Outcome | What it establishes |
|---|---|---|
| pytest suite | 142 passed | Behaviour against local fixtures and HTTP mocks, including actual MCP subprocess calls |
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

- Organisation approval and actual token expiry. A real personal token was used, but neither an
  organisation-approved token nor an expired one was tested.
- Measured semantic answer accuracy. Real answers were produced and read, but no labelled
  accuracy measurement was carried out.
- Graphical browser rendering and click verification. Browser installation in this environment
  failed because the download was not a valid archive. The real HTTP flow and JavaScript syntax
  were checked instead, and the user exercised the interface manually.
- Jira and Slack connectors. Stages 3 and 4 are unstarted; no credentials exist for either.

The first three entries of the previous record, covering a real repository scan, a real
Ollama response and Windows/Python 3.10 runtime execution, were completed on 6 October 2026
and moved into the acceptance table above.

No simulated check is represented as a live-account or model-accuracy test. Valid source identifiers establish that citations refer to supplied excerpts; they do not establish that the model interpreted them correctly. Prompt-injection tests verify prompt separation and absence of tools, not immunity of the model to malicious text.

## Before expanding to Stage 3

Stage 3 needs a Jira site, a project key and an API token with read scopes, none of which
exist yet. Until they do, the Jira adapter can only be written against fixtures, and no
fixture result should be read as evidence that a real Jira project behaves the same way.

Before starting it, exercise the Stage 2 overview on a repository other than the one used
here, confirm that a topic with no evidence still reports itself as empty, and check that the
documented setup steps it collects are presented as documentation rather than executed.
