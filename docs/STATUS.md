# Implementation and verification record

## Interactive project overview, 23 October 2026

The overview now opens as a dashboard with a project snapshot and shortcuts for topics,
indexed files, feature groups and items to review. A searchable topic menu replaces the
long report. Each topic offers expandable prose, its original evidence excerpts and source
links; citation clicks reveal the matching excerpt. All modes retain access to every saved
point and fact group. Missing evidence, unsupported claims and failed sections stay visible,
with a separate coverage view to collect the flags. Counts describe the saved data, not an
accuracy score.

The reading checklist keeps progress while navigating topics in the mounted overview. It
resets on a new source revision or page reload and never persists project data in browser
storage. Exploring topics, modes, facts and evidence does not trigger a model build. Existing
session checks, source-access revalidation, explicit rebuild and partial-build behavior are
preserved. Feature summaries are shown in place rather than linking to the unfinished feature
explorer route.

All 20 frontend checks and the production build passed. Seven dashboard checks cover
navigation without refetch/build requests, source expansion, search, checklist preservation
and revision reset, evidence flags, feature errors and partial builds. Live checks in a fresh
tab in the owner's Empricitest profile verified saved content, expandable points, a matching
Jira citation, feature cards and reading progress across topic switches. Topic search and
keyboard activation passed, and 940px and 1440px viewport checks showed the expected layout
changes without horizontal overflow. The temporary viewport override was reset. No browser
console errors were observed. This validates the overview change, not a whole-product
end-to-end run.

## Browser tab loading follow-up, 23 October 2026

Returning to a browser tab used to set the authenticated session to null before checking it.
That unmounted the entire workspace, lost drafts and view selections, and restarted source
reads. Session checks now hide the mounted workspace until the server confirms the session;
the same account keeps its state, while logout, verification failure and account changes
discard it. Late activity responses cannot restore a previous account.

Overview and architecture reads wait for the project revision instead of issuing two initial
requests. Superseded reads are aborted and ignored. Changing the polling interval does not
restart an in-flight request. Saved overview permissions are checked every 30 seconds while
idle and every four seconds during a build, with an immediate refresh on job transitions.
Navigation still checks current source access; it never starts an overview build automatically.
Feature read failures now show their actual error instead of claiming that no features exist.
Cards and page controls adapt to the narrower viewport created by a browser side panel.

The loading screen now distinguishes checking project status, loading the saved overview and
loading progress for an existing build. It explains the source-access check instead of saying
"Reading the overview". The generation action is labelled "Rebuild overview", and the start
notice uses "build requested" so it does not keep claiming a build is running after completion.
Architecture uses the same distinction for its saved diagrams. All 13 frontend checks and the
production build passed again; the running app serves the bundle containing these messages.

The 13 frontend regression checks, 106 authentication/workspace/source-freshness regression
tests and production build passed. The Python run emitted the existing Starlette test-client
deprecation warning. The running app was verified to serve the final compiled bundle.
Vite, React Router and the
new test runner use patched compatible releases; npm reported zero vulnerabilities after
installation. Run the frontend checks with `cd frontend`, `npm ci`, and `npm test`.

Live checks used the owner's existing Empricitest Chrome tab. Connections showed 99 files
read, two skipped and zero failures, with the saved Jira project and Slack channel present.
Read-only MCP checks passed for GitHub, Jira and Slack. Retrying the failed overview through
the browser completed all nine topics with zero failed topics in 648.5 seconds; generated
content still carries the model's evidence/unsupported-claim qualifications.

The Chrome extension detached during the live test and then the Empricitest connection
disappeared from the browser inventory. Full navigation, question submission and visual
verification of the final bundle remain unverified in that live session. Feature explorer,
Troubleshooting and Settings are still placeholder routes, so this is not a whole-product
end-to-end sign-off. Account settings is implemented separately at `/account`.

## Task 6.7 private workspaces and source permissions, 23 October 2026

