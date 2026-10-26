# Project plan

The product helps a developer understand a project and investigate tasks with less dependence on experienced colleagues. All connectors must be explicitly scoped and read-only. Advance only after the previous stage has passed its acceptance checks.

Current state, 22 October 2026: source reading, overview, Ask, architecture, background jobs
and coverage are implemented. Live scoped connector checks have passed. Human answer-quality
acceptance remains separate. See [task 5.8](TASK_5_8.md) for current evidence and open gates;
the stage descriptions below retain the broader product acceptance goals.

## Stage 1 — implemented; live acceptance passed on 6 October 2026

One GitHub repository and branch; commit-pinned scans; a real MCP client/server; bounded, path-aware text chunks; local lexical search; plain-English Ollama answers; inspectable sources; scan coverage and failures; freshness checks; manual feedback; a browser interface and Windows instructions.

Acceptance gate: install on the target Windows/Python 3.10 environment, scan the chosen repository, verify the commit and line links, ask known questions using the real Ollama model, and test an expired/revoked token. Fixture and protocol checks are included. Do not treat fixture results as live model accuracy.

## Stage 2 — beginner-friendly overview, implemented; revised 8 October 2026

Build an overview workflow from evidence about purpose, technologies, modules, documented setup/startup, important flows and suggested reading order. Gather evidence separately for each topic, cite sources and expose missing information. Do not infer business goals from names alone. Cache by commit and invalidate after refresh. Do not claim repository-wide understanding from a few excerpts.

Acceptance: a developer can follow only documented setup instructions, find important entry points, inspect every reference and see which overview sections lack evidence. Confirm that collected instructions are presented as documentation, never executed automatically.

The revision separates what can be read from what has to be explained. Anything a file states
outright, meaning the declared dependencies, the route declarations, the defined commands, the
tables and data shapes, the names of the settings read from the environment and the documents
the project ships, is now read out of the indexed text and shown with the file and line it came
from, because asking a small model to report a fact that is written down invites it to get the
fact wrong. The model keeps only the prose, split across more and narrower topics, and what it
returns is checked for repetition, for citations that point at everything at once, and for
statements that cannot be found in the excerpt they name. Every citation, every fact and every
entry in the reading order links to the source at the scanned commit.

It is also presented as a handover rather than a report. The overview had become complete and
still gone unread, so it now runs one step at a time in the order somebody would actually
explain the project: what it is, its shape, what uses what, getting it running, one request
followed through, and the reading order last. Three diagrams carry the parts a picture tells
faster than a paragraph, and they are derived from imports, routes and paths rather than
described, so an arrow is evidence of a line in a file.

The rendered overview and navigation have now been exercised in Chrome. Remaining product
validation includes a second real repository and a developer unfamiliar with the project
using the walkthrough. These usability and model-quality judgments are separate from passing
technical checks.

## Stage 3 — Jira explanations and related sources implemented within documented scope

The adapter reads one selected Jira project through scoped MCP tools. Credentials, pagination,
bounded descriptions/comments, custom text field names, updates, access checks and coverage
are implemented. Selected task explanations and evidence-backed related files/discussions are
available; see [task 6.2](TASK_6_2.md) and [task 6.3](TASK_6_3.md). Requirement implementation
verification and specialized non-text field mapping remain incomplete. Channel-level Slack
summaries are available through [task 6.4](TASK_6_4.md), within the limits below.

For a selected issue, explain the request, requirements, related code/documents, recorded discussions/decisions, investigation areas and open questions. Establish confirmed relationships through explicit issue keys, URLs and recorded links. Label lexical or semantic similarity as a possible connection, not a confirmed relationship. Preserve issue keys, timestamps and URLs in the index.

Acceptance: a known ticket produces a traceable report; unrelated projects never enter the index or answers; missing custom fields and uncertain matches remain visible; no issue is created or changed.

## Stage 4 — Slack decision context, reading and cited summaries implemented

Task 6.4 provides saved channel summaries with exact quotes, recorded authors/timestamps,
source links, conservative decision/proposal/historical/unclear labels and possible conflicts.
All substantive imported passages are read in bounded background requests. Current channel
access is rechecked; source changes invalidate summaries. Labels describe recorded wording,
not verified current policy. See [task 6.4](TASK_6_4.md). Task 6.5 adds bounded thread pagination,
message-level evidence and edit/deletion-sensitive content checks. Changed or absent content
invalidates derived caches; transient failures withhold unchecked results. Full archives and
live event subscriptions are outside this scope. See [task 6.5](TASK_6_5.md).

Replace the disabled Slack placeholder. Require an explicit channel allowlist and a connection authorised to read those channels. Read relevant messages and thread replies with cursors, timestamps and permalinks. Account for channel membership changes, deleted/edited messages, retention limits, API restrictions and token revocation. Do not silently add channels or direct messages.

Distinguish a proposal from an agreed decision. Preserve conflicting evidence and identify who said what and when only when the source records it. Implement refresh/tombstone handling so removed or newly inaccessible content is excluded from both retrieval and answers, including any stored answer caches.

Acceptance: a real recorded decision is distinguishable from an unanswered suggestion, linked threads are complete within disclosed permissions/limits, and deletion/revocation tests prevent obsolete content from being returned.

## Later improvements — evidence-led

Evaluate ordinary-language questions first. The comparison between word matching and a small
local embedding model is now available to run rather than still to be built: `pka/embed.py` sits
behind the retrieval interface as the plan required, is off unless `PKA_EMBED_MODEL` names a
model, and adds its candidates to the existing ranking instead of replacing it. Nothing has been
measured yet, so nothing is claimed. The comparison worth running is the same one this plan
already described: a set of human-labelled questions, scored for source relevance and answer
quality separately, with the setting on and off. Until that exists, leaving it off is the
honest default.

Measure source relevance and answer quality separately using human-labelled cases; never substitute a model confidence score for accuracy. The overview's per-statement support measure is a
retrieval-side check on whether a sentence appears in the excerpt it cites, not a judgement of
whether the sentence is true, and it must not be reported as an accuracy score.

Task 7.2 implements incremental/resumable GitHub and local file reads, with current access and
content-hash checks; see [task 7.2](TASK_7_2.md). Scheduled refresh and incremental Jira/Slack reads
remain outside that scope. Consider import/call-graph expansion, language-specific parsers,
persistent evaluation history without retained restricted excerpts, or a larger local model only
when an observed limitation justifies the additional cost.

## Gate before multiple users

Task 6.6 provides password authentication and server-side sessions for one local owner. See
[task 6.6](TASK_6_6.md). Per-user and per-source permission checks, credential isolation,
permission-filtered search, audit records and adversarial cross-user tests remain. A shared
index must not return another user's restricted snippets or an answer derived from them.
Keep the single-user application local until that work is complete.
