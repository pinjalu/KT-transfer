# Task 6.4 — Summarise Slack decisions with sources

This record describes the original task 6.4 delivery. [Task 6.5](TASK_6_5.md) subsequently adds
thread pagination, message metadata/permalinks and checks for changed or removed source text.
[Task 15.3](TASK_15_3.md) strengthens status and conflict checks and adds a source-wording
comparison across model batches. Its rules supersede the original conflict criteria below.

Open **Team decisions**, choose an imported Slack channel and click **Summarize decisions**.
The screen shows concise points, supporting quotes and full imported passages. The shared job
banner keeps generation visible when navigating to other screens; cancellation, retry and
restart recovery follow the existing background-job lifecycle. Saved summaries survive reload.

## Evidence and recorded status

Each model point must provide known passage IDs and one matching quote for each ID. Quotes
are constrained to supplied source wording and independently checked against the cited passage.
Unknown references, invented quotes and malformed responses withhold the entire new summary.
An earlier valid summary remains available after a failed generation, explicitly labeled.

Status is conservatively derived from the full imported message's wording:

- **Recorded decision:** explicit adoption/agreement wording with a stated object. Questions,
  conditions, pending approval and negated agreement do not qualify. A deliberate negative
  choice, such as deciding not to use a product, is preserved.
- **Proposal:** suggestion or recommendation wording without an unqualified adoption cue.
- **Historical context:** wording describing a former, superseded or withdrawn choice.
- **Possible conflict:** a model suggestion backed by two distinct complete messages with
  different text. Both positions remain inspectable; the assistant does not resolve them.
- **Unclear decision status:** context lacking sufficient evidence for a stronger label,
  including partial messages. Vague assent alone is not treated as agreement.

When the generated category disagrees with the supported label, or its summary omits a literal
name/version/number in the supporting quote, the exact quote is displayed as source wording.
Unrelated values elsewhere in a long message do not force the whole message into the summary.
Greeting-only passages stay available as evidence but are omitted from model requests and points.
These checks establish source traceability, not complete semantic correctness or approval
authority. The user should review the evidence before treating a point as current team policy.

## Input scope and limits

Only the chosen imported channel is summarized. Current Slack access is checked before reading
and before publishing; Jira and GitHub requests are unnecessary for this Slack-only view.
Credential, channel-selection and knowledge-revision changes invalidate the cached summary.
Confirmed access denial removes affected imported content and derived summaries. A transient
access failure withholds content without deleting the cache. Results use private, no-store APIs.

The saved transcript is divided at its recorded message headers. Long messages are split into
at most 6,000-character passages, preferably at newline/word boundaries, with no source text
discarded. Such passages are explicitly partial and cannot establish a recorded decision.
All substantive passages are read in bounded model requests. Each part produces up to eight
summary points; repeated points retain their combined evidence. The UI filters statuses and
paginates long summaries. Summaries can omit details and cross-part conflicts may not be found.

Author identifiers and timestamps are shown as recorded in the imported transcript. No user
profile lookup or invented display name is added. Stored Slack links open the first message
of an imported excerpt; the matching passage may occur later. Missing links remain explicit.
No arbitrary URL is fetched, and no Slack message is sent or changed.

Coverage and read times remain visible. This task uses the existing Slack snapshot: live access
checks verify history permission, not whether every saved message was edited/deleted after
import. A source refresh invalidates summaries. Fuller thread reconstruction, edit/deletion
handling and message-level permalink improvements remain task 6.5. English wording rules are
conservative; unsupported wording stays unclear rather than claiming a complete classifier.

## Implementation

`pka/decisions.py` contains passage preparation, structured generation and evidence/status
checks. `decision_summaries` stores results against the current knowledge revision. The
`decisions` background job keeps its selected channel as its target and rejects stale retries.
Read-only GETs never start generation:

- `GET /api/decisions/channels`
- `GET /api/decisions/channels/{channel_id}`
- `POST /api/decisions/channels/{channel_id}/summarize`

## Verification, 22 October 2026

- Production frontend build passed.
- All 614 Python regression tests passed; 108 final focused checks also passed.
- Twelve controlled Chrome checks covered empty imports, evidence/status labels, inert markup,
  navigation during generation, saved reloads, channel selection, cancellation/retry, failed
  refresh, pagination, narrow layout, import invalidation and revoked access.
- A real read-only Slack/Ollama run read three passages in two parts with qwen3:1.7b. Eight
  points passed quote/citation checks. The live app was then restarted and generated its own
  saved summary of nine points while preserving existing imported data and the Jira explanation.
  The long pasted conversation remained unclear, rather than being presented as team agreement.
- Three Chrome checks on the running app confirmed saved points/model/evidence and navigation
  through Jira tasks and reload, with no generation requests or page errors. The imported block
  lacks a saved permalink; this is disclosed beside the evidence rather than inventing a link.
- Excel task 6.4 was marked Done, with other cells and workbook features preserved.

Private live outputs and browser artifacts remain outside the repository under
`outputs/task-6-4-2026-10-22/`. These checks are technical verification, not human approval of
every model summary. Fuller Slack thread, edit and deletion handling is still task 6.5.
