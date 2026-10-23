# Build plan against the ten-phase chart and the ten UI mockups

Written 9 October 2026. Two documents arrived that are not the same thing as the roadmap already
in this repo: a phase chart naming 126 functionality titles across ten phases, and ten screen
mockups for a product called KT Assistant. This file maps both against what is actually built,
then sets a build order.

Current verification is recorded in [task 5.8](TASK_5_8.md). Phase counts below are the original
9 October inventory, not current completion percentages. Individual task rows have been updated
where later acceptance records exist. The workbook uses separate ticket/task IDs, including 5.1–5.8 and 6.1–6.6.

The backend is already FastAPI (`pka/web.py`, `fastapi==0.142.2`). Nothing needs to be moved onto
FastAPI. The original missing-functionality counts below describe the 9 October baseline; the current screen coverage is listed below.

## Headline

| | Count | Share |
|---|---|---|
| Done | 46 | 37% |
| Partly done | 33 | 26% |
| Not started | 47 | 37% |
| **Total titles in the chart** | **126** | |

The React sidebar now has ten destinations. Home, Connections, Project overview, Ask assistant,
Jira tasks, Team decisions and Architecture have implemented views. Feature explorer,
Troubleshooting and Settings explicitly show planned functionality. The original wizard remains
at `/legacy`. Jira explanations, related source links and cited Slack summaries are available;
requirement implementation checks remain planned.

## Phase by phase

### Phase 01, Foundation and GitHub — 20 of 20 done

Everything in this phase is built and was accepted live on 6 October. GitHub MCP tools, access
checks, commit-pinned snapshots, file listing and reading, repository and branch selection,
exclusion rules, progress and cancellation, change detection, local storage, search, Ollama
answers, sources, missing-information reporting, overview and reading order, feedback, interrupted
scan recovery, logs, the connection doctor and demo mode.

### Phase 02, Jira and Slack connections — reading implemented and checked live

Scoped GitHub, Jira and Slack user-token reads passed live on 22 October 2026. Access checks,
refresh behavior and import coverage have separate acceptance records. The Slack bot-token
path remains a placeholder. Missing workspace configuration prevents Slack message permalinks.

### Phase 03, Reliable current project knowledge — 4 done, 9 partly, 5 not started

| Title | State |
|---|---|
| Test live GitHub, Jira and Slack connections | Done for scoped live reads. See `TASK_5_1.md` and the final rerun in `TASK_5_8.md`. |
| Evaluate answer quality | Progress. `pka/answer_evaluation.py` runs source-checked questions through the app and measures retrieval, citations, reference phrases and refusal behavior separately. Human correctness and source-sufficiency review remains pending; see `TASK_5_2.md`. |
| Recheck Jira and Slack access before using information | Done. Saved Jira issue/comment visibility and Slack history permissions are rechecked before use, cached views, and publication of generated external-source content. See `TASK_5_3.md` for verification and limits. |
| Refresh saved information and cached answers | Done. Transactional source revisions survive restarts; source replacement clears derived caches and open views reload safely. Repository scans invalidate same-commit overviews. See `TASK_5_4.md` for tests, live refresh checks and limits. |
| Improve background jobs, cancellation and retries | Done. Saved job states, shared progress/cancel/retry controls, duplicate-start protection and interrupted-job recovery. Cancellation waits for a safe checkpoint; retries require an explicit action. See `TASK_5_5.md`. |
| Show import coverage and incomplete reads | Done. Connections displays per-source counts, saved-read times, limits and omission reasons. Jira comment/text gaps and Slack history/thread gaps are recorded; older imports remain coverage-unknown until reread. See `TASK_5_6.md`. |
| Improve connection screens and source labels | Done for the current local Connections view: repository, Jira credential/project and Slack channel selection, read actions, labels and coverage. |
| Complete final acceptance and update documentation | Done for technical acceptance and documentation of the current local prototype. Agent answer review is recorded in `TASK_5_8.md`; task 5.2's separate human quality ratings remain open. |
| Provide inspectable evidence for important claims | Done. |
| Label illustrative scenarios separately from actual facts | Partly. Asked of the model, not enforced. |
| Explain supported parts when some information is missing | Done. |
| Show what was checked and what remains unknown | Done. `gaps` in `pka/facts.py`. |
| Identify unavailable, outdated or conflicting sources | Partly. Unavailable yes, conflicting no. |
| Add automatic, incremental or resumable imports | Partly. Recovery exists, incremental does not. |
| Detect changes across connected project sources | Partly. GitHub commit comparison only. |
| Refresh affected relationships and KT explanations | Not started. |
| Remove deleted or no-longer-permitted information | Partly. Slack and Jira replace on read. |
| Show when project knowledge was last refreshed | Partly. Per source, not per project. |

