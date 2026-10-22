# Implementation and verification record

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


