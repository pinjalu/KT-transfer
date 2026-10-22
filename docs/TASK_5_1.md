# Task 5.1: Test live GitHub, Jira and Slack connections

Status: **Done** for the scoped live connection checks. GitHub, Jira and Slack passed together,
and Jira's browser import indexed four issues from the selected project.

Run from the project folder with the Python environment used by the application:

```powershell
python -m pka.acceptance
python -m pka.acceptance --source jira
python -m pka.acceptance --output data/acceptance/connections.json
```

The command loads the existing repository, branch, Jira project and Slack channel selection
from the local SQLite database in read-only mode. It uses the saved credentials and the same
MCP client/server as the app. It never changes a remote source, modifies the saved index,
changes the selection or sends content to a model.

Each service has an independent timeout (180 seconds by default, configurable from 5 to 600)
and result. One failed service does not skip the others. The report keeps check names, counts,
the GitHub commit and selected Slack channel IDs. It omits credentials, account identities,
source text, message text, issue text and upstream error bodies.

## Acceptance checks

- MCP exposes only the expected read-only tool set.
- GitHub resolves the selected repository and branch, enumerates a commit-pinned manifest,
  and reads one non-empty supported file whose blob matches the manifest. At most three
  candidate files are sampled. This is not a complete repository scan.
- Jira authenticates, lists the selected project, reads its issues within the connector's
  limits, validates their project keys and source URLs, reconciles paged block counts and
  rechecks access to those issues.
- Slack lists the selected channels and reads their history without adding other channels.
  Returned message timestamps and text are validated. If the workspace name is saved,
  message links are constructed and checked locally; their destination pages are not opened.

Missing setup is `blocked`; a service failure is `failed`; accessible sources with no readable
content are `incomplete`. Only three passing service results set `task_complete` to true.
A successful single-service retry cannot complete the full task. Exit code 0 means the
requested checks passed; 1 means the checks or report write failed; 2 is a command usage error.

## Live run on 22 October 2026

The final run finished at 10:29:12 IST with `task_complete: true`. Evidence is in
[`live-connections-final.json`](../../outputs/task-5-1-2026-10-22/live-connections-final.json).

| Service | Result | Evidence |
|---|---|---|
| GitHub | Passed | 12 read-only MCP tools; 64 manifest entries; one pinned file read, 3,686 bytes |
| Jira | Passed | Authenticated; selected project visible; 4 issues read, source URLs checked and issue access rechecked |
| Slack | Passed | Selected channel visible; 2 readable messages; no thread replies in the returned sample |

Earlier runs failed at Jira authentication. After saving the replacement API token through
the app's credential storage function, the Jira-only check and the final all-service run
passed. The saved site and email were unchanged.

The Slack workspace name is empty in the saved selection, so message-link construction was
not exercised. A successful bounded history read does not prove complete thread pagination
or complete channel history.

## Optional follow-up

Save the Slack workspace name if message links are required, then rerun the Slack check.
The missing workspace name does not prevent the selected channel's connection and read checks.

The new runner tests use stubs and the real MCP subprocess in explicit example mode; they
exercise reporting, scope checks, error handling, timeouts and index preservation. They are
separate from the live evidence above.

## Browser verification on 22 October 2026

Tested the actual local app at `http://127.0.0.1:8000/connections` in installed Google Chrome,
with a visible test window. Reconnecting the saved repository restored its existing scan.
The Slack **Read messages** action completed over the real HTTP/MCP path and the last-read
timestamp updated. After the token replacement, Jira listed the selected SCRUM project.
Clicking **Read issues** imported four issues and updated the last-read timestamp at
10:29:56 IST, with no page errors. See
[`browser-jira-live.json`](../../outputs/task-5-1-2026-10-22/browser-jira-live.json).

Browser testing found two defects: the Connections screen lacked fields for replacing Jira
credentials, and the saved-project reminder pushed repository fields beyond the card edge.
The Jira panel now offers a masked-token form that sends only changed fields to the existing
credential endpoint. Success and Cancel clear the entered values. Saving refreshes project
access. The reminder now spans its own grid row, with fields fitting at 1440px and 1024px.

Six UI regression checks passed with no page errors. Credential save requests were intercepted
with test responses, so the test values did not replace real credentials. See
[`browser-check-results.json`](../../outputs/task-5-1-2026-10-22/browser-check-results.json).
The frontend TypeScript check and production build passed. The Python baseline passed 309
tests, and the added acceptance suite passed 16 tests, including two real MCP subprocess
checks using explicit example data. A targeted rerun of the credential handling tests passed
20 tests. The obsolete Jira warning about never having exercised live issue reads was removed
after the successful browser import.

A later browser check caught a stale "Reading issues" note after import completion. Jira's
progress message now follows the actual background-job state. A real Chrome import verified
that progress appears while reading and disappears when the last-read timestamp updates,
with no page errors. The TypeScript check and production build passed again. Evidence:
[`browser-jira-progress.json`](../../outputs/task-5-1-2026-10-22/browser-jira-progress.json).
