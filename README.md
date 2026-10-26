# Project Knowledge Assistant — local prototype

Understand a project with a local assistant. Connect a GitHub repository, add a local project folder, read relevant Jira issues and Slack messages, and inspect the excerpts behind each answer. The Connections dropdown opens one source's form at a time; all saved sources can be used together. See [local folder setup and limits](docs/LOCAL_REPOSITORIES.md).

The app reads one GitHub repository, one selected Jira project and selected Slack channels through a read-only MCP server. It provides project overviews, source-backed Ollama answers, selected Jira task explanations and related source links, Slack discussion summaries with evidence and status labels, derived architecture views, background jobs and import coverage. The backend chooses what to read; the model does not choose tools. Requirement implementation checks and other planned screens remain unfinished. See [Jira task explanations](docs/TASK_6_2.md), [related sources](docs/TASK_6_3.md), [Team decisions](docs/TASK_6_4.md), [baseline acceptance](docs/TASK_5_8.md) and [the roadmap](docs/ROADMAP.md).

Start with [START_HERE_WINDOWS.md](START_HERE_WINDOWS.md). Commands assume Windows PowerShell in this project's folder. Python 3.10 or newer is required. Current target-machine checks are recorded in [task 5.8](docs/TASK_5_8.md); older platform checks remain in [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

## What the first version does

- Protects the local workspace with one owner account, password sign-in and server-side sessions. See [account setup and session limits](docs/TASK_6_6.md).
- Selects one GitHub repository and branch, with an optional additional local folder. Local folders also work on their own. GitHub reads pin a commit; local reads pin a content snapshot that includes uncommitted files.
- Reads supported source files and documentation without cloning, importing, installing or executing the project's code.
- Uses Python syntax boundaries for Python chunks; uses headings and simple declaration boundaries for other text. Oversized sections are split with accurate line ranges.
- Searches words, filenames and split code symbols. A small synonym dictionary and the project's own vocabulary help ordinary questions such as “How does login work?” find authentication code. The example configuration also enables semantic retrieval with `nomic-embed-text`; install that model once, or clear `PKA_EMBED_MODEL` to use only word matching. Follow-ups can use four recent turns from the current project and source revision.
- Sends up to five relevant excerpts to `qwen3:1.7b`, using local Ollama's structured-output API, non-streaming responses and thinking disabled.
- Shows source paths, line ranges, commit links, scan times in IST, elapsed answer time and manual feedback. Source sufficiency is recorded separately from answer quality.
- Runs saved BSA regression questions from **Answer quality**, with exact-answer/source inspection and separate human correctness and evidence ratings. Automatic checks are not accuracy scores. See [answer evaluation](docs/TASK_5_2.md).
- Rejects unknown citation IDs and preserves retrieved excerpts if Ollama fails. Valid IDs do not prove the model's statements are correct.
- Replaces the index atomically after a completed collection. Deleted files do not survive a refresh. A failed, interrupted or cancelled scan disables answers until another usable scan.
- Reuses unchanged GitHub/local files and compatible repository embeddings on refresh. **Retry job** continues from saved file reads after interruption, with current access and hash checks. See [incremental and resumable imports](docs/TASK_7_2.md) for scope and limits.
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

For frontend development and tests, use Node 22 LTS (22.12 or newer) or Node 24 LTS.

```powershell
cd frontend
npm ci
npm test
npm run build
```

That writes `pka/static/ui/`. The included bundle provides login and account setup without a Node
installation. If it is missing, rebuild it before using the app. The original interface remains
available at `/legacy` after signing in.

To work on the interface, run `npm run dev` beside `python -m pka` and open
<http://localhost:5173>. The dev server proxies `/api` to the Python process and rewrites the
`Origin` header, because the application refuses a request whose origin is not its own. Nothing
in `pka/web.py` is relaxed to make that work.

Open <http://127.0.0.1:8000/connections>. On first use, copy the one-time code from the local
setup-code file named in the startup terminal and create an owner username and a 15–128-character
password. Then click **Refresh repository**, open **Ask assistant** and ask **How does login work?**
Example mode uses built-in data and a simulated explanation. Its account and database are separate
from live mode; it does not test a live source account or Ollama.

## Connect your actual repository

Follow [START_HERE_WINDOWS.md](START_HERE_WINDOWS.md) for token permissions and Ollama checks. Then run:

```powershell
.\.venv\Scripts\python.exe -m pka
```