### Phase 04, Project sources and discovery — 2 done, 6 partly, 4 not started

Three of the fourteen sources named in the requirements document are connected. Pull requests,
commit history, live database contents, application logs and monitoring data are all absent, and
`KT_REQUIREMENTS.md` already says so. Documentation, API specification and build configuration are
covered only in the sense that those files live inside the scanned repository, which answers what
the code says and nothing about what happened when it ran.

On the business half: technologies and components are read from files and are solid. Project
purpose is a model-written topic. Project users and main features are not derived at all, and both
appear on mockup 03 as filled sections.

### Phase 05, Connections between project parts — 2 done, 5 partly, 3 not started

The import graph in `pka/diagram.py` is real and the file cards in `pka/roles.py` are exact,
because both are read from import lines rather than written by a model. What is missing is a level
down: calls between functions rather than imports between files, explanations of individual
functions and classes, and the conditions and business rules inside them. Requirements linked to
pull requests and tests cannot be done at all until pull requests are read.

### Phase 06, Complete feature explanations — 0 done, 3 partly, 13 not started

The weakest phase, and the reason is a single missing idea. There is no concept of a feature.
A route, the files reached from it, the table it writes and the ticket that asked for it are each
already known separately. Nothing groups them under one name. Every one of the six titles under
"Explain features with relevant examples" waits on that, and so does mockup 05 in its entirety.

API and database explanation stops at declaration level: `pka/facts.py` finds every route with its
method, path and line, and every table with its line, but not inputs, validation, outputs, field
relationships or what a query changes. External services are named with the line that reaches for
them, which is the "why and when" title; failure behaviour and test environments are not derivable
from a static read and need either documentation or logs.

### Phase 07, Requirements and team decisions — 1 done, 3 partly, 4 not started

Task 6.1 now reads visible descriptions, named custom text fields and paginated comments into
bounded excerpts alongside code. It reports configured limits and incomplete reads; see
[task 6.1](TASK_6_1.md). Attachments and non-text custom fields are excluded.
Task 6.2 adds a per-issue endpoint and screen for cited explanations, requested work, explicit
acceptance criteria and suggested clarification questions. Results run as background jobs and
are saved against the current source revision. See [task 6.2](TASK_6_2.md). Task 6.3 adds explicit
reference and possible word-match links to indexed files and Slack excerpts, with evidence and
current access checks. See [task 6.3](TASK_6_3.md). Comparing requirements against implementation
remains subsequent work.

Task 6.4 adds a dedicated Team decisions screen with channel summaries, verified supporting
quotes, imported messages and status filters. Conservative wording checks distinguish explicit
recorded choices from proposals, historical context and unclear evidence; possible conflicts
retain both cited positions. Results are saved and generated through background jobs. These
checks do not establish current policy or complete semantic correctness. See [task 6.4](TASK_6_4.md).
Task 6.5 adds bounded reply pagination, message identities/edit times/permalinks and snapshot
rechecks that invalidate changed or missing source text and derived results. Transient failures
withhold unchecked content. Live event subscriptions and complete archives remain outside this
scope. See [task 6.5](TASK_6_5.md).

### Phase 08, Tests, failures and troubleshooting — 0 done, 1 partly, 9 not started

Test files are found and each file card says whether a test imports it. Nothing explains why a test
matters, what scenario it covers, or what would fail. Problem investigation does not exist in any
form. Mockup 09 is the whole phase on one screen.

