# Task 6.2 — Explain a selected Jira task

Implemented 22 October 2026. The Jira tasks destination now explains a selected imported
issue instead of showing a placeholder. A searchable list selects the issue; **Explain task**
starts a background job. The result separates purpose, requested work, explicit acceptance
criteria and suggested clarification questions. Model name, saved time, imported excerpts,
Jira link and exact supporting quotes are inspectable.

## Behavior and boundaries

- Only the selected issue's imported text reaches the explainer. No repository or Slack text
  is mixed into that explanation. Separate related-source panels are covered by [task 6.3](TASK_6_3.md).
- Every imported excerpt is processed in bounded batches, including large legacy excerpts.
  The model's structured response must cite a supplied source ID and a quote found in that
  excerpt. Invalid formats or quotes fail visibly instead of publishing an unverifiable result.
- Known Jira bookkeeping, including reporter and rank, cannot support requested work or
  acceptance criteria. Empty sections describe what was not extracted, without inventing work.
  Exact model names and values are requested in the explanation text as well as its quotes.
  A verified quote is retained visibly when the prose omits its versioned identifiers or numeric
  conditions. If a summary cites an explicit request in the description but the work list is
  empty, that request is copied verbatim into the list. This conservative fallback excludes
  comments and statements of current behavior; it is not a complete requirement classifier.
- Long issues use multiple model calls. Each part contributes to the saved result; exact
  duplicate points are removed. Clarification questions are suppressed for multiple parts
  because another part could answer them. Import limits still apply, and coverage gaps are shown.
- Jobs survive navigation and reload. Cancellation waits for the current request and discards
  its result. Explicit retry retains the selected issue. A stopped app marks unfinished jobs
  interrupted; it never restarts them automatically. One job/answer runs at a time.
- SQLite stores completed explanations by issue and knowledge revision. Source changes,
  changed credentials, revoked access and project changes invalidate derived results. Failed
  explicit refreshes can retain the previous valid explanation, labeled as an earlier result.
- Both listing and detail endpoints recheck Jira access; model publication checks it again.
  Temporary connection failures withhold saved content without deleting it. Confirmed denial
  removes the source and explanations. Jira-only explanation does not require Slack access.
- Example mode produces a deterministic, labeled explanation. Normal mode uses local Ollama.

API: `GET /api/jira/tasks`, `GET /api/jira/tasks/{key}` and
`POST /api/jira/tasks/{key}/explain`. Existing job cancellation/retry endpoints apply.
The normal same-origin request header, no-store responses and selected-project boundary apply.

## Verification

Evidence is local under `outputs/task-6-2-2026-10-22/` in the workspace; private Jira text,
database copies and runtime credentials are not committed.

- Production React build passed.
- All 515 regression tests passed. After the final quotation and detail-preservation safeguards,
  all 35 focused task tests passed. Checks cover scope, exact quotes, metadata classification, long excerpts,
  persistence, invalidation, access before and after generation, cancellation, retry and APIs.
- Ten Chrome checks passed with the real UI and controlled Jira/model fixtures: empty state,
  search, navigation during work, cited result, reload, task switching, cancel/retry, model
  failure, stale-response isolation, responsive layout and revoked access. No page errors.
- A scoped real Jira read and local `qwen3:1.7b` explanation passed on a disposable index.
  A metadata-only issue correctly produced no requirements or acceptance criteria after the
  metadata filter was added. All four imported issues passed the access check.
- Two additional real Ollama replies for synthetic configuration and receipt-access tasks were
  revalidated through the final checks. Both retain exact model names or HTTP status values,
  requested work, acceptance criteria and valid supporting quotes. These are examples, not an
  exhaustive model-quality benchmark or human acceptance review.
- The updated app was restarted while idle and reconnected to the same project. A real
  explanation completed successfully without changing its 1,099 source excerpts or existing
  answer/overview counts. Three additional Chrome checks confirmed that the four real Jira
  tasks display, the saved explanation survives navigation, and reload starts no new job.

## Limits

A matching quote and lexical support label do not prove that a model interpreted the task
correctly or extracted every condition. Review the original excerpts, especially when comments
contain proposals or contradictory requirements. The model can still omit details or assign a
statement to the wrong semantic section. Each batch permits up to two summary points, eight
requirements, eight acceptance criteria and four questions. These are extraction bounds, not
a completeness guarantee. No implementation or test completion is inferred from Jira status.

This task changes orchestration, validation, prompting and display. It does not train or
fine-tune Ollama model weights. Existing Jira import exclusions and read limits remain in force.
