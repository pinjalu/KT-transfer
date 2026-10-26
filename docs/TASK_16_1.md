# Task 16.1: Explain existing tests and why they matter

The **Existing tests** page (`/tests`) reads test definitions from the saved project scan.
It is available in the sidebar and from the Feature explorer's Tests tab. It does not call
Ollama, import project modules, collect tests, run fixtures or execute assertions.

For supported Python definitions it shows the test name, source docstring when available,
assertion explanations, exception expectations, skip/xfail/parameterization declarations,
original source text and links pinned to the commit or local snapshot. Strict and inclusive
comparisons stay distinct. Nested helper definitions are not counted as assertions executed
by their enclosing test. Common unittest assertions require a directly declared TestCase
base; pytest aliases are read from imports.

Every item is labelled **Definition / Not run**. The explanation describes what a written
check requires and the regression it can detect. Business purpose is attributed to the
test's docstring when supplied; it is not invented from the filename. Definitions do not
prove coverage, collection, a passing run or production behaviour. Suggested tests remain
separate in Ask assistant.

## Scope and limits

- Candidate files use the same conservative test-path patterns as Feature explorer.
  Python test functions, Test-prefixed classes and direct unittest.TestCase methods are
  supported. Other matching files are listed with an unsupported-language explanation.
- Custom collectors, inherited tests, dynamic imports, reassigned framework names, overridden
  assertion methods, fixture/helper bodies and other frameworks are not resolved. Parameter
  values and skip conditions are displayed but never evaluated. Definitions are not a count
  of collected test cases.
- Up to 100 candidate files, 300 definitions and 20 checks per definition are shown. Per-file
  analysis is limited to 20,000 line positions and 250,000 stored characters. Limit omissions,
  parse failures, unrecognized checks and partial scans are visible.
- The index can omit blank or unavailable lines between chunks. Such gaps are disclosed,
  original line positions are preserved, and missing content is never fabricated.
- An empty result means no supported definitions were found in the saved scope. It does not
  establish that the repository has no tests.

The endpoint requires an authenticated workspace, rechecks connected-source access and
withholds results if the source revision changes during analysis. The page hides failed or
superseded reads. Search and expanded details stay in the mounted page across navigation;
refreshing the browser starts a fresh view. Browsing never starts a model or overview build.

## Validation on 26 October 2026

- Backend: 47 tests passed across the new parser/API tests and authentication suite, plus
  16 existing feature/fact/source-link regressions and one new adversarial workspace-isolation
  check (64 total). Forged workspace query/header values did not expose another account's
  test source. The existing Starlette/httpx deprecation
  warning remains.
- Frontend: all 87 tests and the production build passed. New checks cover inert source
  rendering, source links, partial/unsupported states, search, refresh retention, access
  failure and immediate removal of data from an old source revision.
- Chrome, real BSA snapshot `0cc9ce9`: the page showed no supported definitions and disclosed
  the partial scan. The existing repository selection and imported sources were reused.
- Chrome, separate labelled sample workspace: three stored definitions displayed boundary
  assertions, a ValueError expectation and a declared skip marker. Filtering by test name
  and navigating to Feature explorer and back retained the filter and expanded definition.
  Sample project tests were only inspected as source, never executed.

Browser screenshots and verification notes are saved in the parent workspace's
`outputs/task-16-1-2026-10-26` folder. The existing Ask tab was not reloaded: approval review
blocked that action because it could clear the conversation, so verification used new tabs.
The pre-existing local edit in `pka/embed.py` is not part of this change.
