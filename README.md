# Project Knowledge Assistant — Stage 1

Understand one GitHub project with a local assistant. Configure a repository and branch, scan a specific commit, ask a question in ordinary English, and inspect the code excerpts behind the answer.

**Stage 1 is implemented.** It uses a Python web app, an actual read-only MCP server, SQLite word search and your local Ollama model. The backend chooses what to read; the small model does not choose tools. Project overviews, Jira and Slack remain planned in [docs/ROADMAP.md](docs/ROADMAP.md).

Start with [START_HERE_WINDOWS.md](START_HERE_WINDOWS.md). All commands assume Windows PowerShell in this project's folder. Your Python 3.10.9 meets the declared requirements; no Python upgrade is required by this project. Runtime checks here used Linux/Python 3.12, and Windows/Python 3.10 dependency resolution was checked separately. See [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

## What the first version does

- Explicitly selects one repository and branch. It resolves the branch to a commit before collecting files.
- Reads supported source files and documentation without cloning, importing, installing or executing the project's code.
- Uses Python syntax boundaries for Python chunks; uses headings and simple declaration boundaries for other text. Oversized sections are split with accurate line ranges.
- Searches words, filenames and split code symbols. A small synonym dictionary helps ordinary questions such as “How does login work?” find authentication code. This is lexical retrieval, not semantic search.
- Sends up to five relevant excerpts to `qwen3:1.7b`, using local Ollama's structured-output API, non-streaming responses and thinking disabled.
- Shows source paths, line ranges, commit links, scan times in IST, elapsed answer time and manual feedback. Source sufficiency is recorded separately from answer quality.
- Rejects unknown citation IDs and preserves retrieved excerpts if Ollama fails. Valid IDs do not prove the model's statements are correct.
- Replaces the index atomically after a completed collection. Deleted files do not survive a refresh. A failed, interrupted or cancelled scan disables answers until another usable scan.
- Verifies GitHub read access and the branch head for every question. If the head changed, it disables old excerpts and requires a refresh. It does not answer offline from an unverified cache.

## Quick start with examples

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pka --demo
```

Open <http://127.0.0.1:8000>, click **Start / refresh scan**, and ask **How does login work?** The example mode uses built-in data and a deterministic explanation of the demonstration. It deliberately does not pretend to test a real account or Ollama. Its separate database is `data/demo.sqlite3`.

## Connect your actual repository

Follow [START_HERE_WINDOWS.md](START_HERE_WINDOWS.md) for token permissions and Ollama checks. Then run:

```powershell
.\.venv\Scripts\python.exe -m pka
```

Save the repository and the branch in the browser. Paste the address straight from your browser, such as `https://github.com/acme/shop`, or type `owner/repository`; a `/tree/...` or `/blob/...` tail, a trailing `.git`, a `?tab=` query and the `git@github.com:` form are all accepted and reduced to `owner/repository` before anything is fetched. Only github.com addresses are read; any other host is refused. Click **Start / refresh scan**, inspect coverage, then ask a question. Public repositories can be read without a token, but the unauthenticated allowance is only 60 requests per hour for your whole IP address and the scan spends one request per readable file. Any repository with more than about 55 readable files therefore needs a token, and waiting for the reset will not help because the next attempt hits the same ceiling. A token raises the allowance to 5000 per hour. Before reading any file the scan compares the files it needs against the allowance left and stops with those two numbers if the allowance cannot cover the run, rather than spending it on an index that would be discarded. Private repositories require a fine-grained token restricted to the selected repository with **Contents: Read-only** and the metadata access GitHub supplies. Do not grant write permissions.

## Limits and current scope

| Limit | Default |
|---|---:|
| Files successfully read per scan | 500 |
| Bytes per file | 256 KiB |
| Total source text per scan | 5 MiB |
| Tree entries considered | 20,000 |
| Non-recursive tree requests during fallback | 200 |
| Excerpt size | 1,800 characters / 60 lines |
| Answer context | Up to 5 excerpts / 7,200 source-text characters |
| Ollama context setting | 8,192 tokens |
| Ollama output budget | 900 tokens |
| Answer request timeout | 180 seconds |
| Concurrent scan or answer | 1 |

Limits live in `pka/config.py`. Supported extensions and exclusions are explicit in `pka/connectors/github.py`. Stage 1 supports GitHub.com; GitHub Enterprise hosts are not implemented. Only files in the selected branch snapshot are collected: no issues, PRs, commit history, Git LFS objects or submodule contents.

