# Task 5.6 — Import coverage and incomplete reads

Connections now shows an **Import coverage** section for GitHub, Jira and Slack. It distinguishes
a completed read within the selected scope, an incomplete read, unknown coverage and a source
that has never been read. Counts of source items and stored excerpts are separate. A successful
empty import reports zero; it does not look like an import that never happened.

## Recorded evidence

- GitHub: files read, skipped, failed and not processed; listed candidates; dependency files
  excluded before listing; grouped skip/failure reasons; truncated file trees with an explicitly
  unknown repository total. Import history retains the individual file report.
- Jira: issues read, comments received before text limits, omitted comments, shortened issue
  text, and issue/page-limit or pagination gaps. Legacy search pagination follows its reported
  total; enhanced search follows page tokens. Missing completeness metadata is shown as unknown.
- Slack: selected/read/failed channels, messages and replies, stored excerpts, and per-channel
  reasons. History limits, missing/repeated cursors, thread limits, failed thread reads and
  additional uncollected reply pages all produce partial coverage.

Import metadata is saved atomically with the source snapshot. The app never infers complete
coverage for older imports that lack this metadata. A new read records it. A failed refresh
retains the preceding saved import and its timestamp, with the latest job failure shown separately.
Confirmed source/credential changes continue to remove obsolete imports and their coverage.
The coverage endpoint performs no remote reads and returns no issue or message text.

Known partial Jira/Slack reads now produce **Completed with gaps** in the shared job banner.
Retry is still explicit. Fixed limits remain in force, so retrying cannot guarantee full coverage.

## API and compatibility

`GET /api/import-coverage` returns per-source summaries, counts, notes and details after the
project has been selected in this app run. Its data comes from recorded scans and source imports.
The MCP Jira begin-read response includes coverage. Slack's existing read tool accepts an
optional `include_coverage` flag; callers using the original list response keep that contract.
No write capability or additional external scope was added.

## Verification

Tests cover page/issue/message/thread boundaries, failed and truncated replies, omitted comments,
shortened issue text, unknown metadata, empty imports, persistence, failed refreshes, project
selection boundaries, and the MCP response contract. Browser checks use the actual app, API and
source adapters with fixture HTTP responses; they do not read or modify live source accounts.
Evidence is stored in `../outputs/task-5-6-2026-10-22/`.

Verified on 22 October 2026:

- **458 Python tests passed**, including 29 new coverage cases. The focused coverage, job and
  source-access run passed 115 tests. One existing Starlette/httpx deprecation warning remains.
- TypeScript and the Vite production build passed.
- **Seven isolated Chrome checks passed** with no page errors: repository omissions; old versus
  unread imports; Jira comments/text gaps; failed refresh retaining the previous import; a
  successful empty read; Slack channel/thread failures; persistence and a 900-pixel layout.
- Restarted the user's idle app and reconnected the same repository. Its 1,099 chunks and two
  source imports stayed intact, as did its zero saved answers/overviews. The new endpoint reports
  the existing partial repository scan and unknown coverage for the two older source imports.
  No new source read was started in the user's saved index.

The evidence folder contains `tests.txt`, `browser-coverage.json`, desktop/narrow screenshots,
and `live-app.json`. Its browser server uses production adapters with fixture HTTP responses.

## Limits

“Read within scope” describes the selected repository/project/channels and content visible to
the connected account at read time. It is not a claim about all organization information or
model answer quality. Source limits are displayed beside coverage. Slack still reads one reply
page per selected thread; Jira still uses embedded comments and bounded issue text. This task
reports these omissions rather than silently broadening the import.

Pagination semantics were checked against the official
[Slack history](https://docs.slack.dev/reference/methods/conversations.history/),
[Slack replies](https://docs.slack.dev/reference/methods/conversations.replies/) and
[Jira issue search](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/)
documentation.
