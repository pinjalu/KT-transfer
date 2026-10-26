# Task 5.2: Evaluate answer quality

The answer evaluator and source-checked BSA baseline are implemented. Human review of
correctness and source sufficiency remains pending; task 5.2 stays **Progress** until that
review is recorded. Reference phrases, valid citations and model confidence are not accuracy
scores. The six reference cases were authored by the coding agent and checked against source
lines; they are not a human-labelled benchmark.

## Browser workflow (26 October 2026)

Open **Answer quality** in the sidebar after selecting the project. Choose one of the three
saved BSA question sets and select **Run evaluation**. A background job calls the normal
answer pipeline sequentially and saves progress. Navigating away does not restart the run.
Cancellation waits for the current request; retry starts a fresh run, leaving completed cases
from the earlier run available for inspection. Restarted jobs are marked interrupted.

Each question set requires its exact repository and commit. The four-question boundary set
covers the 0.45/0.60 decision, strict equality at the handoff threshold, missing production
configuration, and public-image versus private-signing evidence. This is a small regression
set, not a general accuracy benchmark. Runs also record the model, scan completeness and
knowledge revision. A generation failure stops the batch and remains a failure.

Select **Inspect** on a case to see the exact retained answer, source excerpts, reference
guidance and automatic-check details. Review correctness and source sufficiency separately,
then select **Save my review**. Both fields start unselected. The authenticated account is
recorded as reviewer, and the submission must match the dataset and response hashes. Reviews
cannot be saved while the run is still changing. Agent browser testing must not populate
human ratings on live data.

The workspace retains at most 20 evaluation reports, subject to the existing 30-job history
limit. Reports store metrics and answer IDs; they do not duplicate generated text or excerpts.
Answer inspection and review recheck source access. Source refresh, selection changes or
revocation remove dependent reports and answers. A stale in-flight run cannot recreate them.
The existing command-line workflow below remains available. Arbitrary question-set upload and
multi-turn evaluation are not included in this browser workflow.

Verification on 26 October: 856 backend tests and 70 frontend tests passed; the production
bundle built successfully. Chrome ran the four boundary questions against the retained BSA
commit with `qwen3:1.7b` (run 44, partial source scan). Three passed the automatic checks.
The decision answer correctly named 0.45 and said 0.60 was not applied, but used “remains”
instead of a configured reference phrase, so the mechanical check flagged it for inspection.
The dataset was not changed to turn that result green. Exact-answer/source inspection,
unselected review controls, draft preservation across navigation and saved results after
refresh were checked in Chrome. Live human ratings remain empty. This verifies the workflow,
not human accuracy acceptance or performance on arbitrary questions.

## Run against the local app

From the project directory, using the application's Python environment:

```powershell
python -m pka.answer_evaluation --set evals/answers_bsa.json --output data/acceptance/answers.json
```

The app must be running, idle, in live mode, with a usable latest scan. The set pins
`pinjalu/BSA_chatbot` to commit `0cc9ce981956e6e3c352836e8112a06700360947`.
Another repository or commit is rejected before asking any questions. To evaluate a different
snapshot, create and source-check its reference set first.

Each case calls the real `/api/ask` route sequentially. This includes normal access checks,
retrieval, Ollama generation, answer cleanup and the app's normal answer retention. No remote
source is modified. `--url` accepts only a local HTTP address; it defaults to
`http://127.0.0.1:8000`. `--timeout` is 240 seconds per request by default, with a range of
5 to 600. A request failure stops the run because the app may still be processing that request.
Finished cases are checkpointed to the report after each answer.

Exit 0 means measurement finished, including cases whose checks failed. It does not mean the
answers were accepted. Exit 1 means the run could not finish, inspect or save; exit 2 is invalid
command usage. Inspect `run_complete`, the individual results and `quality_acceptance`.

## What is measured

