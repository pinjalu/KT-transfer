# Task 6.5 — Fuller Slack threads, edits and deleted messages

Slack imports now follow reply cursors and keep each message's identity, parent thread,
author, edit time and direct link. Use **Connections → Read messages** to refresh the
selected channels, then **Team decisions → Summarize decisions**. The source details show
the parent message's time and any recorded edit time. Connections shows reply-page counts,
edited-message counts and incomplete reads.

## Reading threads

The reader follows both history and reply pagination. Broadcast replies and overlapping pages
are deduplicated by timestamp; a broadcast whose parent is outside the history window causes
that parent thread to be read. Thread messages remain together in timestamp order. Repeated
or missing cursors, malformed responses, missing parents and reply-count gaps are disclosed or
rejected. A failed later reply page does not publish the earlier fragment as a complete thread.

Limits remain explicit: 600 history messages over at most ten pages, 40 threads per channel,
20 pages or 1,000 replies per thread, and 2,000 fetched replies per channel overall. A fixed
limit produces partial coverage. Join/leave events, hidden messages and textless content are
excluded from evidence; attachments are not downloaded. Parents with no text can still lead
to readable replies. A bounded snapshot is not a complete workspace archive.

## Current content and removal

Current message text replaces older edit versions. Defensive handling of changed/deleted
message envelopes never indexes `previous_message` or deletion-marker text. Deleted or hidden
records cannot be resurrected by a duplicate page. No Events API receiver was added: normal
history/reply reads return the current accessible snapshot.

Each imported channel stores a digest of message text, author identity, timestamps, edit
timestamps and thread relationships. Before saved external content is used, the same bounded
channel snapshot is read again through the scoped MCP connector. A mismatch invalidates the
Slack source, search entries, vectors and derived answers, overviews, Jira explanations and
decision summaries. This also catches new replies. The UI asks for a fresh Slack read.
Absent messages may have been deleted, become inaccessible or left the bounded read window;
the app does not assert which occurred.

Confirmed denial or a vanished thread disables the old source. Network/rate-limit failures
and unreliable pagination withhold content without treating the outage as a deletion. A failed
refresh retains the prior snapshot when one exists, subject to those same checks before use.
Successful refresh replaces the source atomically and invalidates derived caches. A stale
in-flight check cannot purge a newer successful refresh. Source changes during generation
prevent the resulting summary from being saved.

Imports from before this task need one fresh read because they have no content digest.
This is request-time revalidation, not a live notification subscription or atomic Slack-wide
transaction. Changes can happen after a check; already displayed text is rechecked on reload,
navigation or returning to the tab. Large channels require more API calls and may hit Slack's
rate limits. Failures remain visible rather than serving unchecked cached evidence.

## Evidence and links

New excerpts represent one message identity each. Long text is split at word/newline boundaries
without loss, retaining metadata on every part. Team decisions reassembles these parts before
its existing bounded model requests. Quoted text that resembles a transcript header cannot
invent a new author or message. Very long partial messages keep conservative status labels.

One read-only `chat.getPermalink` request resolves the actual workspace domain for a channel;
message addresses are then constructed from that domain, channel and exact timestamps. This
works when no workspace name was saved. A failed link lookup is disclosed and does not invent
a link. The MCP tool allowlist and saved channel scope remain unchanged; Slack is never modified.

The Team decisions completion check also tracks the job ID. A fast refresh that finishes
between polls now displays its new result immediately, even if the preceding job also succeeded.

## Verification

The production build, 663 regression tests, 214 final affected checks, eight controlled Chrome
checks and three checks on the real running app passed. Live MCP reads verified the saved
message snapshot and direct links. The initial Ollama timeout recovered on retry, producing
eight saved points. Excel task 6.5 is Done. Details are recorded in [STATUS.md](STATUS.md).
Private fixtures, screenshots, live reports and the pre-activation
database backup are outside the repository in `outputs/task-6-5-2026-10-22/`.

Implementation follows Slack's official [thread pagination](https://docs.slack.dev/reference/methods/conversations.replies/),
[history](https://docs.slack.dev/reference/methods/conversations.history/),
[message edits](https://docs.slack.dev/reference/events/message/message_changed/),
[message deletion](https://docs.slack.dev/reference/events/message/message_deleted/) and
[message permalink](https://docs.slack.dev/reference/methods/chat.getPermalink/) contracts.
