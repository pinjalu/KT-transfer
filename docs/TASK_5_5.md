# Task 5.5 — Background jobs, cancellation and retries

Repository scans, Jira reads, Slack reads and overview builds now have saved job records.
The shared banner shows the current job on every React page, with progress and **Cancel job**
or **Retry job** when applicable. Page navigation or browser reload does not start another job.
Starting or updating a job refreshes the shared controls immediately; polling keeps them current
while the worker runs.

## Lifecycle

- A start request reserves one job immediately, before its worker is scheduled. Duplicate starts
  are refused while any job or answer is busy. Every run has an ID and an attempt number.
- States distinguish queued, running, cancelling, completed, partial, failed, cancelled and
  interrupted work. Scan failures and partial Slack imports are reflected in the job result.
  Overview sections that could not be built produce a partial result.
- Cancellation targets a specific job ID. A cancellation requested before a queued worker starts
  is retained and does not touch the snapshot. During a connector or model request, the banner
  shows Cancelling until that request returns and a safe checkpoint is reached. Cancelled external
  imports preserve their last successful snapshot; a cancelled scan disables its incomplete index.
  A cancelled overview never publishes the model response that was still in flight.
- **Retry job** is explicit and starts a new attempt using the current saved source information.
  It is available for failed, partial, cancelled and interrupted work. Completed jobs cannot be
  retried through this control. A stale job ID or changed project/source selection is refused;
  use Connections to start a new read for a changed selection.
- Job results persist in SQLite, with up to 30 recent records retained. After an app restart,
  unfinished jobs become Interrupted and wait for an explicit retry. They do not automatically
  run again. Source content, questions and credentials are not copied into job records.
- Existing bounded connector retries for temporary HTTP/network errors remain in place. There
  is no new automatic loop that reruns an entire scan, source import or overview build.

## API

Existing start endpoints return `job_id`. `GET /api/status` adds a `job` object with state,
progress, attempt, timestamps and available actions. `POST /api/jobs/{id}/cancel` and
`POST /api/jobs/{id}/retry` reject stale IDs and enforce the same single-job rule. The original
`POST /api/scan/cancel` remains a compatibility action for the current repository scan.

## Verification

Focused tests cover all four job kinds cancelling while queued or during a request, safe source
retention, retry attempts, stale IDs, duplicate requests, partial Slack recovery, interrupted
startup recovery, changed scopes, embedding cancellation and bounded job history. Browser checks
use the real local API and UI with delayed fixture connectors and a fixture model, so remote
accounts and the user's saved index are untouched.

Verified on 22 October 2026:

- `python -m pytest -q`: **429 passed**, including 20 job lifecycle cases; one existing
  Starlette/httpx deprecation warning.
- Frontend TypeScript and Vite production build: passed after the final shared-status update.
- Five Chrome checks: scan navigation/cancel/retry; failed Jira read surviving reload and
  succeeding on retry; Slack cancel/retry; overview retaining its job ID across reload and
  navigation, then cancelling from Architecture; job controls fitting at 768 pixels.
  All six cancel/retry requests returned HTTP 200; no browser page errors were recorded.
- Restarted the real app at `127.0.0.1:8000`, reconnected the same repository and checked the
  new job API. Saved counts stayed at 1,099 chunks, two source imports, zero answers and zero
  overviews. No source import or model build was started in the user's index during this check.

Local evidence is under `../outputs/task-5-5-2026-10-22/`: `tests.txt`, `browser-jobs.json`,
desktop/narrow screenshots and `live-app.json`. Browser scripts there use a disposable SQLite
database on port 8001 with delayed fixture connectors and model responses.

## Limits

Jobs run inside this local app process; they are not distributed workers. Cancellation is
cooperative and may wait for the current request's timeout. Task 7.2 now reuses completed GitHub
and local file reads on retry; see [incremental imports](TASK_7_2.md). Jira/Slack connector pages
and model generation still start again. The shared controls belong
to the React interface; the legacy page retains its repository-scan cancellation action.
