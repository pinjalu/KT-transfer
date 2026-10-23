# Task 5.4 — Refresh saved information and cached answers

The refresh flow is explicit: refresh repository code in Connections, read the selected Jira
project and Slack channels there, then build the Project overview. Rebuild overview regenerates
the overview from saved information; it does not fetch remote changes. Questions always run
against the current saved snapshot.

## Behavior

- The knowledge revision is stored in SQLite and advances in the same transaction as source
  replacement or invalidation. It survives restarts and rolls back if an import cannot save.
  Multiple Index instances see the same revision, including vocabulary cache changes.
- Starting a repository scan clears previous answers and overviews immediately. Every completed
  scan invalidates derived content, including a scan at the same commit: the files successfully
  read, exclusions and scan limits may have changed. Repository refresh removes external imports;
  the selected Jira project and Slack channels can then be read again.
- Successful Jira and Slack reads replace their previous source text, search entries and vectors,
  and clear answers, overviews and retrieval calibration. Edited text replaces old text; deleted
  issues/messages and successful empty reads cannot leave old evidence behind. Read times and
  reports are saved with the new snapshot.
- A failed or cancelled Jira read preserves its last successful import and timestamp. Slack
  reports partial channel failures and removes content from channels that could not be reread.
  Source access checks still apply before retained data can be used.
- Ask clears old answers when status polling detects a revision change. Overview, architecture
  and the overview's feature listing reload for that revision. Responses from an older in-flight
  request cannot restore old content. Background overview builds continue across page navigation.
- Connections now calls its GitHub-only action **Refresh repository**, with guidance for Jira,
  Slack and overview refreshes. The Slack panel no longer leaves a permanent "Reading" note after
  its background read finishes.

## Verification

Completed 22 October 2026: **409 Python tests passed**, the TypeScript/Vite production build
passed, and **five isolated Chrome checks passed** with no page errors. Live refreshes through
the real MCP connector passed for **four Jira issues and one Slack channel**, followed by a
successful permission recheck. The current index and manual review records were preserved.

Evidence is in `../outputs/task-5-4-2026-10-22/`: `tests.txt`, `browser-refresh.json`,
`overview-refreshed.png`, `connections-refresh.png`, and `live-refresh.json`. The browser and
live-check scripts are retained in that folder for repeatable checks.

Regression coverage includes source edits/deletions, replacement of vectors, answers grounded in
new source text, successful empty reads, transaction rollback after invalidation, revision
persistence, shared database instances, and invalidation before a new scan's network work finishes.
The existing failure, cancellation, partial-import and permission tests remain applicable.

Browser checks use isolated Chrome pages and synthetic API responses. They cover a late old
response during overview/architecture refresh, feature refetch, clearing and replacing an answer,
navigation during a background build, and accurate refresh labels. Live connector checks use a
temporary SQLite backup, keeping the user's current index and manual answer reviews intact.

## Limits

Refresh is manual and bounded by the existing connector read limits. This task does not add
scheduled refresh, remote change subscriptions or automatic overview generation after import.
Open pages detect source revision changes on their status poll (normally within five seconds).
The next overview build still requires Ollama, while source refresh and cache invalidation do not.
