# Feature explorer and payload

The deterministic backend (`pka/features.py`) and the interactive `/features` page are connected.
The runtime frontend types are in `frontend/src/lib/features.ts`.

## Implemented behavior (23 October 2026)

The page reads `/api/features` and `/api/features/{id}` after project selection. It supports
search, feature deep links (`?feature=orders`), summary shortcuts, keyboard-accessible tabs,
source links and expandable evidence gaps. Home and the overview link into the explorer.
Opening it or switching tabs never calls an overview build or a model. Background access
revalidation keeps the selected tab; a changed source revision replaces the saved details.
Failures hide previously displayed protected data and remain distinct from empty results.

Both feature GET responses identify their source with `repo`, `branch`, `scan_id`,
`commit` and `knowledge_revision`. The UI accepts results only for the current project
and saved read. Queuing a source import clears the feature list and detail until that
read finishes. Starting an overview build refreshes **Main features**, including its
count. Delayed responses from an earlier project or read cannot restore old cards.
The backend also rechecks the revision after source access checks before returning features.
Feature details already opened on the current page are reused when a reader switches
away and back. **Refresh feature** fetches them again; a different project or saved
read gets a new detail request.

Features start at route declarations, grouped by URL subject, and follow handler imports up
to two steps. At most 24 groups and 20 files per group are displayed; unmatched files/routes
are reported. This is not an exhaustive inventory of business capabilities. Route names may
group code from both GitHub and an additional local folder, but import resolution never jumps
between those sources just because module names match. Links are pinned to the GitHub commit
or local snapshot. Source-file links open the first indexed line; route/test links open the
declaration/import line.

The five views are Overview, Code flow, APIs and data, Tests, and Known problems. The code
flow is a static map, not a runtime trace. Data declarations do not prove reads or writes.
Test imports do not establish coverage or passing tests. Jira key references are confirmed
references; name matches are marked possible. Slack discussions are available through Ask
assistant, not automatically attached to this feature map.

Feature prose is now available through the separate **KT walkthrough** tab (27 October
2026). The detail endpoint lists six `walkthrough_sections`; explicitly building one calls
`POST /api/features/{id}/walkthrough/{key}`. It returns checked statements, exact excerpts,
knowledge gaps, generation time and source revision. Sections use related code and tests,
confirmed Jira references and matching documentation. Every request revalidates access
before and after generation. Source changes discard in-flight results. The browser retains
sections only for the current feature/revision; there is no persistent KT cache yet.

Generated sections withhold statements with insufficient text matches, unread-file
claims, and explicit method/path claims absent from their own cited excerpts. The
gap message reports withheld statements. These conservative checks can omit a valid
paraphrase; passing them does not establish factual correctness or runtime behavior.
The example section asks for one evidenced route and its validation conditions.

The deterministic detail's `overview`, outcomes, suggested tests and known-problem items
remain empty. Generated examples and explanations are drafts, not observed runtime behavior
or test results. Runtime-problem analysis is not implemented. Keep those limits visible.

The JSON examples below preserve the original richer design proposal. Fields such as
`built`, generated `plain` text, scenarios, inputs/outputs and suggested tests are illustrative,
not promises of current populated output. Refer to the runtime types and tests for the
implemented read contract.

## What a feature is in this project

A feature is a cluster of things already known separately: one or more routes, the files reachable
from those routes through the import graph in `pka/diagram.py`, the data declarations
and service references found by `pka/facts.py`, the Jira issues whose keys appear in
those files or whose text names those routes, and the test files that import any of them.

A feature is derived, never model-written. The name comes from the route path and the ticket
summaries, not from a sentence a model produced. Prose about a feature is a separate, later call
and carries its own support marking, exactly as overview statements already do.

## Confidence

Every membership carries `confidence`, matching the distinction the diagrams already make:

- `confirmed` — an import line, a route declaration, an issue key written in the file, a test that
  imports the file. There is a file and a line behind it.
- `possible` — lexical or semantic similarity only. Shown dashed or labelled, never presented as
  established.

Nothing is dropped for being only possible. It is labelled.

## GET /api/features