### Phase 09, Learning modes and complete KT — 4 done, 4 partly, 3 not started

The three reader modes are built and working (`MODE_SHOWS` in `pka/static/app.js`), and switching
between them for the same content works. That is four titles done outright.

Deployment and operations stop at listing container, pipeline and hosting files as files. The KT
walkthrough exists as eighteen ordered steps in `pka/overview.py`, which covers the structure
title partly, but the per-feature KT section needs the feature concept from Phase 06.

### Phase 10, Team use and further improvements — local owner login implemented

Task 6.6 implements a local owner account, password sign-in, server-side sessions, expiry,
logout and password recovery. See [task 6.6](TASK_6_6.md). The gate before multiple users has
not passed: per-user source permissions, isolated credentials and audit records remain.
The application remains single user and local.

Semantic search is built and off by default and has never been measured. A larger local model is a
configuration change (`OLLAMA_MODEL`) rather than work.

## Screen by screen

| Mockup | Backend ready | What is missing |
|---|---|---|
| 01 Home | Partly | Recent project changes feed, knowledge gaps summary, feature list, learning cards |
| 02 Connections | Mostly | Import history, per-source last read, "more sources" slots |
| 03 Project overview | Mostly | "Who uses it", "Main features", feature-shaped sections |
| 04 Ask assistant | Yes | Conversation history, follow-ups, the two-part feedback row |
| 05 Feature explorer | No | Everything. Needs the feature concept first. |
| 06 Jira tasks | Partly | Explanation, cited requirements and related files/discussions implemented; requirement implementation comparison remains |
| 07 Team decisions | Partly | Cited summaries, status labels, bounded threads and content rechecks implemented; current-policy verification and code implementation evidence remain |
| 08 Architecture | Mostly | Tabs for APIs, database, external services, deployment; node detail panel |
| 09 Troubleshooting | No | Symptom input, cause ranking, where to check, suggested checks and tests |
| 10 Settings | Partly | Owner password/session controls available from the username; team, permissions, model settings, refresh schedule and activity log remain |

## Build order

Thirteen steps in four milestones. The order puts visible progress first where the backend already
supports it, then stops and builds the one missing idea that half the remaining chart hangs off.

### Milestone A, shell and what already works

1. **Application shell.** Sidebar with ten destinations, client-side routing, breadcrumbs, project
   selector, the design tokens from the mockups, served by the existing FastAPI app. Keep the
   current wizard reachable as first-run onboarding inside Connections rather than deleting it.
2. **Connections, mockup 02.** Re-skin the existing configuration and scan controls. Add import
   history, per-source last-read times and the read-only badge. New endpoint for import history.
3. **Project overview, mockup 03.** Re-skin the existing overview payload into the mockup layout.
   Add "Who uses it" and "Main features" as new derived sections.
4. **Ask assistant and Architecture, mockups 04 and 08.** Both read payloads that already exist.
   Architecture needs the four extra tabs and the node detail panel wired to `pka/facts.py`.

### Milestone B, the feature concept

This is the keystone. Nothing in the second half of the chart moves without it.

5. **`pka/features.py`.** Derive features by clustering routes, the files reachable from them
   through the existing import graph, the tables those files touch, and the Jira issues whose keys
   appear in them. Name each cluster from its route path and its ticket summaries. Mark every
   membership as confirmed or possible, the same distinction the diagrams already make.
6. **Feature explorer, mockup 05.** Overview, Flow, APIs and data, Tests, Known problems. The flow
   is a per-feature version of the request journey already in `pka/diagram.py`.
7. **Deeper API, database and service explanation.** Phase 06's remaining titles: request and
   response shapes, validation, field relationships, what a query changes, service call sites and
   their recorded outcomes.

### Milestone C, requirements, decisions and problems

8. **Jira task investigation, mockup 06.** Per-issue explanation endpoint, requirement extraction
   from description and acceptance criteria, an evidence match per requirement against the index,
   and an open questions list from what found no evidence.
