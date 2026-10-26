# Task 16.6: Separate suggested behaviour from verified project behaviour

The answer renderer now shows an evidence label on each statement in Ask, project overview,
Jira explanations and answer evaluation. Labels remain visible in Beginner mode, even when
citations or project-name warnings are hidden.

| Label | Meaning |
| --- | --- |
| Verified from code | The existing deterministic numeric-rule checker computed this result from parsed code, for the stated input and assumptions. It did not run the project or check production. |
| Suggested behaviour | A recommendation or proposed expected outcome; not evidence that it exists or has been tested. |
| Code-based explanation | Model-written prose citing code. It still needs review for factual correctness. |
| Test definition, not a test result | Cites a test or fixture file; no test execution is inferred. |
| Documentation or configuration | Written documentation/settings, not proof of the deployed state. |
| Recorded requirement or discussion | Jira/Slack evidence, which can describe plans, agreements or reported results. It does not independently verify implementation. |
| Mixed evidence — needs verification | Citations span different evidence types. |
| Behaviour not verified | Uncertain, insufficient or missing evidence; also the safe fallback for older saved answers without labels. |
| Example data | Simulated content, never verified live behaviour. |

The backend derives provenance from actual cited source IDs and paths. It recognises common
English recommendation and uncertainty wording. A source containing the word “verified”,
perfect word overlap, or a model-supplied evidence object cannot grant verification. The
generator schema still only accepts statement text and citation IDs. Only the deterministic
numeric checker can provide the internal verification signal; that signal is removed before
publishing the answer. Test files, Jira records and documentation cannot use that signal to
become verified code evidence.

The generation instruction asks the model to introduce recommendations with **Suggested:**,
keep them separate from existing behaviour and never infer a passing test run from a test
definition. The existing overlap warning is now called **Some text overlap** or **Low text
overlap** rather than implying semantic support. Overlap and provenance are separate checks.

Saved answers and evaluation hashes are preserved. Older answers show **Behaviour not verified**
until a fresh answer is generated; they are not silently relabelled as verified. No scanned
project code or tests are executed by this feature. It does not certify arbitrary generated
claims, infer production state, resolve conflicting discussions (task 15.3), or create a new
test-generation workflow (task 16.5). English wording rules may miss a recommendation, but
that omission still cannot promote model prose to **Verified from code**.

Implementation: `pka/statement_evidence.py`, shared `overview.tidy`, the deterministic answer
check integration in `service.py`, and `frontend/src/components/Statements.tsx`.

## Validation (2026-10-26)

- Backend suite: 884 passed. Frontend suite: 74 passed. Production UI build passed.
- Tests cover recommendation wording, source types, uncertainty, mixed evidence, legacy
  answers, and attempts to forge verification through model output or matching words.
- Live Chrome, BSA_chatbot: the exact-0.45 answer displayed **Verified from code** with
  the runtime limitation. Jira/Slack-based responses displayed **Recorded requirement
  or discussion**, including in Beginner mode. Navigating to Answer quality and back
  retained the conversation and labels.
- An answer retained before this change in evaluation run 44 displayed **Behaviour not
  verified** and the explanation that it predates evidence labels. No review was submitted.
- Two live requests for test suggestions produced source summaries instead of the requested
  tests; the handoff summary also described the additional guards imprecisely. These are
  recorded answer-quality failures, not passing evaluations. Neither response was labelled
  verified. The recommendation label itself is covered by backend pipeline and frontend
  rendering tests; this live model session did not produce that branch.

Browser evidence and verification notes are saved locally under
`outputs/task-16-6-2026-10-26` in the workspace parent. These checks establish the label
behaviour, not general answer accuracy or human acceptance of task 5.2.
