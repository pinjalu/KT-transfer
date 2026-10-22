# Task 5.3: Recheck Jira and Slack access before using information

The app checks the saved account and source scope before using imported Jira or Slack content.
Cached overview and feature endpoints use the same check. An answer using external excerpts is
checked again after generation, before it is saved or returned. Overview topics using external
excerpts are checked before generation and before saving the generated section.

## What the checks establish

- Jira authenticates the account, checks every saved issue against the selected project, and
  compares the currently visible issue text with the saved text. This includes imported comments:
  an issue remaining visible does not prove that an earlier restricted comment remains visible.
- Slack probes history access for each imported channel using its saved ID and allowlist.
  The probe message is discarded. Listing a channel alone is not accepted as history access.
- Incomplete or malformed check results block use of saved content. Account/token changes,
  scope changes and removed file-backed credentials also invalidate the affected import.
- A confirmed denial removes that source's indexed text and vectors, plus answers and overviews
  that could contain it. Repository content and the other source's imported text are retained.
- A temporary network, rate-limit or verification failure blocks the response without deleting
  the saved import. Retry once verification works again.
- The Ask screen clears earlier answers and excerpts when verification fails. The React and
  legacy overview screens hide cached content on failed checks. Source revisions also clear
  previously displayed answers.

Jira's comparison deliberately requires **Read issues** again when the visible snapshot changes,
including ordinary edits. It does not attempt to infer whether a missing comment was deleted,
restricted or changed. This conservative behavior prevents the old text being used. It does not
automatically import changed content.

The provider behavior is documented in Atlassian's [issue search API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/)
and [comment API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/),
and Slack's [history API](https://docs.slack.dev/reference/methods/conversations.history/).

## Repeat the live check

From the project directory, using the application's Python environment:

```powershell
python -m pka.access_check --output data/acceptance/access.json
```

This runs the production service's access checks through the real MCP connector on a temporary
SQLite backup. It opens the original index read-only, never refreshes or purges that index,
and deletes the temporary copy afterward. It does not revoke credentials, change memberships,
write remote content, invoke Ollama or export source text. The report contains counts, times
and a result code. Both Jira and Slack must have imported content for the task-level check.

## Verification on 22 October 2026

The live check passed at 12:28:25 IST for **four saved Jira issues and one Slack channel**.
See the [live report](../../outputs/task-5-3-2026-10-22/live-access.json).
The running app's cached overview was also checked after restarting with the implementation;
its result is recorded in [the app check](../../outputs/task-5-3-2026-10-22/live-app.json).

Automated tests cover issue-level denial, changed comment visibility, invalid scope, incomplete
check results, Slack history denial, temporary failures, credentials removed or changed, source
changes during generation, cached views, and preservation of the original database by the live
checker. Remote denial is simulated in these tests; the user's accounts were not modified to
force a real revocation.

Six isolated Chrome checks passed with no page errors. They used synthetic API responses to
verify answer/source removal for denial, transient verification failure and stale content,
revision-based clearing, and hiding cached overviews in both interfaces. The user's browser
tabs and credentials were not changed. See [browser results](../../outputs/task-5-3-2026-10-22/browser-access.json)
and the [blocked-answer screenshot](../../outputs/task-5-3-2026-10-22/browser-access-blocked.png).
The frontend TypeScript/Vite build passed. The final full Python suite passed **404 tests**
with the existing Starlette/httpx deprecation warning. See [the test output](../../outputs/task-5-3-2026-10-22/tests.txt).

## Limits

These are checks at request and publication time, not a push subscription to remote permission
events. A provider can change access after a check; an already displayed screen is cleared when
the app detects the change. Slack checks channel history permission, not whether every saved
message has since been edited or deleted. Refreshing source contents is separate work under
task 5.4. This remains a local, single-account application, not per-user enterprise authorization.