Save the repository and the branch in the browser. Paste the address straight from your browser, such as `https://github.com/acme/shop`, or type `owner/repository`; a `/tree/...` or `/blob/...` tail, a trailing `.git`, a `?tab=` query and the `git@github.com:` form are all accepted and reduced to `owner/repository` before anything is fetched. Only github.com addresses are read; any other host is refused. Use **Save and read files** in Connections, or **Refresh repository** for the saved selection. Inspect coverage, then ask a question. Public repositories can be read without a token, but the unauthenticated allowance is only 60 requests per hour for your whole IP address and the scan spends one request per readable file. Any repository with more than about 55 readable files therefore needs a token, and waiting for the reset will not help because the next attempt hits the same ceiling. A token raises the allowance to 5000 per hour. Before reading any file the scan compares the files it needs against the allowance left and stops with those two numbers if the allowance cannot cover the run, rather than spending it on an index that would be discarded. Private repositories require a fine-grained token restricted to the selected repository with **Contents: Read-only** and the metadata access GitHub supplies. Do not grant write permissions.

## Limits and current scope

The username in the top bar opens **Account**, with password change and **Sign out all sessions**.
**Sign out** ends the current session. Sessions expire after 30 minutes without interaction or
8 hours after login; automatic polling does not extend them. Existing background jobs continue,
but their results require sign-in. Recover a forgotten password locally with
`python -m pka --reset-password` (add `--demo` for example mode), using the hidden terminal prompts.
For Slack browser approval, sign in on `http://localhost:8000` before connecting; Slack's callback
uses localhost and must return to the session that started it.

| Limit | Default |
|---|---:|
| Files successfully read per scan | 500 |
| Bytes per file | 256 KiB |
| Total source text per scan | 5 MiB |
| Tree entries considered | 20,000 |
| Non-recursive tree requests during fallback | 200 |
| Excerpt size | 1,800 characters / 60 lines |
| Answer context | Facts: 5 excerpts / 7,200 characters; explanations: 8 / 14,000 |
| Excerpts retrieved per overview topic | Up to 5, merged from 2 to 4 separate searches |
| Overview topics | 8, or 9 once Slack or Jira content has been read |
| Walkthrough steps | Up to 9, each dropped when this project cannot fill it |
| Boxes per diagram column | 7, then the remainder is counted in one box |
| Files drawn individually before folders replace them | 26 |
| Ollama context setting | 8,192 tokens; 16,384 for explanations or conversation context |
| Ollama output budget | Facts: 1,200 tokens; explanations: 2,000 |
| Answer request timeout | 180 seconds |
| Concurrent scan or answer | 1 |

Limits live in `pka/config.py`. Supported extensions and exclusions are explicit in `pka/connectors/github.py`.

Naming an embedding model in `PKA_EMBED_MODEL` adds
meaning-based retrieval beside it: the snapshot is turned into vectors after a scan, a question
is turned into a vector when it is asked, and the nearest excerpts join the word matches in the
same merge rather than replacing them, so asking for a function by name or for a ticket key
still works by exact match. It is off unless you name a model, and if the model is missing or
Ollama is down the scan and the answer carry on exactly as they did without it. This has been
checked against a stub embedder and the failure paths. Existing snapshots are also embedded on
the first question without rescanning or dropping imports. See [answer quality checks](docs/ANSWER_CHECKS.md)
for context handling and the repeatable local-model comparison. The GitHub connector supports GitHub.com; GitHub Enterprise hosts are not implemented. It collects files in the selected branch snapshot, without GitHub issues, PRs, commit history, Git LFS objects or submodule contents. Jira issues and selected Slack channels are read separately.

Selecting a project or platform does not grant access. Reading requires your credential and an explicit scope: one repository, one Jira project, or selected Slack channels. In the current React Connections screen, Jira credentials can be saved locally, and Slack supports its configured OAuth connection. GitHub and Slack user tokens can be set in `.env`; the legacy interface at `/legacy` also exposes credential forms. The Slack bot-token connector is not implemented. Use the Slack user-token path described in [START_HERE_WINDOWS.md](START_HERE_WINDOWS.md).

Saved credentials stay in the local, git-ignored `.env` file. Forms never return the token values, accept only registered setting names, and reject line breaks. OAuth scopes are fixed by the connector registry and redirects require a matching single-use state. Select the account and source scope deliberately before reading.