```json
{
  "scan_id": 14,
  "commit": "a1b2c3d",
  "built": "2026-10-09T11:02:14+05:30",
  "features": [
    {
      "id": "checkout",
      "name": "Checkout",
      "plain": "Help a customer turn their basket into a confirmed order.",
      "confidence": "confirmed",
      "route_count": 3,
      "file_count": 7,
      "issue_count": 2,
      "has_tests": true,
      "gap_count": 1
    }
  ],
  "unclustered": {
    "routes": 2,
    "files": 31,
    "note": "Files that no route reaches are not assigned to a feature."
  }
}
```

`plain` is empty until prose has been generated for that feature. The list endpoint never blocks
on a model.

## GET /api/features/{id}

The five tabs on mockup 05 map to five top-level keys. Any key whose evidence is empty is present
and empty rather than absent, so the screen can say "nothing found" instead of hiding a tab.

```json
{
  "id": "checkout",
  "name": "Checkout",
  "plain": "Help a customer turn their basket into a confirmed order.",
  "confidence": "confirmed",

  "overview": {
    "purpose": {"text": "...", "support": "supported", "cites": [0, 2]},
    "statements": [{"text": "...", "support": "partly", "cites": [1]}],
    "sources": [{"n": 0, "path": "src/pages/Checkout.tsx", "line": 14, "url": "https://...", "excerpt": "...", "origin": "github"}]
  },

  "flow": {
    "title": "A customer buys two headphones.",
    "derived": true,
    "steps": [
      {
        "n": 1,
        "label": "Review basket",
        "plain": "Customer checks the items, quantities and total in their basket.",
        "component": {"kind": "file", "name": "CheckoutPage.tsx", "sub": "shopflow/web",
                      "path": "src/pages/CheckoutPage.tsx", "line": 1, "url": "https://..."},
        "confidence": "confirmed"
      }
    ],
    "outcomes": [
      {"kind": "success", "title": "Success", "plain": "...", "evidence": "derived"},
      {"kind": "warning", "title": "Out of stock", "plain": "...", "evidence": "illustrative"},
      {"kind": "failure", "title": "Payment timeout", "plain": "...", "evidence": "illustrative"}
    ]
  },

  "apis_and_data": {
    "routes": [{"method": "POST", "path": "/orders", "plain": "...", "declared_at":
                {"path": "src/api/orders.ts", "line": 22, "url": "https://..."},
                "inputs": [], "outputs": [], "confidence": "confirmed"}],
    "tables": [{"name": "orders", "engine": "PostgreSQL", "plain": "...",
                "declared_at": {"path": "...", "line": 25, "url": "..."},
                "fields": [], "confidence": "confirmed"}],
    "services": [{"name": "Stripe", "plain": "...", "called_at":
                  {"path": "...", "line": 40, "url": "..."}, "confidence": "confirmed"}]
  },

  "tests": {
    "existing": [{"name": "payment-notification.test.ts", "covers": "...",
                  "path": "...", "url": "...", "confidence": "confirmed"}],
    "suggested": [{"name": "Payment timeout", "covers": "...", "why": "..."}]
  },

  "known_problems": {
    "items": [{"symptom": "...", "causes": [], "where_to_check": []}],
    "note": "No application logs are connected, so this is derived from code and tickets only."
  },

  "related": [
    {"kind": "file", "name": "CheckoutPage.tsx", "plain": "...", "sub": "shopflow/web",
     "path": "...", "url": "...", "confidence": "confirmed"}
  ],

  "gaps": [
    {"what": "Refund policy", "checked": "README, src/, SHOP issues", "why_missing": "No source states it."}
  ]
}
```

## Rules both sides honour

1. Every object that points at real code carries `path`, `line` and `url`, and the `url` is pinned
   to the scanned commit. A component with no line number is a bug on the backend side, not
   something the screen papers over.
2. `support` on a statement is one of `supported`, `partly`, `unsupported`, and is computed the
   way `pka/overview.py` already computes it. The screen marks `partly` and `unsupported`
   visibly; it does not hide them.
3. `evidence` on an outcome is `derived` or `illustrative`. Mockup 05 shows three outcome cards
   and two of them are scenarios, not facts. Phase 03 requires illustrative scenarios be labelled
   separately, so the screen labels them.
4. Empty is reported, never hidden. An empty list plus a `note` saying what was checked.
5. Neither GET endpoint calls a model. The separate explicit KT POST endpoint generates
   draft prose with its own sources, checks and knowledge gaps.
