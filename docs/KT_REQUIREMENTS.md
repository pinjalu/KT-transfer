# The KT requirements, and where this project stands against them

A requirements document was handed over describing an AI system that reads every authorised
source about a project, understands it from both a business and a technical angle, and teaches
it to a new developer with project-specific real-life examples backed by evidence.

This file is the honest map between that document and what is built. It exists because the gap
is large in one specific direction, and anybody comparing the two needs to know where without
reading both end to end.

## The one thing that limits everything else

The document names fourteen sources: source code, Git repository, Jira, pull requests,
documentation, chat, database, APIs, third-party applications, CI/CD, deployment, logs,
monitoring and tests.

Three are connected: GitHub files at one commit on one branch, Jira issues for one project,
and Slack messages from an allowlist of channels. Documentation, APIs and tests are covered
only in the sense that those live inside the files, which is a real answer to "what does the
code say" and no answer at all to "what happened when it ran".

Nothing can be said about pull requests, commit history, pipeline runs, running deployments,
log output, monitoring data, live database contents, or how an outside service behaves in
practice. The overview now says exactly that, by name, in the group "What this cannot tell
you", along with what was checked for the scan. That is the honest form of a gap. Silence is
not, because silence reads as "there is nothing here".

## Where each requirement stands

| Section | State | Where |
|---|---|---|
| 1 Project-first understanding | Partly. One connected index across code, Jira and Slack. Eleven of the fourteen sources are absent. | `pka/index.py` |
| 2 Understand before explaining | Partly. The facts and diagrams are read before any prose is written, and the prose only ever sees retrieved excerpts. | `pka/facts.py`, `pka/diagram.py` |
| 3 Real-life example from the project | Yes for the request path, drawn rather than described. The prose is asked for a scenario and a 1.7B model is not reliable at it. | request journey in `pka/diagram.py` |
| 4 Simple language | Yes. | the system prompt, every `plain` line |
| 5 Business plus technical | Partly. The topics ask for both. Business intent is only recoverable where a readme or a ticket states it, and is never inferred from names. | `pka/overview.py` |
| 6 End-to-end flow | Yes for one request through the real files. Not per feature, because nothing records what a feature is. | request journey |
| 7 Real-life story format | Partly. The walkthrough is ordered as a handover. The ten-step purchase story needs a feature concept the scan does not have. | STEPS in `pka/overview.py` |
| 8 Code connected to functionality | Yes. Each card says what the file is for and what it answers or declares. | `pka/roles.py` |
| 9 File explanation format | Yes, and exact. Used by and Uses come from the import lines with their line numbers. | `pka/roles.py` |
| 10 Jira plus code plus business | Partly. Jira issues sit in the same index and are searched beside the code, and issue keys stay whole so one can be asked for by name. Tracing a ticket to the commit that closed it needs commits, which are not read. | `pka/index.py`, `pka/connectors/jira.py` |
| 11 Chat and technical decisions | Partly. Slack is indexed and the decisions topic is asked to keep a proposal apart from an agreement. Marking a decision outdated against current code is not automated. | decisions topic |
| 12 Third-party explanation | Mostly. Which service, what for, and the line that reaches for it. Failure behaviour and the test environment are not derivable from a static read. | `pka/facts.py` services |
| 13 Database explanation | Partly. Tables, models and engines with their lines. Relationships between tables are not extracted and no row is ever read. | `pka/facts.py` stores |
| 14 API explanation | Partly. Every route with its method, path and declaring line. Input and output shapes are not extracted. | `pka/facts.py` routes |
| 15 Error explanation | No. | |
| 16 Test case explanation | Partly. Test files are found and each card says whether a test imports that file. Why a given test matters is not explained. | `pka/roles.py` |
| 17 Negative scenarios | No. | |
| 18 Deployment explanation | Partly. Container, pipeline and hosting files are listed as files. No run, no release, no live version. | `pka/facts.py` delivery |
| 19 Troubleshooting | No. | |
| 20 Beginner mode | Yes. | `MODE_SHOWS` in `pka/static/app.js` |
| 21 Developer mode | Yes. | same |
| 22 Architect mode | Yes. | same |
| 23 What, why, how | Partly. The topic prompts ask in that order; a small model follows it unevenly. | `pka/overview.py` |
| 24 Relevance rule | Yes, and enforced rather than requested. A statement naming nothing from this project is marked in the interface. | `project_names` in `pka/overview.py` |
| 25 Evidence-based | Yes. Every statement, fact, diagram box and reading-order entry opens its source at the scanned commit. | throughout |
| 26 Unknown information | Yes. Named, with what was checked. | `gaps` in `pka/facts.py` |
| 27 KT section structure | Partly. The walkthrough covers what it is, why, project specifics, flow, code, storage, third party, testing, evidence and gaps. Common problems are absent. | STEPS |
| 28 Senior developer teaching | Partly. The order and the diagrams are there. The teaching voice depends on the model, and on a 1.7B model it is the weakest part of the page. | |
| 29 Continuously maintained | No. Refresh is manual and the overview is rebuilt against a commit. | `docs/ROADMAP.md` |

## What is enforced rather than asked for

Four things in the document are rules a model is told to follow. Telling a 1.7B model to
follow a rule does not make it follow one, so each is checked after the fact and the result is
shown to the reader.

Section 24, relevance: a statement is compared against the names this scan knows, meaning the
paths of its excerpts and every dependency, route, table and setting already found. One that
names none of them, and carries no path, route or identifier either, is marked as not being
about this project.

Section 25, evidence: a statement is compared against the excerpts it cites, and one whose
content cannot be found there is marked for checking with the excerpt underneath it.

A citation naming every supplied excerpt at once is narrowed to the ones whose text carries
the wording, and a statement restating an earlier one is dropped before anybody reads it.

## The two things most worth doing next

Neither is a presentation problem, which is why neither appears above as a near miss.

A feature concept. Most of what is still missing, meaning the per-feature story, the happy and
failure and edge paths, and the troubleshooting entries, hangs off knowing what a feature is.
A route, the files reached from it, the table it writes and the ticket that asked for it are
already known separately. Grouping them under one name is the step that has not been taken.

A larger local model. The relevance check, the repetition check and the support check are all
compensating for a 1.7B model, and compensating is not fixing. The facts and the diagrams are
already at the standard the document asks for, because no model touches them. The prose is
not, and the cheapest way to move it is `OLLAMA_MODEL`.