A **complete** scan means all discovered, supported, policy-allowed files within scope were processed. It never means every file in the project was examined. Unsupported files and deliberately excluded paths remain listed as skipped. Size/encoding omissions, unreadable supported files or a truncated tree produce a **partial** scan with warnings. A tree limit means some files cannot even be enumerated; the interface says so. A partial snapshot can answer only from its available excerpts.

Potential secret filenames, dependency folders, build artefacts, lock files, symlinks and unsupported formats are excluded. Dependency folders such as `.venv`, `node_modules` and `vendor` are discarded before the entry cap is applied and the crawler does not descend into them, so a repository that commits its virtual environment still has its own source read. The count of files dropped this way is reported in the scan log. This filename policy is not a secret scanner: credentials embedded inside an otherwise normal source file can still enter the local index. Review what you select and keep credentials out of project files.

Refresh is manual. Short transient failures get bounded retries; longer rate-limit waits are reported so you can retry later. GitHub and local-file retries reuse completed file reads after checking current access and content hashes. Jira/Slack reads still restart; there is no scheduled sync or incremental archive backfill. See [task 7.2](docs/TASK_7_2.md).

Repository scans, Jira and Slack reads, overview builds and Jira task explanations have a shared job banner in the
React interface. You can navigate or reload while they run. **Cancel job** requests a safe stop;
the current connector or model request must finish first. **Retry job** starts a new attempt
after a failure, cancellation, partial result or app interruption. Jobs do not restart
automatically, and only one job or answer runs at a time. The latest result is saved across
app restarts. See [task 5.5](docs/TASK_5_5.md) for behavior and verification.

After reading issues in Connections, open **Jira tasks**, select an imported issue and click
**Explain task**. The screen shows its purpose, requested work, explicit acceptance criteria
and suggested clarification questions. Each point has a citation and an inspectable supporting
quote; model name and generation time remain visible. You can navigate while the explanation
runs, reload a saved result, or cancel and retry through the shared job banner. Jira access is
checked before returning imported text or saved explanations, and before publishing a new
result. A source refresh clears old explanations. Missing details stay explicit; this screen
does not verify code implementation. See [task 6.2](docs/TASK_6_2.md) for limits.

For the selected issue, click **Related files and discussions** to reach the two source panels.
Explicit issue keys, source URLs and indexed file paths produce **Confirmed link** cards;
shared words alone produce **Possible connection** cards. Expand the evidence to inspect the
reference and open files at the scanned commit. These links load without Ollama. Slack excerpts
retain recorded authors and timestamps; their links open the first message of the imported
excerpt. Coverage, empty results and source-specific access failures remain visible. A linked
discussion does not establish an agreed decision. See [task 6.3](docs/TASK_6_3.md).

On **Team decisions**, choose an imported Slack channel and click **Summarize decisions**.
Ollama reads its saved passages in bounded parts. Each point includes supporting quotes and
expandable messages; recorded decisions, proposals, historical context, possible conflicts and
unclear wording have separate labels. The screen shows the model, saved time and source coverage.
Generation continues across navigation, with cancellation and retry in the shared job banner.
Reload restores the saved summary. These labels describe imported wording; they do not establish
current team policy. See [task 6.4](docs/TASK_6_4.md).

Slack reads now paginate thread replies, deduplicate repeated messages and retain recorded
edit times and direct message links. Current text and thread relationships are rechecked before
saved content is used. Changed or removed messages invalidate old summaries and answers; use
**Connections → Read messages** and then regenerate the summary. Temporary failures withhold
unchecked content and preserve the previous snapshot. Limits and gaps remain visible; this is
a bounded read rather than a live message subscription. See [task 6.5](docs/TASK_6_5.md).

Each source on Connections also shows **Import coverage**: what was read, what was skipped or
failed, when it was saved, and which limits or gaps apply. Expand **Coverage details and limits**
for repository skip reasons, Jira comment/text omissions, or Slack channel/thread failures.
Older imports show **Coverage unknown** until another read records this information. A finished
job can still have incomplete coverage; see [task 5.6](docs/TASK_5_6.md).

Jira imports include custom text fields such as acceptance criteria and paginate incomplete
comment lists. Long descriptions and comments become searchable excerpts instead of ending
at the old 3,600-character cutoff. The limits are 1,000 comments, twenty comment pages and
200,000 characters per issue; omissions are reported in coverage. Use **Read issues** to update
older imports. Attachments and non-text custom fields are excluded. See [task 6.1](docs/TASK_6_1.md).

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