9. **Team decisions, mockup 07.** Decision extraction from Slack threads, classification into
   agreed, proposed and historical, implementation evidence from the code, conflicting points.
10. **Troubleshooting and test explanation, mockup 09.** Symptom to cause ranking from the feature
    graph, where to check, suggested checks, and relevant tests marked as existing or suggested.

### Milestone D, freshness, home, settings, more sources

11. **Change detection and incremental refresh.** Phase 03's remaining titles. This is what fills
    the "Recent project changes" feed on Home with something real.
12. **Home and Settings, mockups 01 and 10.** Home last because it summarises everything above.
13. **More sources, then multiple users.** Phase 04's pull requests, commit history, documentation
    and logs. Phase 10's authentication gate last, and only against the conditions already written
    in `ROADMAP.md`.

## Two things to decide before step 1

**Frontend stack.** The repository is Python only with no Node toolchain, and the current interface
is hand-written HTML, CSS and JavaScript served straight from `pka/static/`. The mockups are
achievable either way. Adding React and a build step buys component structure and costs a toolchain
on a Windows machine that currently needs nothing but Python and Ollama.

**Where to start.** Step 1 gives something to look at within a day and re-skins work that already
exists. Step 5 is the keystone and unblocks the largest share of what is pending, but produces
nothing visible until step 6.

## Progress

Decided on 9 October 2026: React with Vite for the interface, and steps 1 and 5 built in
parallel. The parallel risk, that the explorer screen would be built against a guessed payload,
is handled by agreeing the shape first in [FEATURE_CONTRACT.md](FEATURE_CONTRACT.md).

### Step 1, application shell — done

`frontend/` holds a React application built by Vite into `pka/static/ui/`, served by the existing
FastAPI process. Sidebar with all ten destinations, client-side routing with a server fallback so
reloading on `/connections` works, breadcrumbs, the design tokens read off the mockups, and the
shared primitives every screen reuses: card, chip, tabs, segmented control, confidence label,
missing-information block, empty state and source link.

Two things in the existing application constrained this and neither was weakened to make the
interface work. The response carries `script-src 'self'; style-src 'self'`, so nothing may be
inlined; `assetsInlineLimit` is zero and the production bundle is external files only. And every
`/api/` request must carry `x-pka-request: 1` and an origin matching the server's own, so the
single API client adds the header and the dev server proxy rewrites the origin.

Home and Connections are live against real endpoints. Both state what they cannot show rather
than filling the space: Home has no feature list and no change feed, and says why for each.
Connections reports import history as not yet served over HTTP, naming where the logs are written.
The other eight screens render a placeholder naming the step that builds them and what it will
hold, which is deleted as each one lands.

### Step 5, the feature concept — first cut done

`pka/features.py` clusters routes by what they are about, follows the import graph out two hops
to find the files a route reaches, and attaches the tables, services, tests and tickets belonging
to those files. `diagram.import_edges` was added so the feature walk and the drawn import graph
resolve imports the same way: an arrow on the diagram and a file inside a feature both mean a real
import line at a known line number.

A ticket key written inside a file is `confirmed` and carries the file and line; a ticket that
only shares a word with the feature name is `possible` and says so. A test joins a feature by
importing one of its files, never by having a similar name. A feature that found no tests, no
storage or no ticket reports each as a gap with what was checked.

Ten tests cover it, and the whole suite is at 238 passing. Against the real index on disk it
derives one feature from the two routes that repository declares, with the flow
`WEBSOCKET /api/live` to `game.py` to `storage.py` to the `rooms` table, every step a real line.

What this first cut does not do: a feature starts at a route, so a project declaring no routes
produces no features, which the payload states rather than leaving to be noticed. No prose is
written for a feature yet. Only outcomes that are derivable are returned, so the three outcome
cards on mockup 05 arrive as one until a model writes the other two and they are labelled
illustrative.

### Step 4, Ask assistant — done

Built next and ahead of its place in the order, because making the new interface the default at
`/` had left the product's main function reachable only at `/legacy`.