Each project records which platforms it uses. Ticking a platform records that fact and shows what connecting it would need; it never grants access on its own. Access requires a credential you place in your own `.env` file and a scope you name yourself: one repository, one Jira project, a listed set of Slack channels. Each platform's panel has a box for every credential it needs. What you type is written to your own local `.env` file, which `.gitignore` excludes, and applied to the running process so the next scan uses it without a restart. Values are never shown again, never written to a log and never sent to the model; the interface is told only whether a credential is set. Only names a platform declares can be written, so a form post cannot set `PATH` or `PYTHONPATH`, and a value containing a line break is refused because it could smuggle in a second setting. A platform that supports it can be connected by pressing a button instead of pasting a token. You paste the client id and secret once, press Connect, approve the reading permissions on the platform's own page, and the token is exchanged and stored for you. The permissions the link asks for are fixed in the registry, so the browser cannot widen them, and a single use random state created here and checked on return is what proves the redirect belongs to a connect you started. Platforms are defined in `pka/connectors/registry.py`, so adding one is an entry in that list plus a connector module beside it, and it then appears in the interface, the API and the setup guidance without any of them being edited. A **complete** scan means all discovered, supported, policy-allowed files within scope were processed. It never means every file in the project was examined. Unsupported files and deliberately excluded paths remain listed as skipped. Size/encoding omissions, unreadable supported files or a truncated tree produce a **partial** scan with warnings. A tree limit means some files cannot even be enumerated; the interface says so. A partial snapshot can answer only from its available excerpts.

Potential secret filenames, dependency folders, build artefacts, lock files, symlinks and unsupported formats are excluded. Dependency folders such as `.venv`, `node_modules` and `vendor` are discarded before the entry cap is applied and the crawler does not descend into them, so a repository that commits its virtual environment still has its own source read. The count of files dropped this way is reported in the scan log. This filename policy is not a secret scanner: credentials embedded inside an otherwise normal source file can still enter the local index. Review what you select and keep credentials out of project files.

Refresh is manual. Short transient failures get bounded retries; longer rate-limit waits are reported so you can retry later. Interrupted scans restart from the beginning. There is no scheduled sync or incremental backfill yet.

## How it works

The browser calls the FastAPI backend. For each read, the backend launches the fixed local MCP server through standard input/output. Every platform's scope is fixed at that launch: the repository and branch, the one Jira project, and the list of Slack channels. A tool argument naming anything outside that scope is refused by the server, and credentials are handed to it at launch so no token is held in the request path. The server's GitHub connector resolves the commit, lists the manifest in pages and reads allowed blobs; its Jira and Slack connectors list what an account can see and read only what was pinned. The backend stores bounded chunks in SQLite FTS5. For each question, it verifies access, retrieves excerpts and asks Ollama for a cited explanation. It stores feedback locally.

| File | Responsibility |
|---|---|
| `pka/web.py` | Local browser API, input validation, same-origin boundary |
| `pka/service.py` | Scan lifecycle, access checks, retrieval-to-answer workflow |
| `pka/mcp_client.py` | Actual SDK client and fixed tool allowlist |
| `pka/mcp_server.py` | Ten read-only MCP tools across GitHub, Jira and Slack; scope fixed at launch |
| `pka/connectors/github.py` | GET-only GitHub calls, limits, retries and source restrictions |
| `pka/connectors/base.py` | Interface for later connectors and safe errors |
| `pka/connectors/jira.py`, `slack.py` | GET-only Jira and Slack reads, reached only through the MCP server |
| `pka/index.py` | Chunking, SQLite snapshots, search and feedback |
| `pka/static/` | Plain HTML, CSS and JavaScript interface |
| `tests/test_core.py` | Fixture-based and protocol tests |
| `scripts/smoke_demo.py` | Full local HTTP/MCP example-mode check |

## Local data and permissions

The app binds only to `127.0.0.1`. Keep it on your own machine; do not expose it through a tunnel or shared server. This is a single-user prototype without user accounts. Before multi-user use, implement authentication, per-user platform credentials, permission-filtered retrieval and answer generation, revocation checks and isolation tests. Localhost and a shared index are not sufficient for multiple users.

One continuous debug log is written to `data/logs/pka.log`, covering startup, repository saves, every GitHub request with its status and remaining allowance, scan starts and endings, retrieval for each question including which excerpts were chosen, and every model call with its timing. It rolls at 5 MB and keeps five previous files. `PKA_LOG_LEVEL` changes the level. It never records the token, source excerpt text or answer text, and it withholds question text unless `PKA_LOG_QUESTIONS=1` is set, recording only the length and word count. Alongside it, every scan writes a plain-text report to `data/logs/scan-<id>-<status>-<time>.log` listing the counts, the reason totals and every candidate file with its state. The twenty most recent are kept. Set `PKA_LOG_DIR` to put them elsewhere. The report holds paths, states and counts only, never source text, tokens or your questions. The application writes its own settings, scan metadata, excerpts, answers and feedback under `data/`. It never writes to GitHub. The `.env` file and local database are unencrypted files protected by your operating-system account. Never commit them or share them with the project ZIP. Changing the selection clears previous indexed content and answers. Rescanning clears old answer feedback as well, preventing old source excerpts from being retained as answer history. This is logical removal from application results, not forensic erasure of disk backups.

Only a fixed Python MCP module is launched. Downloaded project code is never executed. Source text goes into a labelled data section in the prompt. The model has no tools, secrets or unrestricted network actions. Prompt instructions reduce injection risk but do not make model explanations infallible. Output is displayed as text, not HTML.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\smoke_demo.py
.\.venv\Scripts\python.exe -m pka.doctor
```

The first two checks need no account or model. `pka.doctor` checks the actual local Ollama service and your configured repository without printing tokens or file contents. The test record and remaining verification are in [docs/STATUS.md](docs/STATUS.md).