The app binds only to `127.0.0.1`. On Windows, the owner can create up to 25 member accounts
from Account settings. Each account has its own source credentials, index, answers and jobs;
members never inherit the owner's sources. Source access is checked before using saved content
and again before publishing generated answers. See [task 6.7](docs/TASK_6_7.md).
Keep hosting local; this does not add LAN hosting or SSO. HTTP cookies are allowed only on
loopback; HTTPS uses Secure cookies. The Windows account running the app remains trusted.
Protect local data and backups with operating-system permissions.

Production source credentials use separate Windows current-user DPAPI vaults. Existing owner
credentials are migrated out of `.env` after encryption is verified; `.env` retains model and
other local settings. Account settings accepts new credentials without displaying saved values.
Owner-only audit records contain action metadata, not credential values or source content.

One continuous debug log is written to `data/logs/pka.log`, covering startup, repository saves, every GitHub request with its status and remaining allowance, scan starts and endings, retrieval for each question including which excerpts were chosen, and every model call with its timing. It rolls at 5 MB and keeps five previous files. `PKA_LOG_LEVEL` changes the level. It never records the token, source excerpt text or answer text, and it withholds question text unless `PKA_LOG_QUESTIONS=1` is set, recording only the length and word count. Alongside it, every scan writes a plain-text report to `data/logs/scan-<id>-<status>-<time>.log` listing the counts, the reason totals and every candidate file with its state. The twenty most recent are kept. Set `PKA_LOG_DIR` to put them elsewhere. The report holds paths, states and counts only, never source text, tokens or your questions. The application writes its own settings, scan metadata, excerpts, answers and feedback under `data/`. It never writes to GitHub. The `.env` file and local database are unencrypted files protected by your operating-system account. Never commit them or share them with the project ZIP. Changing the selection clears previous indexed content and answers. Rescanning clears old answer feedback as well, preventing old source excerpts from being retained as answer history. This is logical removal from application results, not forensic erasure of disk backups.

To read that log without opening the file, use `python -m pka.logs`. It shows the last forty events by default. `-n 200` shows more, `-e ask` keeps only events whose name starts with that prefix, `-g chat_bridge` keeps lines containing that text, `--errors` keeps warnings and errors, `--follow` prints new events as they arrive, and `--path` prints where the file is. The most useful one is `--last-ask`, which prints the whole trace of the most recent question: the terms it was reduced to, the excerpts that were retrieved, the model call, the repetition and citation checks and the timing. That is normally enough to explain an answer that came back wrong without reading anything else. The log is deliberately not served over HTTP, so this is the way in.

Only a fixed Python MCP module is launched. Downloaded project code is never executed. Source text goes into a labelled data section in the prompt. The model has no tools, secrets or unrestricted network actions. Prompt instructions reduce injection risk but do not make model explanations infallible. Output is displayed as text, not HTML.

## Parallel processing

Independent work inside a job runs with bounded concurrency. File reads default to four
at a time (`PKA_READ_CONCURRENCY`, maximum eight); embedding batches and overview topics
default to two (`PKA_EMBED_CONCURRENCY` and `PKA_OVERVIEW_CONCURRENCY`, maximum four each).
Set any limit to `1` in `.env` to use sequential processing for that stage. Restart the app
after changing these settings. The single-job guard still coordinates source changes and
database publication, and scan file/byte limits still apply.

Completed overview topics appear as they finish, in their original topic order. Read-only
analysis of facts, diagrams and file roles runs off the web server's event loop so sign-in
and status requests remain responsive during those passes. All topic
query embeddings are prepared before the explanations, avoiding repeated switches between
the embedding and answer models. Cancellation stops new requests, drains the bounded set
already in flight, and prevents cancelled results from being published. Source revocation
also prevents late vector and overview writes.

