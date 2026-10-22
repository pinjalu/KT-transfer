# Task 6.3 — Link tasks, project files and discussions

Implemented 22 October 2026. Open **Jira tasks**, select an imported issue, then click
**Related files and discussions**. File and Slack panels load independently of the task's
Ollama explanation. Refresh links rechecks access and recomputes results; no external source
is changed and no model call or background job is started.

## Relationship rules and evidence

- **Confirmed link:** a target excerpt names the exact selected issue key or canonical Jira
  URL; alternatively, the Jira text names an exact indexed file path, a file URL in the selected
  repository at the scanned commit/current branch, or the stored Slack excerpt permalink.
  Foreign repository/site URLs, similarly prefixed keys and path suffixes do not confirm links.
- **Possible connection:** at least two meaningful whole words overlap after administrative
  metadata, common English terms and generic code vocabulary are removed. The matched words are displayed. This is a lexical
  suggestion, not a semantic confidence score or a verified relationship.
- Each file appears once with its strongest matching excerpt. File URLs include the scanned
  commit and excerpt line numbers. Forward references retain the Jira quote as well as target
  context. Excerpts are bounded to 1,400 characters around the match; large results are paged
  ten at a time (API maximum 25). Counts cover the entire imported scope.
- Slack cards retain recorded message timestamps/authors and use the stored excerpt's first
  message permalink. The matching message may appear later in that excerpt. The UI explicitly
  discloses this limit and never labels a discussion as an agreed decision.

An explicit reference can itself be outdated or wrong; a confirmed link establishes only
that the reference was recorded. Neither category verifies that requested work is implemented.
No match means none was found in the imported content, not that none exists elsewhere.

## Scope, freshness and failure behavior

`GET /api/jira/tasks/{key}/links?kind=files|discussions&offset=0&limit=10` is restricted to the
selected Jira project and active repository snapshot. File lookup checks the current GitHub
head/access and Jira issue visibility; discussion lookup checks Jira and selected Slack channels.
Scope, credentials and knowledge revision are checked before publishing results. Changed source
identity or confirmed revocation invalidates affected saved content; a temporary connection
failure hides that panel's unverified result. A Slack outage leaves Jira detail and file lookup
available. Changed repository heads require a new scan. Responses are private and not cached.

No arbitrary URL is fetched. File paths must already be indexed; Slack content comes only from
selected imported channels. Coverage and read times accompany both panels. Missing Slack imports
give a Connections action. Selection/revision changes discard old responses and reset pagination.
Returning to the browser tab rechecks access. Source refresh recomputes links without a derived
relationship cache. A read-only panel does not queue another explanation when navigating.

## Verification

- Production TypeScript/Vite build passed.
- 561 regression tests and 74 final focused relationship/task-explanation checks passed.
  Coverage includes reference boundaries, foreign and malformed URLs, forward evidence,
  metadata exclusion, long excerpts, deduplication/pagination, scope, access revocation,
  concurrent source/identity changes, source outages, refreshes and API validation.
  The final common-word filter was checked again after the regression run; generic language
  such as "all", "under", "off" and "function" cannot create a possible match by itself.
- Eleven controlled Chrome checks passed with no page errors: evidence and labels, pagination,
  task switching, empty results, stored discussion links, inert source markup, independent
  source failures, navigation/reload, 900-pixel layout, revocation and refreshed imports.
- Read-only real GitHub/Jira/Slack checks passed on a disposable copy of the saved database:
  six Jira tasks, both relationship kinds, 57 imported repository files and one Slack excerpt.
  These records yielded possible connections or no links; no confirmed relationship was
  invented. Repository coverage was partial and Slack coverage unknown, both displayed.
- The running local app was restarted only while idle; existing imports and the saved task
  explanation were retained. Three additional Chrome checks on the real app passed: task/empty
  states, possible matches with coverage and evidence, and navigation/reload without another
  explanation job. Browser and live artifacts stay outside the repository under
  `outputs/task-6-3-2026-10-22/` to avoid committing private source content.

Task 6.4 covers decision summarization. Task 6.5 covers fuller Slack threads, edits and deletions.
This task does not add semantic retrieval, commit/PR history, requirement completion checks,
per-message permalink reconstruction or broader channel access.
