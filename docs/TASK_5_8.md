# Task 5.8: Final acceptance and documentation

Recorded 22 October 2026. Status: **Done for technical acceptance and documentation of the
current single-user local prototype**. The user delegated the answer corrections and review
to the coding agent. That review is recorded as agent review; the separate human correctness
and source-sufficiency measurement in task 5.2 remains open. No human ratings were invented.

## Scope and documentation

The Windows startup guide now describes the current Connections, overview, Ask and
Architecture flows, credential options, import coverage, background jobs, cancellation,
retry and diagnostics. README, environment-setting comments, BUILD_PLAN, ROADMAP and STATUS
distinguish current capabilities from dated acceptance records.

Home, Connections, Project overview, Ask assistant and Architecture have implemented views.
Feature explorer, Jira tasks, Team decisions, Troubleshooting and Settings remain explicitly
labelled planned screens. Importing Jira issues or Slack messages does not implement those
dedicated analysis screens. The original interface remains at `/legacy`.

## Checks and retained evidence

Evidence is local in `../../outputs/task-5-8-2026-10-22/`. It is not included in the Git
repository. Model answers and source excerpts stay local, including the review page.

| Check | Result and boundary |
|---|---|
| Python suite | 463 tests passed after the combined-answer and indexed-scope corrections. After the final prompt/citation-schema changes, all 37 affected tests passed, including two new citation-schema cases. One Starlette/httpx deprecation warning. |
| Frontend | TypeScript and Vite production build passed; final build includes the corrected source-scope label. |
| HTTP/MCP smoke | Passed: three fixture files read, one excluded, cited answer and feedback saved. Real app/server/subprocess transport, simulated source data and answer. |
| GitHub/Jira/Slack acceptance | All three scoped live checks passed with saved credentials. No remote content was changed. |
| Live source refresh | Four Jira issues and one Slack channel (two messages, one indexed block) reread in an isolated database. Both imports reported complete within configured scope. |
| Saved-source access | Read-only check passed for the four Jira issues and one Slack channel. Real permission revocation was not performed. |
| Initial answer run | Nine of nine automatic checks passed on `qwen3:1.7b`. The run is preserved in `answers.json`; it is not a factual-accuracy score. |
| Latest answer cases | All nine latest cases pass their automatic checks, combining the final nine-case run with a three-case multipart rerun. `answers-reviewed.json` identifies both reports and retains the exact response hashes. |
| Chrome walkthrough | Seven checks passed with no page errors: scan/coverage, partial overview and reload, question/source/feedback, 1024-pixel layout, architecture, planned-screen labels and import logs. Fixture data/model, real app and MCP. |
| Original app data | Preserved: 1,099 chunks, two source imports, zero saved answers and zero overviews at the start of acceptance. |

The live evaluation uses `pinjalu/BSA_chatbot` at commit
`0cc9ce981956e6e3c352836e8112a06700360947`, saved scan 28 (partial: 57 files read,
seven skipped). It does not claim a fresh or complete GitHub snapshot. Live source imports
and evaluation ran through a separate local app on a database copy, preserving the user's
working app. `review.sqlite3` retains the exact answers with report hashes.

Target environment: Windows 11, Python 3.12.14 and Ollama `qwen3:1.7b`.

The final app on port 8000 was restarted and reconnected, ready and idle, with the original
data counts preserved. Temporary acceptance servers were stopped; review evidence remains
in the output directory.

## Corrections found during acceptance

The smoke runner previously treated a saved complete scan as proof that its worker had
released the job slot. An immediate question could receive HTTP 409. It now waits for an
idle, ready app, rejects failed scans and validates the answer HTTP response. On Windows,
cleanup stops the runner's own process tree so the venv launcher cannot leave a server
holding temporary files open. Two regression tests cover completion-before-idle and failure.

Agent inspection of the first live answer run found a repeated port in the startup response
and repeated audience in the purpose response. Factual lookups now receive concise output
instructions, and the question follows the untrusted excerpts so the model finishes reading
with the specific request. Single-fact questions use one statement; multipart questions keep
room for distinct facts. Forcing every lookup into one sentence dropped the requested database
driver in a live check, so that restriction was rejected. Broader explanations retain up to
four statements and can report partial evidence. These changes contain no project-specific
answer values and do not modify model weights. Regression tests cover multipart lookups and
preserve the broader explanation behavior.

One intermediate unavailable-cost response invented a source ID and was withheld by the
existing validator. The generation schema now enumerates only the actual supplied source
IDs for both focused and explanatory answers. Post-generation validation still rejects any
unknown ID. A model failure is recorded as a failure, never counted as successful abstention.

The no-evidence response and both interfaces previously overstated what an unknown search
term proved. They now say it was not found in indexed content and explain that unread or
skipped content may contain it. Two regression cases cover complete and partial scans.

The small demo project has no architecture-topic evidence. Its overview correctly retains
the available sections, reports a partial job, explains the missing evidence and offers
retry. The browser test checks this expected state instead of waiting for a successful job.

## Agent review and remaining limitations

The agent checked all nine latest answers against their retained sources: embedding and chat
model names, purpose/audience, database/driver, startup command/port and image extensions are
present in the cited evidence. The unavailable-cost question declines to invent an amount;
the off-topic response stays within the indexed scope. This is a small reference set, not
an accuracy guarantee for arbitrary questions. Minor repetition remains in the purpose and
startup responses; both are recorded in `agent-review.json` for further quality work.

The latest exact responses, source excerpts and an empty ratings template are available in
`answer-review.html` and `human-review-template.json` beside the reports. Agent inspection
remains distinct from the human correctness/source-sufficiency ratings required in
[task 5.2](TASK_5_2.md). Apply ratings only to the matching dataset and response hashes.

Slack's workspace name is not configured, so message permalinks remain unavailable.
Slack bot-token support, a second-repository evaluation, unfamiliar-user usability and
multi-user access isolation are not accepted by these checks. Existing controlled tests
cover permission denial and interruption; real account revocation was not attempted.

## Repeat the checks

Use the project's Python environment and an idle local app with the matching saved project:

```powershell
python -m pytest -q
npm --prefix frontend run build
python scripts/smoke_demo.py
python -m pka.acceptance --output data/acceptance/connections.json
python -m pka.access_check --output data/acceptance/access.json
python -m pka.answer_evaluation --set evals/answers_bsa_followups.json --output data/acceptance/answers.json
```

If the global pytest temporary directory is inaccessible, pass `--basetemp` with a **new,
empty directory inside this workspace**. Pytest owns and may clear that directory; never
point it at project data. The acceptance rerun used a dedicated directory under its output
folder. Evaluation records answers in the selected app; use a separate database/app copy
when the user's current answer history must be preserved.