| Measure | Meaning | Limit |
|---|---|---|
| Reference retrieval | An expected file and overlapping line range were returned | Does not prove the retrieved passage is enough |
| Citation checks | Statement IDs resolve, source IDs are unique, GitHub links use the pinned commit and correct range | Does not prove the statement follows from the passage; Jira/Slack links are not verified here |
| Cited reference phrases | Required phrase alternatives occur in statements citing an expected excerpt | Negation, semantic mistakes and unrelated extra claims can still pass |
| Behavior | Answer, abstain, or disclose missing information as specified | A disclosure does not excuse an invented claim elsewhere |
| Human correctness | Correct, partially correct, incorrect | Supplied by an identified human, never inferred from phrase overlap |
| Human source sufficiency | Sufficient, partly sufficient, insufficient | Recorded independently from correctness |

Generation errors cannot pass as successful refusals. Empty measurement denominators are
reported as `null`, not as a perfect score. The report contains counts, case IDs, hashes,
answer IDs, timings and scope metadata; it excludes generated prose, source excerpts,
questions and upstream error bodies. The reference set contains the questions.

The older retrieval-only command, `python -m pka.evaluate`, now also refuses a reference set
for another repository or a mismatched optional pinned commit. Its two existing sets belong
to other repositories and are not valid BSA measurements.

## Inspect and review the exact run

The following command reads one retained response from the local database and prints its
question, statements and source excerpts. It does not change the database or create an excerpt
export. `--db` defaults to `data/index.sqlite3`.

```powershell
python -m pka.answer_evaluation --inspect-report data/acceptance/answers.json --case database
```

The response must match the report's hash and still belong to the active scan. If an import,
credential change or rescan has removed it, run a new evaluation. Review the exact response;
asking the same question again may produce a different answer.

For each case, check every generated claim against the displayed sources, whether the
requested facts were covered, whether extra material is relevant, and whether missing evidence
was acknowledged. Use **correct** only when the requested facts are answered accurately without
material unsupported claims. Use **partially correct** for a mixed or incomplete answer, and
**incorrect** for a material wrong answer or an unjustified refusal. Judge source sufficiency
separately. Record repetition or irrelevant details in the task findings even when the central
fact is right. For `production_bill`, explicitly check for an invented amount; for `off_topic`,
check that the response does not invent project facts.

A human reviewer can create a JSON review file using hashes from the report:

The recorded run already has a [blank review template](../../outputs/task-5-2-2026-10-22/human-review-template.json)
with the six matching IDs and hashes. Its empty ratings deliberately cannot be applied until reviewed.

```json
{
  "dataset_hash": "copy the dataset_hash from the report",
  "reviews": [
    {
      "case_id": "database",
      "response_hash": "copy this case's response_hash from the report",
      "reviewer_type": "human",
      "reviewer": "reviewer's name",
      "correctness": "correct",
      "source_sufficiency": "sufficient"
    }
  ]
}
```

The example ratings are placeholders, not ratings for the live run. Apply completed reviews:

```powershell
python -m pka.answer_evaluation --review-report data/acceptance/answers.json --reviews reviews.json --output data/acceptance/answers-reviewed.json
```

Dataset and response hashes must match; the whole review batch is validated before changing
ratings. `human_review_complete` means all planned cases were rated, not that all were correct.
Any incorrect or partly correct answers require a recorded finding and a decision about the
remaining limitation before task acceptance. A six-case sample cannot establish general accuracy.

## Live baseline on 22 October 2026

The live run uses `qwen3:1.7b`, scan 28, a partial scan with 57 files read and 7 skipped,
and no stored embedding vectors. Retrieval therefore uses word matching. The baseline covers
project purpose, database/driver, RAG startup, image extensions, missing billing information
and off-topic refusal. Jira issue reasoning, Slack decisions, other models and other
repositories are outside this baseline.

Evidence: [`answers-live.json`](../../outputs/task-5-2-2026-10-22/answers-live.json).
The run finished at 11:16:23 IST. All six requests completed without a generation error.
The app's knowledge revision was 4 before and after the run. All four answerable questions
retrieved an expected excerpt. Three of four matched the cited reference phrases; five of six
cases passed their automatic checks. Every returned citation ID and GitHub link passed the
mechanical checks. **These numbers are not factual accuracy.**