Task 6.7 adds owner-managed member accounts and separate indexes, source credentials,
retrieval, cached views, feedback, background jobs and import reports for each authenticated
account. GitHub checks now also protect cached code views and the publication of generated
answers. Existing Jira issue and Slack message checks remain in place. Disabled accounts lose
their sessions immediately. See [task 6.7](TASK_6_7.md) for the local Windows trust boundary.

All 707 regression tests passed, followed by 22 focused credential/diagnostic checks after
adding encrypted-vault support to the local diagnostic CLIs. The production build, real
HTTP/MCP fixture smoke and six Chrome account checks passed with no browser page errors.
The suite emitted the existing Starlette test-client deprecation warning. The narrow-screen
app shell remains outside this desktop account scope.

The live app was backed up and updated. All 20 project table counts and the existing owner's
password record were preserved. Credentials were moved to a verified current-user Windows
DPAPI vault and removed from `.env`. A read-only diagnostic confirmed the encrypted GitHub
credential still reaches the selected branch and that the configured Ollama model is present.
The earlier network failure was fixed by launching outside the restricted runner: the live
repository scan completed with 99 files read, two skipped and zero failures. Ollama was started
and qwen3:1.7b answered a short test prompt successfully.

Task 6.7 is **Done within this local Windows account scope**. The implementation includes the
credential and audit foundation for 6.8; the separate 6.8 closeout and 6.9 deployment/backup
work remain queued. Verification artifacts are in `outputs/task-6-7-browser/` beside the repo.

## Task 6.6 owner login and secure sessions, 23 October 2026

Task 6.6 adds one local owner account, one-time setup, salted password hashes and persistent
server-side sessions. Project APIs require sign-in. Account controls support password changes,
current/all-session logout and local terminal recovery. Sessions expire after 30 minutes without
interaction or eight hours after login. Slack OAuth approval is bound to the initiating session.
See [task 6.6](TASK_6_6.md) for the authentication boundary and deployment limits.

All 694 regression tests, the production frontend build, dependency check and authenticated
HTTP/MCP example smoke passed on 23 October. The test suite emitted one existing Starlette
test-client deprecation warning. Seven fresh-account Chrome checks covered setup/confirmation, HttpOnly cookies,
navigation/reload/background scanning, cross-tab logout, revoked-cookie replay, incorrect login,
password changes, idle/absolute expiry, mobile layout and sign-out-all. Two further Chrome checks
confirmed that the local app shows owner setup and denies unauthenticated project requests.
No browser page errors were reported. Browser tests used disposable accounts and simulated sources.

The local app was started after a fresh database backup. All 20 existing project database tables
were unchanged, including SQLite metadata. The owner setup code remains in its local file so the
user can choose their own credentials. No production owner account was created by the checks.
The prior task's implementation and browser evidence were present when this work resumed; the
tracker and final verification record had not yet been completed.

Task 6.6 is **Done within this local-owner scope**. The tracker now records the final test and
browser results, with every unrelated cell, style and native workbook part preserved.
Verification artifacts are in `outputs/task-6-6-2026-10-23/` beside the project folder.
This remains one owner on loopback HTTP. Team membership, per-user source permissions and
isolated credentials remain tasks 6.7–6.8. Task 5.2's human quality ratings remain open.

## Task 6.5 Slack threads and message changes, 22 October 2026

Task 6.5 adds bounded thread pagination, broadcast/page deduplication, per-message evidence,
direct permalinks and recorded edit times. Current channel snapshots are checked before using
saved content. Changed, missing or inaccessible text invalidates source and derived caches;
transient failures withhold unchecked content. Successful refresh replaces the snapshot.
Concurrent checks cannot purge newer imports, and fast summary jobs now update the screen
even when they finish between polls. See [task 6.5](TASK_6_5.md) for scope and limits.

The production frontend build, all 663 regression tests, 214 final affected checks and eight
Chrome checks passed. Browser checks covered later-page evidence, deduplication, edit times,
direct links, coverage, edited/deleted content, outage/recovery, refresh and 900-pixel layout.
A live read-only MCP check imported three messages into six excerpts/four summary passages
and verified current snapshots and direct links twice. The real channel had no thread replies;
multi-page and removal scenarios were verified with controlled Slack HTTP responses.