Ollama controls actual model concurrency separately. Its `OLLAMA_NUM_PARALLEL` setting must
be supplied to the **Ollama process**, not this app's `.env`; changing the app limit alone
cannot increase that server limit. Parallel model requests need additional memory and may
not improve throughput on a fully occupied CPU. Measure before increasing the server setting;
use an app limit of `1` if simultaneous requests are slower. See the
[Ollama concurrency documentation](https://docs.ollama.com/faq#how-does-ollama-handle-concurrent-requests).

`python scripts/benchmark_parallel.py` compares sequential and concurrent file reads using
a disposable fixture with simulated I/O latency. Add `--ollama` only when the local model is
idle to also compare embedding throughput on synthetic text. Neither mode reads a live
repository, changes the application index, or modifies Ollama settings.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\smoke_demo.py
.\.venv\Scripts\python.exe -m pka.doctor
.\.venv\Scripts\python.exe -m pka.acceptance
```

The first two checks need no account or model. `pka.doctor` checks the actual local Ollama service and your configured repository without printing tokens or file contents. The test record and remaining verification are in [docs/STATUS.md](docs/STATUS.md).

`pka.acceptance` tests the saved GitHub, Jira and Slack connections through the real MCP
subprocess. It reads a pinned GitHub file, the selected Jira project's issues and the selected
Slack channels. It leaves the application index unchanged and saves counts and check results
under `data/acceptance/`, without credentials or source contents. Use `--source jira` to retry
one service, `--timeout 180` to set the per-service deadline, or `--output report.json` to choose
the report path. A missing connection, a failed read or an empty source cannot complete the
three-service acceptance task. See [task 5.1](docs/TASK_5_1.md) for the recorded run and remaining work.

## Evaluating generated answers

`python -m pka.answer_evaluation --set evals/answers_bsa.json --output data/acceptance/answers.json`
runs six source-checked questions through the local app, including real retrieval and Ollama.
The set must match the selected repository and exact commit. Results separate retrieval,
citation checks, reference-phrase coverage, expected refusal behavior and human review.
Automatic checks are not factual accuracy. Reports exclude generated prose and source excerpts;
`--inspect-report report.json --case database` displays an exact retained answer for review.
See [task 5.2](docs/TASK_5_2.md) for the baseline, review rubric and commands.

## Checking saved source access

`python -m pka.access_check --output data/acceptance/access.json` rechecks the saved Jira
issues and Slack channels through the real MCP connector, using a disposable database copy.
It leaves the application's index unchanged and records no source text or credentials.
The app also runs these checks before using cached external information. Changed Jira text
requires **Read issues** again; a temporary verification failure blocks answers until retry.
See [task 5.3](docs/TASK_5_3.md) for the behavior, tests and limitations.

## Refreshing saved information

In **Connections**, use **Refresh repository** for code, **Read issues** for the selected Jira
project, and **Read messages** for the saved Slack channels. A repository refresh clears the
external imports, so read Jira and Slack again afterward. Each source refresh clears previous
answers and the overview; then choose **Build overview** in Project overview. **Rebuild overview**
only regenerates from saved information and does not fetch source changes. The refresh version
survives app restarts, and open pages discard old content when their status poll detects it.
See [task 5.4](docs/TASK_5_4.md) for failure behavior, verification and limits.

## Measuring retrieval

Whether an answer is any good is decided mostly before the model is reached: if the file that holds the answer never comes back, no amount of explaining rescues it. `python -m pka.evaluate` scores retrieval against a labelled question set without calling Ollama at all, which makes it deterministic and fast enough to run after every change.

A question set lives in `evals/`. Each question names the file or files a correct retrieval has to surface, and sits in one of four bands: `lexical` where the question shares words with its answer, `paraphrase` where it deliberately shares none, `conceptual` where the answer spans several files, and `reject` where the right answer is nothing at all, because correctly refusing an off-topic question is half of what this promises. Two sets are included, one per repository measured so far. Writing one for your own project is an afternoon and is the only way to know whether a change helped it.

The command refuses a set whose repository, or optional pinned commit, differs from the active scan.

`--compare` runs word matching alone and then with meaning-based retrieval and prints both with the difference. `--failures` lists every miss with what came back instead and which words were actually searched for, which is usually enough to see why. `--sweep` and `--sweep-reject` try a range of settings and print the score at each, so a constant is chosen by measurement rather than by taste. `--save` and `--diff` compare two runs question by question, regressions first.

Two settings are worth knowing about. `PKA_SEMANTIC_WEIGHT` is how much a meaning-based ranking counts against a word-matching one when the two are combined, and the shipped value was swept rather than guessed. The cut-off below which a semantic match is discarded is not a constant at all: after a scan is embedded, a set of deliberately irrelevant probe questions is run against that snapshot to find where irrelevance tops out, and the cut-off is set just above it. That measurement is stored per scan and per embedding model, so the same code is calibrated correctly on a repository it has never seen, and changing `PKA_EMBED_MODEL` recalibrates rather than inheriting a number that belonged to a different model.
