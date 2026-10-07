# Project plan

The product helps a developer understand a project and investigate tasks with less dependence on experienced colleagues. All connectors must be explicitly scoped and read-only. Advance only after the previous stage has passed its acceptance checks.

## Stage 1 — implemented; live acceptance passed on 6 October 2026

One GitHub repository and branch; commit-pinned scans; a real MCP client/server; bounded, path-aware text chunks; local lexical search; plain-English Ollama answers; inspectable sources; scan coverage and failures; freshness checks; manual feedback; a browser interface and Windows instructions.

Acceptance gate: install on the target Windows/Python 3.10 environment, scan the chosen repository, verify the commit and line links, ask known questions using the real Ollama model, and test an expired/revoked token. Fixture and protocol checks are included. Do not treat fixture results as live model accuracy.

## Stage 2 — beginner-friendly overview, implemented

Build an overview workflow from evidence about purpose, technologies, modules, documented setup/startup, important flows and suggested reading order. Gather evidence separately for each topic, cite sources and expose missing information. Do not infer business goals from names alone. Cache by commit and invalidate after refresh. Do not claim repository-wide understanding from a few excerpts.

Acceptance: a developer can follow only documented setup instructions, find important entry points, inspect every reference and see which overview sections lack evidence. Confirm that collected instructions are presented as documentation, never executed automatically.

## Stage 3 — Jira task explanations, reading implemented, not yet verified live

Replace the disabled Jira placeholder with an adapter using read permissions for one selected Jira project. Add only scoped read tools to MCP and the backend's explicit tool allowlist. Handle pagination, custom acceptance-criteria fields, descriptions, comments, credentials, rate limits, updates and deletions.

For a selected issue, explain the request, requirements, related code/documents, recorded discussions/decisions, investigation areas and open questions. Establish confirmed relationships through explicit issue keys, URLs and recorded links. Label lexical or semantic similarity as a possible connection, not a confirmed relationship. Preserve issue keys, timestamps and URLs in the index.

Acceptance: a known ticket produces a traceable report; unrelated projects never enter the index or answers; missing custom fields and uncertain matches remain visible; no issue is created or changed.

## Stage 4 — Slack decision context, reading implemented with a user token

Replace the disabled Slack placeholder. Require an explicit channel allowlist and a connection authorised to read those channels. Read relevant messages and thread replies with cursors, timestamps and permalinks. Account for channel membership changes, deleted/edited messages, retention limits, API restrictions and token revocation. Do not silently add channels or direct messages.

Distinguish a proposal from an agreed decision. Preserve conflicting evidence and identify who said what and when only when the source records it. Implement refresh/tombstone handling so removed or newly inaccessible content is excluded from both retrieval and answers, including any stored answer caches.

Acceptance: a real recorded decision is distinguishable from an unanswered suggestion, linked threads are complete within disclosed permissions/limits, and deletion/revocation tests prevent obsolete content from being returned.

## Later improvements — evidence-led

Evaluate ordinary-language questions first. If relevant code is repeatedly missed, compare lexical search with a small local embedding model behind the retrieval interface. Measure source relevance and answer quality separately using human-labelled cases; never substitute a model confidence score for accuracy.

Consider incremental refresh, resumable scans, import/call-graph expansion, language-specific parsers, persistent evaluation history without retained restricted excerpts, or a larger local model only when an observed limitation justifies the additional cost. No such features are represented as implemented.

## Gate before multiple users

Implement authentication, per-user and per-source permission checks, credential isolation, permission-filtered search, permission rechecks before answers, secure sessions, audit records and adversarial cross-user tests. A shared index must not return another user's restricted snippets or an answer derived from them. Keep the single-user application local until that work is complete.
