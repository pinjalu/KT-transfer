# Task 16.5: Suggest tests with reasons and verification steps

Ask assistant now recognises requests such as "Suggest two tests for private S3 signing",
"What tests should we add for the handoff threshold?" and "How can we test a timeout?".
These use a dedicated structured generation format instead of a one-sentence fact lookup
or the numeric-comparison shortcut. Questions about tests that already exist or have run
keep the normal answer path. The configured local model is unchanged.

Every proposed test includes a title, why it matters, setup, at least two actions, an expected
result to validate, observable verification steps, assumptions and a source quote. The UI
shows these fields in all reader modes, with **Suggested / Not run** always visible. Source
quotes and links are available inside each test. The same renderer is used when inspecting
retained answers in Answer quality. Test plans remain in the current conversation when
navigating between screens; refreshing the browser starts a fresh conversation as before.

The plan is stored with the answer and its source revision. Existing access checks run before
retrieval and after generation; revoked access or changed sources prevent publication. Follow-up
context explicitly calls the plan a suggestion that was not run. No test is executed, no project
files are changed, and no external records are written by this feature.

## Validation boundaries

The backend validates the complete plan structure, requested count, distinct titles, known
source identifiers and quotes that actually occur in the cited excerpts. The model cannot
assign a verified status. Recognised claims that tests were executed/passed are rejected.
Malformed summaries, missing verification steps and invented citations withhold the plan.
The original excerpts remain available for manual review.

During generation the model selects evidence identifiers from a supplied catalogue. The
server expands each selection to its original source identifier and quote, preventing a
quote from one source being attributed to another. Unknown selections are rejected.

By default the assistant suggests two tests, with a maximum of four per answer. Requests for
more display the limit. Fewer tests require an explained evidence gap. The prompt requires
unknown fixture keys, environment values and unsupported expected behaviour to be stated as
assumptions rather than invented project facts. Empty or insufficient evidence can produce
an explicit gap instead of a plan.

Test planning retrieves up to five excerpts within a 6,000-character context budget and asks
for concise plans. This leaves room for the structured response and quote schema in the local
model context. Evidence identifiers appear beside the original source lines, so the request
does not send a second copy of every quote. Relevant material outside those excerpts may
still be missed.

These checks establish structure and traceability, not complete semantic correctness. A valid
quote motivates a suggestion; it does not prove that each proposed action or expected result
is correct. Review assumptions, contradictory sources and prerequisites before carrying out a
test. The app does not generate executable test files, provision fixtures, inspect production,
or certify test outcomes. Test-request recognition is English wording based.

Implementation: `pka/test_plans.py`, the Ask generation route in `pka/service.py`, and the
shared `TestSuggestions` frontend component.

## Validation on 26 October 2026

- Full backend suite: 933 passed before the final evidence-selection refinement. The
  affected test-plan, evidence-label, answer-quality and evaluation suites were rerun
  against that refinement: 106 passed. The only warning is the existing Starlette/httpx
  deprecation.
- Frontend suite: 82 passed. Production UI build passed and its assets are included.
- Regression checks cover request routing, numeric-rule bypass, complete fields, counts,
  duplicate plans, insufficient evidence, invented/foreign quotes, mismatched source
  selections, forged verification/execution claims, source revision changes, persisted
  plans, inert rendering and explicit unexecuted follow-up context.
- Initial live trials exposed local-model timeouts and a source/quote mismatch. Those
  responses were withheld, with retrieved excerpts available. The context budget was
  reduced, free-form source/quote pairs replaced by bound evidence selections, and duplicate
  source text removed from the generation request.
- Final live Chrome request on BSA_chatbot (answer 99, scan 35, commit `0cc9ce9`): two
  structured plans rendered with all required sections, exact source quotes and the
  **Suggested / Not run** label. Navigating to Answer quality and back retained both
  plans and the expanded evidence. The local model took 95.72 seconds; total request
  time including access checks was 118.72 seconds. This is a single observation, not
  a performance guarantee.
- **Content review remains partial.** The expired-link and missing-object scenarios
  are relevant, but "check if the signing path is properly validated" is still too
  vague to be a sufficient assertion. Some assumptions also restate the behaviour
  under test. An earlier trial incorrectly borrowed a text-grounding `FLAGGED` marker;
  the final prompt explicitly warns against cross-subsystem markers, and the rerun
  omitted it. These results do not establish general answer accuracy or constitute
  human acceptance of the generated plans. The source scan was partial throughout.

Browser proof and local verification notes are in the parent workspace's
`outputs/task-16-5-2026-10-26` folder. The model remains `qwen3:1.7b`.