The screen renders what the answer actually carries rather than the shape the mockup drew. The
mockup shows a model-structured answer, with a simple explanation, a numbered example and a what
happens next. The backend returns a flat list of checked statements, so that is what is shown,
each with its citations and its support mark. A statement whose content was not found in the
excerpt it cites is marked, in red, with the excerpt one click away, and a statement naming
nothing from this project is marked as well. Both marks already existed in `pka/overview.py`
and had nowhere to appear.

The three reader modes decide how much working is shown, never what the answer is, and the
screen says so next to them. Beginner hides citations and excerpts, Developer shows everything
including the repetition and citation checks, Architect sits between.

One test was added: the answer response is asserted field by field against the names
`frontend/src/lib/answer.ts` reads, so renaming one fails the suite rather than leaving a blank
panel in the browser. The suite is at 239 passing.

### Step 3, Project overview — done

The mockup's layout over the payload that already existed, with three panels corrected to what
the project can actually establish.

"Who uses it" is drawn on the mockup as two filled cards. Nothing derives it. Users are only
knowable from a readme, a ticket or a discussion that names them, and deriving them from file
names is the guess this product exists to refuse, so the panel states that instead of being
filled. "Main features" is filled, from the step 5 derivation, and is empty with its reason on a
project that declares no routes. "Getting started" carries the setup prose and, underneath it,
the commands read straight out of the files with their lines, because a command that is written
down should not be retyped by a model.

Statement rendering moved into `frontend/src/components/Statements.tsx` and the question screen
now uses it too, so the support mark and the names-nothing-from-this-project mark look the same
wherever a model-written sentence appears. Both marks were already computed in
`pka/overview.py` and had never been shown anywhere.

Two tests were added: the overview payload asserted field by field against the names
`frontend/src/lib/overview.ts` reads, and a check that a topic which found no evidence stays in
the payload rather than being dropped, since the screen relies on it being there to say so. The
suite is at 241 passing.

### Step 2, Connections completed — done

The Jira and Slack panels are real, and import history is served over HTTP for the first time.

Jira: the project list is fetched, one project is chosen and saved, and reading is started with
its progress shown. Slack: the channel list is fetched, channels are ticked against the limit the
backend enforces, the allowlist is saved and reading is started. Both panels carry the caveat that
belongs to them, in the interface rather than in a document: Slack does not resolve a message
author to a name because that needs a permission this does not request, and reading again replaces
what was read before.

Import history, `GET /api/import-history`, lists the per-run reports `write_scan_log` has always
written to `data/logs` and that nothing could read without opening the folder. A run that failed
is listed exactly like one that succeeded, because that is the one somebody needs. A second
endpoint serves one report's text, and the name is matched against the pattern this application
writes before it is ever joined to a path. Two tests cover it, one of them asserting that
`pka.log`, an encoded `..` and a crafted name that merely ends in `.log` are all refused and that
a file outside the log folder is never served. The suite is at 243 passing.

### Jira is live after all

Running against the real credentials on this machine, `GET /api/jira/projects` returned
`SCRUM, My PM Team` over the live Atlassian API. `docs/STATUS.md` still records that the
credentials were rejected with AUTHENTICATED_FAILED and that every Jira check is against mocks.
That is now out of date for authentication and for listing projects. It is not yet out of date for
reading issues, which has still never been exercised against a live site. Worth closing properly
by reading the SCRUM project and recording what came back.

### Fixed after first use of the Connections screen

Clicking Read issues before any scan existed printed a traceback on the console and showed
nothing at all on the page. Two separate faults.

The screen offered the button at all. Jira issues and Slack messages are stored against a scan,
so there is nowhere to put them until one exists. Both read buttons are now disabled until a scan
has succeeded, and both panels say why rather than just going grey.

Underneath that, every background read was started with `asyncio.create_task` and never awaited,
so when one raised, the exception went to the event loop as an unretrieved task. The browser had
already been answered "started" and then polled a progress field that stayed empty for ever, and
the only sign of the failure was on a console the user is not expected to be reading. All four
background jobs, scan, overview, Slack and Jira, now run through `Service.background`, which keeps
the failure for the status endpoint to report, clears the progress fields whatever happens so a
read that dies cannot leave the page spinning, and keeps an internal message out of the interface.
Four tests cover it, including the exact sequence that produced the traceback. The suite is at
247 passing.

