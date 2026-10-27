# Private team release

Work started 27 October 2026. Scope: the seven agreed features: team access, project
connections, project Q&A, project understanding, knowledge-transfer walkthroughs,
knowledge refresh, and private deployment.

The 26 October tracker maps 100 tasks to this scope: 60 marked Done and 40 open.
Counts are tracker states, not estimates of engineering effort or release readiness.
Existing local Windows behavior is the baseline. Shared HTTPS hosting is implemented
and locally verified; office activation remains open. Tests use disposable fixtures.
The existing owner account, credential vault and saved source selections are preserved.

The updated workbook has **63 Done and 37 open** among the 100 mapped tasks.
Across the entire 126-task roadmap it has 65 Done, 39 Progress, 19 Pending and
3 Testing. This is not a claim that all seven features are complete.

## Work order and acceptance

| Order | Tasks | Acceptance | Current state |
|---|---|---|---|
| 1 | 5.2 | Deterministic and UI regressions pass; real answers are inspected; a person records correctness and source-sufficiency ratings. | Regression checks passed. Live answers inspected. Human reviews remain open; automatic checks are not correctness ratings. |
| 2 | 6.8 | Credentials remain encrypted and isolated; audit records omit secrets and are owner-only; current Windows tests pass. | Done for the existing Windows scope: 46 tests passed. See TASK_6_8.md. |
| 3 | 6.9 | Explicit private-host configuration, authenticated access, health checks, verified backups and a recovery procedure. | Implemented. Actual team certificate passed verified HTTPS checks with disposable data. Live-data recovery passed. Office activation and operating arrangements remain open. |
| 4 | 7.2 | Unchanged, edited, deleted and interrupted imports behave correctly in API and browser checks. | Done for GitHub/local incremental and resumable imports. 112 focused tests passed. Live GitHub read 57 files; retry reused all 57 and fetched 0. No scheduler or Jira/Slack resume. |
| 5 | 21.2, 21.5, 22.1–22.4 | Evidence labels, access/deletion invalidation, refresh relationships and visible refresh times work for the supported sources. | 22.4 Done: all-source snapshot times shown and verified in browser. Existing access/change checks passed. Scheduled refresh and automatic KT regeneration remain absent. |
| 6 | 7.3, 9.1–9.3, 10.1–10.4, 11.1–11.6, 12.2–12.4, 13.1–13.7, 14.1–14.3 | Project-specific explanations have inspectable evidence, honest static-analysis limits and no invented runtime behavior. | Improved with six feature-scoped KT sections and corrected Python import aliases. Deep call/data analysis remains bounded; generated business-purpose and example content needs review. |
| 7 | 20.1–20.3 | Structured walkthroughs retain purpose, examples, flows, component links, tests and explicit knowledge gaps. | Testing: six sections implemented, backend/UI checks pass, live purpose generation works. Section content acceptance remains open. |

Task 16.5 test-suggestion content review is a conditional release gate while that
feature remains exposed; it is outside the 100-task counting map above.

## Verification record

- The project `.venv` runs Python 3.12.14. The older `venv` points to a removed
  Python 3.10 installation. Use `.venv` for application and tests.
- Installed the existing pinned test requirement, pytest 8.4.2, into `.venv`.
- An existing user change in `pka/embed.py` was present before this work and is
  preserved.
- The final app runs at `http://127.0.0.1:8000` with the existing signed-in owner.
  Reconnecting the saved BSA project preserved its source selections and account.
- Full backend suite: **992 passed**. After the final alias and maintenance-lock
  fixes, **296 focused tests passed**. These counts overlap and must not be added.
  All **89 UI tests passed**; the final changed UI selection passed 22 tests.
  Production TypeScript/Vite build passed. One existing Starlette TestClient
  deprecation warning remains. No implementation test failed in these final runs.
- Live repository refresh: 57 files, 0 failures, 7 exclusions. One size limit and
  one overlong-line exclusion keep coverage partial; other exclusions are generated,
  potential-secret and unsupported files. Retrying reused all 57 files, fetching 0.
  Jira and Slack were re-read successfully after the repository replacement.
- Live purpose generation produced inspectable source citations and provenance
  labels. Some generic business-benefit wording still needs review. This was not
  recorded as human acceptance. Old evaluation #45 had 5/6 automatic checks and
  no human ratings; its database phrase mismatch was due to cited excerpts outside
  the test's fixed reference ranges, not missing PostgreSQL/asyncpg in the answer.
- Fresh evaluation #50 completed all six cases on 27 October at 11:07 IST.
  Five passed automatic checks; the database case still missed its reference-phrase
  check. No generation errors occurred. All six human reviews remain unsubmitted.
  The database reference list was subsequently extended with two verified source
  locations: README line 132 and admin-panel/main.py line 6. The phrase and citation
  requirements are unchanged. All six retained answers pass when rescored against
  these references; this is not a new generation or a human correctness rating.
  The reference fix and quality workflow passed 47 focused tests. Run #50 remains
  bound to its original question set, so a fresh run is required for human review.
- Fresh run **#51** completed through the signed-in browser with **6/6 automatic
  checks passing** and no generation errors. It uses the updated verified reference
  list and is available for human review. No human ratings were submitted by the
  agent. Browser proof is saved as `live-quality-final.jpg`.
- The final live feature view confirms that Admin includes both `main.py` and
  `database.py`, and exposes all six KT section controls.
- Live generation of the Admin example section exposed an unsupported `GET /admin`
  analytics-response claim. The cited database helper did not establish that route
  or response. A focused fix now requests one evidenced route and withholds weak
  matches, unread-file claims and method/path claims absent from their own citations.
  **18 focused KT/alias tests passed**, including this failure and wrong-method,
  prefix and case mismatches. These conservative checks do not prove semantic
  correctness. Loading this last fix into the running app and rechecking the example
  remain pending while the user reviews run #51; avoid interrupting unsaved ratings.
- Two verified live-data backups are in the release output folder: before changes
  and after refresh. The separate recovery drill retained every project-table row
  count and account count, decrypted the original credential vault under the owner
  Windows account, and revoked restored sessions. The original data was not replaced.
- The selected office host is `192.168.0.149:8443`. A 90-day private server
  certificate, public distribution copy, fingerprint and `Start-Team.ps1` are ready.
  The private key folder is restricted to the owner Windows account and SYSTEM.
  No certificate trust, firewall rule, autostart task or network listener was installed.
  See [TEAM_OFFICE_SETUP.md](TEAM_OFFICE_SETUP.md).
- The tracker copy preserves all 126 existing notes, its table, validation, styles,
  formulas, sheet structure and unrelated cells. Eleven task status/remark rows were
  updated; the source workbook remains untouched.

Verification artifacts are in `../outputs/team-release-2026-10-27` relative to
the repository. They include JUnit results, recovery/HTTPS results and browser proof.

Each task remains open until its stated checks finish. A passing test fixture does
not establish successful deployment, live-source behavior, or human acceptance.