The local app was restarted with a database backup and its selected Slack channel refreshed,
preserving GitHub and Jira imports. The initial summary regeneration hit Ollama's 180-second
response timeout; retry through the background-job controls succeeded with qwen3:1.7b and
eight saved points. Three further Chrome checks confirmed the live summary, message dates,
direct links and persistence across Jira navigation/reload, with no page errors or new
generation requests. Excel task 6.5 is **Done**, with other rows and workbook features preserved.
This task does not add a live event subscription or guarantee complete workspace history.

## Task 6.4 Slack discussion summaries with sources, 22 October 2026

Task 6.4 replaces the Team decisions placeholder with selected-channel summaries, exact
supporting quotes, expandable imported messages, source links and status filters. Conservative
wording checks distinguish recorded decisions, proposals, historical context and unclear
evidence; possible conflicts retain both positions. The actual model and source coverage are
visible. Background generation supports navigation, cancellation, retry and saved results.

The production frontend build, 614 regression tests, 108 final focused checks and twelve
controlled Chrome checks passed. A live read-only Slack/Ollama run used qwen3:1.7b to read three
passages in two parts, producing eight points with validated quotes. The existing app was
restarted with this build and a separate real summary was saved, preserving all imported data
and the existing Jira explanation. Three further Chrome checks against the running app verified
saved evidence, model details and navigation/reload with no generation requests or page errors.
This second generation produced nine points. Both runs
correctly kept the long, partial conversation's status unclear rather than asserting agreement.
See [task 6.4](TASK_6_4.md) for evidence rules and limitations. Task 6.4 is **Done within this
summary scope**. Fuller Slack threads and edit/deletion handling are covered by task 6.5 above.

## Task 6.3 related files and discussions, 22 October 2026

Task 6.3 adds separate related-file and Slack-discussion panels to the selected Jira task.
Explicit references are confirmed links; shared words are possible connections. Bounded
evidence, pinned file links, stored discussion permalinks, pagination and coverage explain
what was matched. Each source is checked before use; no model or external write is needed.
The production build, 561 regression tests, 74 final focused checks, 14 Chrome checks and twelve live relationship
reads across six saved Jira tasks passed. See [task 6.3](TASK_6_3.md) for scope and limits.
Task 6.3 is **Done**. Decision summarization is covered by task 6.4 above; fuller Slack thread handling
is covered by task 6.5 above. These links do not verify requirement implementation.

## Task 6.2 selected Jira task explanations, 22 October 2026

Task 6.2 adds a searchable imported-task list and grounded explanations with requested work,
acceptance criteria, clarification questions, exact supporting quotes and model details.
Explanations use the shared background job lifecycle, persist across navigation/restarts,
and are invalidated by source changes. Jira access is rechecked before use and publication.
See [task 6.2](TASK_6_2.md) for verification and scope. Code/discussion linking is covered by task 6.3 above.
The production build, 515 regression tests, 35 final focused checks, ten Chrome checks and
scoped live Jira/Ollama checks passed. Task 6.2 is **Done within this explanation scope**.

## Task 6.1 Jira requirements and comments, 22 October 2026

Task 6.1 is **Done within the documented import scope and limits**. Custom text fields retain
their Jira names, incomplete comment lists are paginated, and long issue text becomes multiple
searchable excerpts. Access rechecks cover those excerpts. Coverage reports remaining limits.
All 487 tests, 38 final affected checks, five Chrome checks and scoped live Jira reads passed.
See [task 6.1](TASK_6_1.md). The dedicated Jira explanation screen is covered by task 6.2 above.

## Task 5.8 acceptance and documentation, 22 October 2026

Task 5.8 is **Done for technical acceptance and documentation**. The Windows guide and current feature inventory now describe
the working screens, scoped source readers, import coverage and background controls.
Historical records below retain their original dates. Five dedicated analysis/settings
screens remain planned.