### Ollama failures told apart

Every way of failing to reach Ollama produced one sentence, "Ollama is unavailable or timed out.
Start Ollama and check the model", which sent a reader looking for a stopped service when the
service was running. Three causes with three different remedies now say which one happened: not
running, with the command to start it; still answering after 180 seconds, which a larger model on
a slow machine genuinely needs; and HTTP 404, which is Ollama saying it has no such model, with
the exact pull command.

Underneath that, the first request after Ollama starts can be refused while the model loads.
That is a cold start, not a broken installation, and the only sign of it was the first topic of an
overview failing while the next seven worked. A connection level failure is now retried once
after three seconds, which removes the whole class of first request failures. A read timeout is
not retried, because waiting 180 seconds twice helps nobody.

Found by the new message within a minute of writing it: this machine's `ollama list` shows
`gemma3:4b`, and asking for it returns `model 'gemma3:4b' not found`. The manifest is there and
the data behind it is not, so it needs pulling again. The old message would have blamed the
connection. Four tests cover the retry and the three messages. The suite is at 260 passing.

### Next

Step 6 builds the feature explorer on the contract above. Step 4's architecture half, the
three derived diagrams, is the remaining re-skin.

### Retrieval measured, and tuned against two repositories

The decision was to improve retrieval rather than train anything. Nothing here is a model
change: the same qwen3:1.7b answers, on the same machine, from better excerpts.

Retrieval had never been measured. The whole log held five answer records, so no change to
chunking or ranking could be shown to have helped. `pka/evaluate.py` scores retrieval against
a labelled set without calling the model, which is deterministic and takes seconds rather than
the minute and a half a generated answer costs on this CPU.

The first measurement found the real gap. On questions sharing words with their answer,
word matching scored mrr 0.73 and needed no help. On questions deliberately phrased in other
words it scored 0.31, because "what stops the same problem being reported twice" and a file
whose docstring says deduplication have no word in common and BM25 cannot bridge that.
Meaning-based retrieval already existed in `pka/embed.py` and had never been switched on.

Switching it on and sweeping the fusion weight contradicted the guess going in. The guess was
that an approximate match should be weighted below an exact one; the measurement said weight
three, and word matching improved rather than suffering, from 0.73 to 0.85. Word matching was
not being protected by a low weight, it was being left to fail alone.

Two bugs surfaced that had been waiting for anyone to turn embeddings on. Raw vector bytes
rode along in every retrieved chunk and stopped an answer being serialisable. And asking
something the project knows nothing about began returning the nearest file instead of nothing,
which is the opposite of what this product is for.

That second one is why the cut-off is now measured rather than written down. An absolute
similarity means something only against a particular embedding model and a particular body of
text, so after a scan is embedded a set of deliberately irrelevant probes is run against that
snapshot to find where irrelevance tops out, and the cut-off is set just above it, stored per
scan and per model.

Two repositories were measured, the second chosen to be unlike the first: an HTTP client
library against an MCP bug-investigation server. The calibration landed at 0.550 and 0.555,
eight thousandths apart, which is the evidence that the scale belongs to the embedding model
and not to the project. Every band improved on the second repository although nothing was
tuned on it, overall mrr 0.31 to 0.64.

| | MCP-project | psf/requests |
|---|---|---|
| Overall | 0.483 to 0.712 | 0.310 to 0.636 |
| Paraphrased questions | 0.312 to 0.479 | 0.056 to 0.292 |
| Shared-word questions | 0.729 to 0.854 | 0.542 to 0.750 |
| Correctly refused | 0.25 to 1.0 | 0.25 to 1.0 |

What is still open. Paraphrase hit@1 is 0.375 and 0.167, meaning the right file comes back but
not first, which points at chunking next rather than at anything to do with the model. The
answer itself is still unscored, only the evidence it is built from. And both question sets
are small, twenty-six and eighteen, so a sweep should be re-run whenever one grows.
