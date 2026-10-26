# Answer checks

Ask assistant now handles two narrow classes of factual questions before model generation:

- For a single numeric input, retrieve the referenced Python comparison and its constant definition from the same indexed file. Evaluate supported literal comparisons without executing repository code. Preserve strict/inclusive operators, qualify environment defaults, and report a visible OR branch and AND-NOT guard separately.
- For a production-state lookup, defaults, example settings, synthetic discussions and pending QA plans do not establish deployment state. Return a specific missing-evidence message unless the excerpts contain a relevant explicit runtime observation. Attribute any observation to its record; do not claim an independent live check.

Missing, dynamic, conflicting or cross-file definitions do not enter the numeric shortcut. It supports a single numeric input and simple Python comparisons, not arbitrary program execution. More complex questions use the model and still require review.

Decision questions give the model relevant decision/discussion excerpts, including competing proposals. The prompt requires an explicit correction before treating a proposal as superseded. Simple yes/no questions have the same concise answer budget as other factual lookups.

These checks add no second model call. They do not make the word-overlap support indicator a factual correctness guarantee.

Follow-up questions now carry up to four recent browser-session turns (600 characters per question and 1800 per reply). The server accepts that context only for the same repository, commit and source revision. Replies marked incorrect, failed replies and older-source replies are excluded by the client. Refreshing the browser clears conversation context along with the visible chat. History resolves references but is explicitly untrusted, and all citations must come from freshly retrieved evidence. Earlier answers are not proof.

Referential follow-ups add the previous topic as a separate retrieval query. Independent questions retain their own query; explicit file restrictions still apply. Explanation questions receive up to eight excerpts / 14,000 characters and six statements, while factual lookups keep their smaller budget. Context length and output budgets grow for explanations and conversations. This permits fuller answers without requiring the model to fill the limit.

Set `PKA_EMBED_MODEL=nomic-embed-text` after installing that model to add semantic retrieval. Existing snapshots are embedded on the first question without rescanning or discarding source imports. Nomic uses its documented `search_document:` and `search_query:` prefixes. Stored vectors track the model and preprocessing version; changing either rebuilds the vectors. Failed embedding attempts leave keyword retrieval available and retry after five minutes or a source change. The existing calibration and exact-name matching remain in place. A failed query embedding also falls back to keyword search.

Compare installed answer models with the same synthetic evidence, separately from retrieval:

```powershell
python scripts/compare_local_models.py --models qwen3:1.7b gemma3:4b --output ../outputs/model-comparison.json
```

The six-case report includes expected facts and exact generated responses for manual review. It is a small diagnostic, not a production accuracy percentage or proof that a model matches ChatGPT. Run `tests/test_conversation.py` with the deterministic suites below to verify scope isolation, follow-up retrieval, fallback behavior and answer budgets.

Run the deterministic regressions with:

```powershell
python -m pytest tests/test_answer_checks.py tests/test_answer_quality.py -q
```

The four user-reported BSA questions are in `evals/answers_bsa_boundaries.json`. They require the matching repository snapshot and imported synthetic discussions. Run them through the existing authenticated evaluation command or Ask assistant, then inspect answers and citations. Automated phrase checks cannot distinguish all negation errors and remain separate from human correctness review.
