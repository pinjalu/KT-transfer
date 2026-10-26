# Task 15.3: Distinguish suggestions, agreements and conflicting decisions

Team decisions now includes a source-wording review before the optional generated summary.
Opening a channel compares its imported passages without asking the model to generate new
text. The existing access checks, source revision checks and import coverage warnings apply.

- **Suggestion / proposal:** an explicitly worded idea or recommendation. Mentioning that
  application code can "suggest handoff" is not itself a new team proposal.
- **Recorded agreement:** a stated choice with explicit adoption wording. Vague assent,
  questions, quoted/code-block examples, conditional plans and incomplete passages do not
  establish agreement. Pending approval and negation cannot be removed by a shorter quote.
- **Different proposed or recorded choices:** comparable values differ, but the evidence
  does not contain two incompatible recorded agreements. Different proposals are alternatives.
- **Possible conflicting agreements:** distinct messages explicitly adopt different values
  for the same recognised setting or choice. Both positions remain visible; no winner is
  chosen from timestamp, author or model preference.
- **Recorded correction:** a direct thread reply explicitly says it replaces the parent's
  proposal and records a choice. The original proposal, adopted wording and withdrawal are
  retained together. This records the reply's claim, not independent approval authority.
- **Mixed positions / unclear decision status:** generated summary evidence cannot safely
  be reduced to one status. Existing historical-wording support remains available.

Statements are split at sentence/line boundaries while preserving decimal values and their
qualifiers. Each recognised position keeps its source ID, exact wording and full message,
including recorded authors, timestamps and Slack links. Users can filter and paginate positions.
Named choices are compared across all imported passages, including different model batches.

The generated-summary validator now requires the supporting quotes themselves to establish
the status. Two merely different messages no longer qualify as a conflict. Model paraphrases
that change the status are replaced by their supporting source wording. Older saved summaries
receive the new label checks when read; their stored payload and model generation time are
preserved, and the UI explains that labels were rechecked. Ask's instructions also distinguish
alternatives, agreements, explicit corrections and unresolved conflicts.

## Limits

These are conservative English wording checks, not complete semantic understanding. Automatic
value comparisons cover explicit uppercase setting names and simple product choices, and can
miss indirect disagreement or differently phrased subjects. Different explicit deployment
scopes, equal numeric values and duplicate message IDs do not create conflicts. A shared Jira
key or thread alone is not evidence of disagreement. An explicit replacement requires stored
thread metadata; legacy transcripts without it cannot establish that relationship.

Agreement does not establish implementation, production configuration, approval authority or
current team policy. Partial and omitted source content remains a limitation. Comparing Jira
requirements to code (15.1/15.2) and checking whether a decision is still implemented (15.4)
remain separate work. No Slack messages or Jira issues are written by this feature.

Implementation: `pka/decisions.py`, the decision read/generation paths in `pka/service.py`,
and `frontend/src/pages/TeamDecisions.tsx`.

## Validation (2026-10-26)

- Full backend regression run: 904 passed. After the live-data correction refinement,
  all 185 affected decision, Slack, answer-quality and evidence tests passed, including
  four additional cases for title mentions and explicit thread replacement.
- Frontend suite: 79 passed. The final comparison-layout refinement passed its five
  focused frontend tests. Production build passed.
- Live Chrome with BSA_chatbot / #casper: 20 imported passages were checked without
  generating a summary. The 0.60 proposal, recorded 0.45 choice and explicit withdrawal
  appeared together as a recorded correction. Two incomplete passages remained excluded
  from establishing agreement.
- Chrome checks covered agreement filtering, original author/time/link inspection, and
  preservation of the selected filter and opened evidence across navigation. These checks
  used existing imported messages; no Slack or Jira records were changed.
- Controlled tests covered unresolved conflicting agreements, different proposals,
  unrelated decisions, duplicate message IDs, deployment scopes, equal numeric values,
  negation, conditions, forged conflict claims, legacy saved labels and denied source access.

Local browser evidence is in the workspace-parent directory
`outputs/task-15-3-2026-10-26`. These are technical checks, not human acceptance of general
answer accuracy or a claim that every semantic conflict will be found.