| Case | Automatic checks | Seconds | Coding-agent inspection of the actual answer |
|---|---|---:|---|
| Project purpose | Passed | 91.56 | Identified customer support for BSA motorcycle dealers; added several unrequested implementation claims |
| Database and driver | Passed | 47.66 | Correctly named PostgreSQL and asyncpg; repeated database setup details across five statements |
| RAG startup | Passed | 97.76 | Correct command and port, followed by a contradictory missing-information message saying the command was not explicit; also described a Node.js front layer while the retrieved admin source is Python |
| Image extensions | **Failed** | 105.94 | Incorrectly answered PDF and cited another file's upload validation; the target excerpt already contained PNG, JPG, JPEG, GIF and WebP |
| Actual AWS bill | Passed | 85.34 | Disclosed that no bill was recorded and supplied no invented amount; added six unrelated implementation statements |
| Off-topic phrase | Passed | 6.87 | Returned no statements or sources and explained that no evidence matched |

This inspection is an agent assessment, not a human rating. No human correctness or
source-sufficiency ratings have been submitted. The image-extension failure is in generation
and attribution, not a missing retrieval: source S1 was the requested file, lines 1-54, with
`IMAGE_EXTS` at line 15. The model instead attributed PDF validation from source S4 to the
requested file. Valid citation IDs did not catch that semantic error. The startup contradiction
and unrelated additions likewise show why a phrase-match pass is not acceptance.

Recommended follow-up work is to constrain answers to the requested facts, prevent claims about
one file from borrowing evidence from another, and check for contradictions between the answer
and its missing-information text. Any change should be rerun on all six cases and reviewed;
the reference labels should not be weakened to turn the observed failures into passes.

## Verification

The evaluator tests plus the existing retrieval-scoring regression passed **29 tests**.
They cover wrong repository/commit, invalid citations and links, missing references, generation
errors, remote URL rejection, checkpointing after request failure, review binding, read-only
inspection, deleted or changed answer records, and the distinction between phrase overlap and
truth. The live results above are separate from those controlled tests. The test run also emitted
the existing Starlette/httpx deprecation warning.

An additional live Chrome check submitted the off-topic question through the visible **Ask
assistant** screen. The real API returned answer 42 with no statements or sources, no generation
error, and the missing-evidence explanation was visible. No page errors were recorded. This
checks the browser submission/rendering path; it does not add a new distinct quality case.
Evidence: [browser result](../../outputs/task-5-2-2026-10-22/browser-ask.json) and
[screenshot](../../outputs/task-5-2-2026-10-22/browser-ask.png).

## Follow-up: direct answers and configuration values

Manual testing found two further failures: a question asking for the embedding model returned
the variable name without its value, and a rephrasing returned classifier helper names. The
indexed source contained the model definition, but retrieval had selected usages and unrelated
helpers instead of that definition.

The fix applies to query concepts and code definitions, without any BSA filenames, model names
or canned project answers in the production logic:

- Conversational filler no longer competes with the question's subject during search.
- Inflection families connect words such as embeddings, embedding and embed, including identifier parts.
- Questions about the model answering a bot's questions search chat-model configuration,
  rather than letting a business-domain model name dominate. Explicit embedding, classifier,
  vision, vehicle and database-model questions retain their own meaning.
- Candidate retrieval includes matches for all query concepts; ranking promotes assignments
  and documentation section labels matching the requested concept while preserving the original lexical scores. Common-word
  expansions do not replace those scores or promote long comments mentioning unrelated services.
- Short matching definitions are retained even when they are below the normal excerpt-length
  preference. A one-line configuration value must not lose to a longer unrelated document.
- Ollama is instructed to state the requested value first, distinguish definitions from usages,
  keep claims attached to the right file, and omit unrelated implementation details.
  Components within one document also remain separate; a statement limit is a maximum,
  not a quota to fill after answering the question.
- Focused questions use alternative JSON schemas: a direct answer with an empty missing
  message, or no statement with a specific evidence gap. The answer budget is one statement
  for a single fact, up to three for facts joined by "and" or semicolons. This avoids dropping
  the driver from a question asking for both database and driver. Explicit explanations and
  comparisons retain up to four statements and can disclose partial evidence. A partial focused
  answer must state its limit in the answer itself.