Live GitHub, Jira and Slack checks, fresh isolated Jira/Slack imports, saved-source access,
the HTTP/MCP fixture smoke and seven Chrome checks passed. Acceptance found and fixed a
smoke-runner race and Windows child-process cleanup. All 463 Python tests passed; after
the final prompt/citation-schema changes, 37 affected tests passed. Answer review also
corrected overbroad missing-evidence wording and constrained generation to supplied citation IDs.
All nine latest answer cases pass their checks after the targeted multipart rerun. The agent
reviewed the exact answers at the user's request; minor repetition remains in two responses.
Task 5.2's separate human quality ratings remain unrecorded and are not represented as complete.
See [task 5.8](TASK_5_8.md) for exact evidence, final test results and remaining review.

## Task 5.6 import coverage, 22 October 2026

Task 5.6 is **Done**. Connections shows per-source coverage, separate item/excerpt counts,
read times, limits and omission reasons. Jira reports missing comments and shortened issue
text; Slack reports channel, history and thread gaps. Partial reads update the job banner.
Old imports without coverage metadata stay explicitly unknown, and failed refreshes retain
the previous import with its original timestamp.

All **458 Python tests**, **seven isolated Chrome checks**, and the production frontend build
passed. The running app was restarted with its 1,099 chunks and two source imports preserved.
Browser checks used fixture HTTP responses through the actual adapters and app. See
[task 5.6](TASK_5_6.md) for verification and scope limits.

## Task 5.5 background jobs, 22 October 2026

Task 5.5 is **Done**. Scans, Jira and Slack reads, and overview builds now save their job state
and show progress, cancellation and explicit retry controls across React pages. Navigation and
reload preserve the current job. Duplicate starts and stale actions are refused; unfinished
jobs become Interrupted after an app restart. Cancellation waits for the current request to
reach a safe checkpoint.

All **429 Python tests**, **five isolated Chrome checks**, and the frontend production build
passed. Browser checks used delayed fixture connectors and a fixture model through the real
API; they did not contact live source accounts. The running app was restarted and reconnected
to the same project; its 1,099 chunks and two source imports were preserved. See
[task 5.5](TASK_5_5.md) for evidence and limits.

## Task 5.4 source and cache refresh, 22 October 2026

Task 5.4 is **Done**. Source revisions now persist transactionally across restarts; repository
rescans invalidate derived content even at the same commit. Open overview, architecture and
feature data reload after a revision change, ignoring late responses from old requests.
Connections accurately labels repository refresh and explains the Jira, Slack and overview steps.

All **409 Python tests**, **five isolated Chrome checks**, and the frontend production build
passed. Live refreshes of four Jira issues and one Slack channel passed on a disposable index,
including cache invalidation, persisted refresh state and a final access check. The user's saved
index and answer reviews remain intact. See [task 5.4](TASK_5_4.md) for evidence and limitations.

## Task 5.3 source access checks, 22 October 2026

Jira and Slack access checks now cover saved content before use, cached views and publication
of generated external-source content. Jira verifies that imported comment text remains visible;
changed snapshots require a new read. Confirmed denial clears the affected source and derived
caches. Temporary verification failures block the response while retaining the saved import.
Both interfaces hide cached content when checks fail, and removed file-backed credentials take
effect without restarting.

The read-only live check passed for four Jira issues and one Slack channel. All 404 Python tests,
six isolated Chrome checks and the frontend build passed. Task 5.3 is **Done** for these scoped
access checks. Tests simulate revoked access without changing the user's
accounts. See [task 5.3](TASK_5_3.md) for the repeatable command, verification evidence and limits.

## Answer quality follow-up, 22 October 2026

The Ask screen now presents a direct answer before supporting details. Retrieval prioritizes
matching configuration definitions, recognizes word inflections and model roles, retains short
definitions, and scopes direct file questions to that file. Ollama receives instructions to
answer each requested fact, keep components separate, and disclose missing evidence without
contradicting an answer. Focused structured outputs limit unrelated additions. No project
answers or model values are hardcoded; model weights have not been trained or changed.

