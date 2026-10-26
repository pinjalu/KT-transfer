# Answer checks

Ask assistant now handles two narrow classes of factual questions before model generation:

- For a single numeric input, retrieve the referenced Python comparison and its constant definition from the same indexed file. Evaluate supported literal comparisons without executing repository code. Preserve strict/inclusive operators, qualify environment defaults, and report a visible OR branch and AND-NOT guard separately.
- For a production-state lookup, defaults, example settings, synthetic discussions and pending QA plans do not establish deployment state. Return a specific missing-evidence message unless the excerpts contain a relevant explicit runtime observation. Attribute any observation to its record; do not claim an independent live check.

Missing, dynamic, conflicting or cross-file definitions do not enter the numeric shortcut. It supports a single numeric input and simple Python comparisons, not arbitrary program execution. More complex questions use the model and still require review.

Decision questions give the model relevant decision/discussion excerpts, including competing proposals. The prompt requires an explicit correction before treating a proposal as superseded. Simple yes/no questions have the same concise answer budget as other factual lookups.

These checks add no second model call. They do not make the word-overlap support indicator a factual correctness guarantee.

Run the deterministic regressions with:

```powershell
python -m pytest tests/test_answer_checks.py tests/test_answer_quality.py -q
```

The four user-reported BSA questions are in `evals/answers_bsa_boundaries.json`. They require the matching repository snapshot and imported synthetic discussions. Run them through the existing authenticated evaluation command or Ask assistant, then inspect answers and citations. Automated phrase checks cannot distinguish all negation errors and remain separate from human correctness review.