- Direct lookups naming a file restrict the evidence to that file. Relationship and explanation
  questions retain cross-file retrieval. Identical excerpts produced by widening are deduplicated.
- The Ask screen presents **Answer** first and **Details** separately. Backtick-delimited values
  and commands render as inline code using React text nodes, with no HTML interpretation.
  At narrower widths, source cards move below the answer. Enter does not discard a draft while
  another task is running, and the busy message no longer incorrectly calls every job a scan.

This changes retrieval and inference instructions, not model weights. Ollama continues to use
`qwen3:1.7b`; no model was downloaded or fine-tuned. Feedback buttons record review ratings;
they do not automatically train the model. Configuration values still come from the selected
commit, so a changed source value can be retrieved without teaching the model a new answer.

The schema mechanism uses Ollama's [structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
Schema compliance controls response shape, not factual truth. Source matching remains heuristic,
and static definitions cannot establish every runtime override or resolve every dynamic value.

The expanded set is `evals/answers_bsa_followups.json`. It keeps the original six cases and adds
both embedding phrasings and the user's answer-generation model question. Regression fixtures also use different model values, TypeScript port
settings, JSON timeouts, image-format lists, missing definitions, and irrelevant classifier helpers.
The original baseline is retained for comparison.

### Follow-up verification

The full Python suite passed **378 tests**. After the final instruction clarification,
**14 targeted tests** passed again. The frontend TypeScript/Vite build also passed.
The existing Starlette/httpx deprecation warning remains.

The expanded live run completed all nine cases with no generation errors and passed all nine
automatic checks. Evidence: [nine-case report](../../outputs/answer-quality-fix-2026-10-22/answers-verified.json).
Agent inspection confirmed both embedding phrasings named `text-embedding-3-large`, the bot
question named `gpt-5-mini` and cited `CHAT_MODEL`, the database answer included both PostgreSQL
and asyncpg, and the image answer listed the five supported extensions. The missing-bill
question returned no invented amount or unrelated statements, and the off-topic case refused.

Inspection also caught an extra startup sentence mixing the RAG API with two other services,
even though that case passed the mechanical checks. The final instruction now explicitly keeps
components separate within a source and says not to fill the statement limit unnecessarily.
The startup recheck returned just `uvicorn api:app --host 127.0.0.1 --port 8000` and port 8000.
This demonstrates why the report's automatic checks are not an accuracy score.

The final prompt was rerun through the live app on five cases: startup, database/driver,
the conversational embedding question, the bot's chat model, and image extensions. All five
passed their automatic checks, and agent inspection of the retained responses confirmed the
requested values without unrelated extra statements or contradictory missing-information text.
The image response also preserved the leading dots in the actual extension literals.
Evidence: [final prompt regression](../../outputs/answer-quality-fix-2026-10-22/prompt-regression.json).
The two model questions cited the embedding definition and chat-model definition respectively.
This is agent inspection, not a human rating or a general accuracy guarantee.

The visible Chrome app returned a direct embedding-model answer through its real API.
The final layout was checked at 1024 and 1440 pixels by replaying that captured live response
in a separate headless browser. The narrow layout stacks sources below the answer, with no
overlap, horizontal overflow or page errors. Evidence:
[live browser check](../../outputs/answer-quality-fix-2026-10-22/browser-verified.json),
[layout check](../../outputs/answer-quality-fix-2026-10-22/layout-verified.json),
[1024px image](../../outputs/answer-quality-fix-2026-10-22/layout-fixed-1024.png) and
[1440px image](../../outputs/answer-quality-fix-2026-10-22/layout-fixed-1440.png).

To rerun the expanded reference set against the idle local app:

```powershell
python -m pka.answer_evaluation --set evals/answers_bsa_followups.json --output data/acceptance/answers-followups.json
```

These checks concern the indexed BSA commit and `qwen3:1.7b`. They do not establish reliable
answers for every future question, repository or model. Human review of the retained evaluation
answers remains pending; task 5.2 is still **Progress** in the evaluation workflow.
