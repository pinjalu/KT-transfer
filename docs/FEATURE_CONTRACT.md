# The feature payload, agreed before either side is built

Step 5 (`pka/features.py`) and step 6 (the feature explorer screen) are being built at the same
time. This file is the shape they both build against, so neither has to guess. Change it here
first and change both sides together.

## What a feature is in this project

A feature is a cluster of things already known separately: one or more routes, the files reachable
from those routes through the import graph in `pka/diagram.py`, the tables those files touch
according to `pka/facts.py`, the external services they call, the Jira issues whose keys appear in
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
5. The list endpoint is cheap and never calls a model. Prose arrives on the detail endpoint and
   may stream in, like the overview already does.