All 378 Python tests and the frontend build passed; 14 targeted tests passed again after the
last instruction clarification. The expanded nine-case live run passed its mechanical checks.
Agent inspection found and corrected an extra startup sentence that those checks missed;
the startup recheck gives only the correct command and port. The observed embedding and
chat-model questions now return the configured names. Chrome checks covered the real answer
flow and the final layout at 1024 and 1440 pixels. Five live cases were rerun after the final
prompt change; all passed their checks and agent inspection of the requested facts.
See [the follow-up record](TASK_5_2.md#follow-up-verification)
for evidence and limitations. Task 5.2 still awaits human evaluation of the recorded answers.

## Task 5.2 answer evaluation, 22 October 2026

Implemented `python -m pka.answer_evaluation` and a six-case, source-checked reference set for
the current BSA commit. The live app/Ollama run finished all six cases. All four answerable
cases retrieved the expected excerpt; three matched the required cited phrases, and five of
six passed the automatic checks. These are retrieval and mechanical checks, not accuracy.

Agent inspection found a wrong PDF answer for an image-extension question despite the correct
image list being retrieved, a contradiction in the startup answer, and repetitive or unrelated
extra statements. No generation errors occurred. Twenty-nine targeted tests passed, covering
scoring, scope guards, review binding and read-only inspection. Human correctness and source
sufficiency remain unreviewed, so task 5.2 remains **Progress**. See [the task record](TASK_5_2.md)
for actual timings, limitations, findings and the review workflow.

## Task 5.1 live connection checks, 22 October 2026

The new `python -m pka.acceptance` command exercised the saved connections through the real
MCP subprocess. GitHub passed: 64 manifest entries at a pinned commit and one non-empty file
read (3,686 bytes). Slack passed: the selected channel was visible and returned two messages.
After replacing the Jira API token, Jira authenticated and read four issues from the selected
project, validated their source URLs and rechecked access. The final all-service run finished
at 10:29:12 IST with `task_complete: true`. Task 5.1 is **Done** for these scoped connection checks.

No Slack workspace name is saved, so message-link construction remains unverified. The two
returned messages contained no thread replies. These checks do not establish complete history,
thread coverage or model quality. Separate Chrome checks verified repository reconnection,
Slack import and a successful four-issue Jira import. Browser testing also led to a Jira credential form
and a fix for the repository-field overflow; six UI regression checks and the frontend build
passed. See [the task record](TASK_5_1.md) for evidence, coverage limits and rerun steps.

## Historical acceptance records

The records below describe their original dates. Current connector, browser and quality results are above and in [task 5.8](TASK_5_8.md); historical limitations are not the current feature inventory.

Delivery: Stage 2 local prototype. Recorded on 6 October 2026 (IST). The project overview and
the question flow were revised on 8 October 2026; what that revision did and did not verify is
recorded below.

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

Stage 2 project overview: eight topics, nine once Slack or Jira content has been read, each
retrieved and explained separately so a weak section cannot borrow confidence from a strong
one, each carrying its own excerpts and its own statement of what is missing. A topic with no
matching evidence is recorded as having none rather than dropped, and a topic that needs Slack
or Jira is not attempted when neither was read. A suggested reading order is derived from the
indexed file paths and labelled as derived, not model-written. The overview is cached against
the commit, survives a refresh that lands on the same commit, and is cleared when the
repository changes.

Revised on 8 October 2026 after reading the overview the application had actually produced for
a real repository. Three faults were visible in it and all three are addressed.

The sections repeated themselves: the setup section said the same thing in its first, second
and seventh statements. Every statement in the purpose section cited all five excerpts at
once, which makes a citation useless as a pointer. And the setup section stated that the server
runs on port 3000, which no excerpt said and which the project's own code contradicts.

The first two are now corrected in `pka/overview.py` before anything is displayed: a statement
that restates an earlier one is dropped, and a citation of every supplied excerpt is narrowed
to the ones whose text carries the statement's wording. The third cannot be corrected from
outside the model, so it is measured instead. Each statement is compared against the excerpts
it cites and one whose content is not found there is marked for checking, with the excerpt
underneath it. Checked against the real statements from that run: the two accurate ones pass,
the port 3000 claim and an invented sentence are both marked.

Alongside the prose, `pka/facts.py` reads groups of facts straight out of the indexed text with
no model involved: what was read and in which languages, the documentation the project ships,
every declared dependency with its version, the commands the project defines, every route
declaration, the tables and data shapes, and the names of the settings read from the
environment. Each entry carries the file and line it came from and links there at the scanned
commit. On the repository used here this produced 35 dependencies with exact line links, two
route declarations and four environment settings, none of which the five model-written sections
had found. A group whose patterns match nothing is omitted rather than filled.

Retrieval for a topic now merges two to four separate searches by reciprocal rank fusion, and
prefers one excerpt per file before taking a second from any file. On the same repository every
section went from repeating files to drawing on five distinct ones. A topic also states how much
test code counts as evidence for it, so setup is not explained from a test file while the topic
about checking is explained from nothing else, and copied-in component libraries are excluded
from overview topics entirely.

The overview payload is saved after every topic, so finished sections can be read while the
rest are still being written. The previous behaviour showed nothing for the whole run, which on
the recorded real run was 501 seconds.

Answers now carry the same checks, and report which words the search used, which it mapped onto
the project's own vocabulary and which appear nowhere in the scanned files.

Walkthrough and diagrams, added 8 October 2026 after the overview was reported as too much
text to read. The content was complete by then and still not being used, which is a
presentation problem rather than a retrieval one.

The overview now opens as an ordered handover: what it is, its shape, what uses what, getting
it running, one request followed through, where information is kept, how it is checked, and the
reading order last. One step is shown at a time, each opening with the sentence a colleague
would say, with prose cut to the first three points and the rest folded. Steps carry keys
rather than copies of the sections, so a section cannot leave a stale duplicate inside a step,
and a step this project cannot fill is dropped rather than shown empty. The previous
everything-at-once view is still reachable by a button, which is the better one for searching.

Three diagrams in `pka/diagram.py`, all derived, none model-written. A stack putting every
file that was read into one of five layers by its path and contents. An import graph where an
arrow exists because a file contains an import naming another, carrying the line number of that
import, laid out by import depth so arrows run left to right. And one worked request from a
client through the receiving file, its declared addresses, the modules it imports and the table
one of them creates. On the repository used here the import graph came out at 11 boxes and 13
arrows, and the journey at 7 boxes and 6 arrows, including the table created at storage.py line
25. Positions are decided in Python and pixels in the browser, and the browser builds the
shapes element by element, so no markup is handed to it as text.

Reported after first use and fixed the same day: the card badge read "3 OF 8" directly above a
walkthrough rail reading "7 of 7", two different counts in the same shape side by side with
nothing saying what either counted. Worse than the confusion, the step list was being built
from the sections finished so far, so it grew during a build; a reader sitting on the last
step had a newly finished step inserted ahead of it and was moved onto different content
without touching anything. The list is now settled against the topics the build intends to
attempt, so every step keeps its number from the first second, a step still waiting for its
prose is marked rather than absent, and the reader's position is held by the step's name
instead of its index. The badge now says what it counts.

Two further faults were found by the tests written for the diagrams and both are fixed. Python's `import
pytest` resolved to the project's own `pytest.ini`, drawing an arrow between two files with no
relationship; an import can now only land on a file that language's import could have named.
And two files importing each other produced an arrow assigned backwards, which the browser
would have drawn doubling back through its own boxes; such an arrow is now marked, routed under
the boxes as a dashed curve, and counted in the diagram's own note, because files depending on
each other is a fact about the project worth stating rather than straightening out.

Optional semantic retrieval, off unless `PKA_EMBED_MODEL` names a model: chunks are embedded
after a scan, a question is embedded when asked, and the nearest excerpts join the word matches
in the same fusion rather than replacing them. Candidates must clear both an absolute and a
relative similarity floor, so a snapshot that is about something else contributes nothing.
Vectors are dropped with the snapshot they describe.

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
bot token mode remains a placeholder. Multiple-user accounts and automatic scheduled sync are
not implemented. Semantic embeddings are implemented and off by default, and have not been run
against a live embedding model.

A handover requirements document was supplied on 8 October 2026 describing the full product:
one connected understanding across fourteen sources, taught to a new developer with
project-specific real-life examples backed by evidence. Three of those fourteen sources are
connected here. What was built against that document on the day, what was already there and
what is still missing is mapped section by section in
[KT_REQUIREMENTS.md](KT_REQUIREMENTS.md), including the two items that are not presentation
problems: there is no concept of a feature to hang a per-feature story on, and the prose is
limited by a 1.7B model rather than by the retrieval around it.

Added that day: outside services with the line that reaches for them and what they are for;
build, container and pipeline files listed as files with the wording saying a definition is
not a run; a card per important file giving its purpose, what it answers or declares, who uses
it and what it uses, with the wiring read from the import lines; three audience modes; and a
standing group naming what the scan cannot reach with what was checked. The relevance rule
from that document is enforced rather than requested: a statement naming nothing from this
project is marked in the interface, which was checked against the document's own two bad
examples and three good ones.

## Executed checks

| Check | Outcome | What it establishes |
|---|---|---|
| pytest suite | 228 passed | Behaviour against local fixtures and HTTP mocks, including actual MCP subprocess calls |
| Real HTTP example-mode smoke check | Passed | Start app, serve UI assets, scan via MCP, retrieve, produce a simulated answer and save separate feedback |
| Example smoke counts | 3 files read, 1 skipped, 3 retrieved sources | Expected fixture coverage; not a real project scan |
| Dependency installation and `pip check` | Passed on Linux / Python 3.12.14 | The installed test environment has no declared dependency conflicts |
| CPython 3.10 / Windows AMD64 binary-only pip resolution | Passed | Declared version and wheel compatibility; not Windows runtime execution |
| Python 3.10 syntax parsing | All 17 Python files passed | The source does not require Python 3.11+ syntax |
| JavaScript syntax check | Passed | Browser script parses under Node; not a graphical browser test |
| Official dependency/API documentation | Reviewed | Requirements and API choices are recorded in DEPENDENCIES.md |

The suite covers scope validation; excluded and unsafe paths; function boundaries and line preservation; ordinary-language retrieval; correct commit/line links; separate quality/source feedback and stale-feedback rejection; no-evidence answers; deleted-file replacement; partial and failed scans; restart recovery; access revocation and changed branch heads; cancellation; GET-only requests; manifest pagination; truncated-tree fallback; 401/403/404, long rate limits, redirects and transient retries; registered MCP read-only tools; MCP error preservation; bounded Ollama requests, untrusted context and unknown-citation rejection; local HTTP boundaries; and retaining sources when Ollama fails.

One dependency emitted a deprecation warning: Starlette's test client currently supports HTTPX but recommends its newer HTTPX2 transport. It did not fail a test. The application itself uses the pinned HTTPX client and MCP v1 SDK. Review dependency upgrades together rather than changing one pin blindly.

## Not executed on 8 October 2026

- A live Ollama model. The Ollama service was not running in this environment, so no section of
  the revised overview and no answer was produced by a real model on this date. Everything
  above about repetition, citations, support marking, retrieval and the fact groups was checked
  against the recorded output of the earlier real run, against the real 205-chunk index on
  disk, and against stub generators. The checks on prose are deterministic and were exercised
  on the actual sentences that run produced; the prose those checks will be given next time was
  not regenerated.
- A live embedding model. `PKA_EMBED_MODEL` was never set against a real model here. The vector
  round trip, the similarity floors, the fusion with word matching, the clearing of vectors with
  their snapshot, an unreachable model and a model that fails part way through are all covered
  by tests using a stub embedder. No stated retrieval improvement from embeddings has been
  measured, and none is claimed.
- Graphical browser rendering of the new overview, the walkthrough or the diagrams. The payload
  was checked field by field against everything the browser script reads, the script parses,
  and the diagram geometry was checked by reproducing the browser's own layout arithmetic
  against the real scan: no two boxes overlap, every box falls inside the canvas and every
  arrow not marked as looping runs left to right. None of that is the same as having looked at
  the page, and the appearance of the drawings has not been seen by anybody.

## Not executed in the original 6 October environment

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


