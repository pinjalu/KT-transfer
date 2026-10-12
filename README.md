# Project Knowledge Assistant — Stage 1

Understand one GitHub project with a local assistant. Configure a repository and branch, scan a specific commit, ask a question in ordinary English, and inspect the code excerpts behind the answer.

**Stage 1 is implemented.** It uses a Python web app, an actual read-only MCP server, SQLite word search and your local Ollama model. The backend chooses what to read; the small model does not choose tools. Project overviews, Jira and Slack remain planned in [docs/ROADMAP.md](docs/ROADMAP.md).

Start with [START_HERE_WINDOWS.md](START_HERE_WINDOWS.md). All commands assume Windows PowerShell in this project's folder. Your Python 3.10.9 meets the declared requirements; no Python upgrade is required by this project. Runtime checks here used Linux/Python 3.12, and Windows/Python 3.10 dependency resolution was checked separately. See [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

## What the first version does

- Explicitly selects one repository and branch. It resolves the branch to a commit before collecting files.
- Reads supported source files and documentation without cloning, importing, installing or executing the project's code.
- Uses Python syntax boundaries for Python chunks; uses headings and simple declaration boundaries for other text. Oversized sections are split with accurate line ranges.
- Searches words, filenames and split code symbols. A small synonym dictionary and the project's own vocabulary help ordinary questions such as “How does login work?” find authentication code. Word matching is the default and the only thing enabled out of the box. Meaning-based retrieval is available beside it and off unless `PKA_EMBED_MODEL` names a local embedding model.
- Sends up to five relevant excerpts to `qwen3:1.7b`, using local Ollama's structured-output API, non-streaming responses and thinking disabled.
- Shows source paths, line ranges, commit links, scan times in IST, elapsed answer time and manual feedback. Source sufficiency is recorded separately from answer quality.
- Rejects unknown citation IDs and preserves retrieved excerpts if Ollama fails. Valid IDs do not prove the model's statements are correct.
- Replaces the index atomically after a completed collection. Deleted files do not survive a refresh. A failed, interrupted or cancelled scan disables answers until another usable scan.
- Verifies GitHub read access and the branch head for every question. If the head changed, it disables old excerpts and requires a refresh. It does not answer offline from an unverified cache.

## The project overview and the questions page

The overview opens as a walkthrough, one step at a time, in the order a developer handing the
project over would actually use. What it is, then a picture of how it is laid out, then what
uses what, then get it running, then follow one request through from arriving to being
answered, then where information is kept, then how it is checked, and finally the files to read
and the order to read them in. Each step opens with the sentence a colleague would say out
loud, carries its own diagram and facts, and keeps its prose to the first few points with the
rest one click away. Nine paragraphs at once is how the overview used to read, and nobody read
it. You can jump to any step from the numbered rail, and the whole thing is still available on
one page behind **Show everything on one page**, which is the better view for searching it.

A step that this particular project cannot fill is dropped rather than shown empty, so a
project with no internal imports gets no "what uses what" step. The steps that do apply are
settled before the first explanation is written, so step five is step five from the first
second of a build and nothing is renumbered under you while you read. A step still waiting for
its prose has a dashed number in the rail and says so when you open it; its diagram and its
facts are already final, because those are finished before any explanation starts.

Two counts appear while a build runs and they count different things. The badge on the card
counts the written explanations, so it reads "Writing 4/8". The walkthrough rail counts steps.
They are not the same number and are not meant to match.

### The diagrams

Three, all derived from the scanned files by `pka/diagram.py`, none written by a model.

**The project as a stack** puts every file that was read into one of five layers: what a
person or a browser touches, where a request arrives, where the work happens, where
information is kept, and settings and checks. A file is placed by its path and its contents,
so the file declaring the routes lands in the request layer and the file creating a table
lands in the data layer.

**What uses what** is boxes and arrows. An arrow exists because one file contains an import
statement naming another, and the line number of that import travels with the arrow. Files
nothing imports sit on the left, so following the arrows rightwards goes deeper into the
project. An import of something outside the project is a dependency, not an arrow, and appears
in the version list instead. Two files that import each other get a dashed arrow looping
underneath, because there is no order in which one of them comes first, and that is worth
knowing. Too many files to draw one by one and the boxes become folders, with each arrow
carrying the number of imports crossing between them.

**One request, start to finish** is a worked example: a client, the file that receives the
request, the addresses declared in it, the modules it imports and the table one of them
creates. Only steps that can be proved are drawn. Which address ends up touching which table
is deliberately left out, because no line in the files states it.

A diagram with nothing behind it is not drawn, and every box that stands for a real file opens
that file at the scanned commit.

### One card per important file

Beside the import graph, a card for each file the rest of the project leans on, in the shape a
new developer asks about it: what it is for, what it answers or declares, who uses it and what
it uses. Who uses what comes from the import lines with their line numbers, so it is exact,
and a wrong answer there would send somebody editing the wrong file. The one-line description
is whatever the file says about itself in its docstring, its leading comment or its first
heading; a file that says nothing is left blank rather than given an invented purpose.

### Outside services, and what it cannot tell you

Services the project reaches for are listed with what they are for and the line that reaches
them, taken from the dependency that pulls them in or the import that uses them, so the entry
is never just "Stripe is integrated". Build, container and pipeline files are listed too, as
files: a pipeline definition is not a pipeline run, and the wording says so.

The last step names what a new developer will want that this scan has no way of answering:
pull requests, commit history, pipeline runs, running deployments, logs and monitoring, the
live database, and how an outside service behaves in practice. Each says why, and the group
carries what was checked for this scan.
[docs/KT_REQUIREMENTS.md](docs/KT_REQUIREMENTS.md) maps the full handover standard against
what is built, section by section.

### Sentences that are not about this project

A statement naming nothing real from this project, the kind that would be equally true of any
other codebase, is marked in the interface. The names come from the scan itself: the paths of
the excerpts and every dependency, route, table and setting already found. This is checked
rather than only asked for in the prompt, because asking a small model politely does not
work.

### Who it is explaining to

Three modes across the top, because the same evidence is wanted at three depths. **New here**
keeps to plain words, pictures and the facts, and hides the citations and the excerpts.
**Developer** adds the excerpts, the citations, the import lines and the full dependency list.
**Architect** drops the prose and shows the shape: layers, what uses what, outside services,
storage and settings.

### What is read versus what is explained

Underneath the walkthrough the content has two halves, labelled separately, because they are
worth different amounts of trust.

The first half is read straight out of the scanned files by `pka/facts.py`: what was read and
in what languages, the documentation the project ships, every declared dependency with its
version, the commands the project defines for itself, every web address it answers on, the
tables and data shapes it keeps, and the settings it reads from the environment. No model
touches any of it, and every single entry links to the file and the line it came from at the
scanned commit. A pattern that finds nothing reports nothing, so an absent group means the
project genuinely has none of that rather than that the overview gave up.

The second half is prose, one section per topic, written by the local model from retrieved
excerpts. There are eight topics, nine when Slack or Jira content has been read in, and each
one is retrieved and explained on its own so a weak section stays weak. Each topic retrieves
from several phrasings at once and the rankings are merged, because one word search for "how
it is set up" finds the readme and misses the start-up script.

What the model returns is checked before it is shown. A statement that restates an earlier one
is dropped. A statement citing every excerpt at once, which a small model does constantly, is
narrowed to the excerpts whose text actually carries its wording. And every statement is
measured against the excerpt it cites: one whose content cannot be found there is marked
**check this** and the reader is pointed at the excerpt. That mark is a prompt to look, not a
verdict that the sentence is wrong.

Citations work the same way in the overview and in the answers. `[S1]` opens the excerpt that
was sent to the model, and the arrow beside it opens that file at those exact lines on GitHub.
Slack blocks link to the message permalink and Jira blocks to the issue. The suggested reading
order links each file too.

Sections are saved as they finish, so the first steps are readable while the rest are still
being written, and the diagrams and the facts are complete before any prose is written at all.
On a processor the whole overview takes several minutes.

Answers also show what the search did with your words: which ones it used, which it read as a
word the project actually uses, and which appear nowhere in the scanned files. A thin answer
is usually the third case, and knowing that is the difference between rewording the question
and concluding the project does not cover it.

## Quick start with examples

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pka --demo
```

### The new interface

The ten-screen interface described in [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) is a React
application under `frontend/`. It is built once and then served by the same Python process, so
running the application still needs nothing but Python and Ollama. Node is needed only to build
it, and only when the interface itself changes.

```powershell
cd frontend
npm install
npm run build
```

That writes `pka/static/ui/`. With it present, `/` serves the new interface; without it, `/`
serves the original single-page interface unchanged, which is also always reachable at `/legacy`.

To work on the interface, run `npm run dev` beside `python -m pka` and open
<http://localhost:5173>. The dev server proxies `/api` to the Python process and rewrites the
`Origin` header, because the application refuses a request whose origin is not its own. Nothing
in `pka/web.py` is relaxed to make that work.

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
| Excerpts retrieved per overview topic | Up to 5, merged from 2 to 4 separate searches |
| Overview topics | 8, or 9 once Slack or Jira content has been read |
| Walkthrough steps | Up to 9, each dropped when this project cannot fill it |
| Boxes per diagram column | 7, then the remainder is counted in one box |
| Files drawn individually before folders replace them | 26 |
| Ollama context setting | 8,192 tokens |
| Ollama output budget | 1,200 tokens |
| Answer request timeout | 180 seconds |
| Concurrent scan or answer | 1 |

Limits live in `pka/config.py`. Supported extensions and exclusions are explicit in `pka/connectors/github.py`.

Retrieval is word matching by default. Naming an embedding model in `PKA_EMBED_MODEL` adds
meaning-based retrieval beside it: the snapshot is turned into vectors after a scan, a question
is turned into a vector when it is asked, and the nearest excerpts join the word matches in the
same merge rather than replacing them, so asking for a function by name or for a ticket key
still works by exact match. It is off unless you name a model, and if the model is missing or
Ollama is down the scan and the answer carry on exactly as they did without it. This has been
checked against a stub embedder and the failure paths, not against a live embedding model; see
[docs/STATUS.md](docs/STATUS.md). Stage 1 supports GitHub.com; GitHub Enterprise hosts are not implemented. Only files in the selected branch snapshot are collected: no issues, PRs, commit history, Git LFS objects or submodule contents.

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
| `pka/index.py` | Chunking, SQLite snapshots, merged word and meaning search, feedback |
| `pka/facts.py` | Dependencies, routes, settings and tables read out of the files, with line links |
| `pka/diagram.py` | The stack, the import graph and the request journey, derived from the files |
| `pka/roles.py` | What each important file is for, who uses it and what it uses |
| `pka/overview.py` | Overview topics, the checks on model prose, the derived reading order |
| `pka/embed.py` | Optional local embedding calls, off by default, fails quietly |
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
