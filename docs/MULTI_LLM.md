# Function-based AI routing

Implementation date: 27 October 2026. Cloud providers ship **disabled**. Office-network deployment remains a separate, pending task.

## Connection diagnostics and monitoring

After saving each key and confirming its free account, use **Test connection** in AI Settings. The model selector affects only this diagnostic. The server sends a fixed synthetic arithmetic prompt to that exact model, validates the JSON, records token usage and latency, and never falls back to another model during a connection test. It works while routing is disabled; it cannot enable providers or approve project content. Catalog checks, key-bound free-plan confirmations, shared quota reservations and cooldowns still apply. The endpoint accepts only a catalog provider/model pair; arbitrary prompts and source content are rejected. A successful connection does not establish factual answer quality.

The owner's first real tests on 27 October returned valid JSON from Groq `openai/gpt-oss-120b` in 0.631 seconds (146 input / 38 output tokens) and Gemini `gemini-3.5-flash-lite` in 3.372 seconds (24 input / 18 output tokens). The first Gemini `gemini-3.8-flash` request timed out at 45.276 seconds; an authenticated model-list request confirmed that both configured Gemini models were available. These are individual connection measurements, not a model-quality comparison. Provider routing and project cloud permission were unchanged.

After restarting, live browser connection tests passed again: Gemini Flash-Lite in 2.443 seconds and Groq GPT-OSS 120B in 0.572 seconds. A startup defect discovered during this verification was fixed: vault migration now imports only missing credential names, preserving saved values and explicit empty values when stale environment variables exist. The original tested Gemini credential was recovered from the verified encrypted backup, and both key-bound confirmations survived the corrected restart. No new free-plan attestation was supplied by the agent. The existing 12 answers, 1,134 chunks, two evaluation runs and two source imports were unchanged; the new log contained neither API key.

Monitoring validation: 426 backend regression tests passed (router, monitoring, authentication, workspace isolation, background jobs, core and conversation). The final monitoring/vault suite passed 20 tests, including the added startup regression. All 96 frontend tests passed and the production build passed. An initial elevated vault-test invocation could not access pytest's temporary folder; rerunning in the normal test context passed all five vault tests. Test artifacts and the live connection report are in `../outputs/llm-router-2026-10-27/`.

The new workspace-local `data/logs/activity.jsonl` records UTC timestamps, HTTP method and application route name, response status, background job lifecycle, overview cache activity, model attempts/skips/fallbacks, quota errors, timings, and reported token counts. Correlation IDs connect events within one request/generation. Each member's workspace has its own file. Logs rotate at 5 MiB, retaining five backups (up to approximately 30 MiB total per workspace). Only allowlisted operational fields are written; keys, authorization headers, URLs/query values, prompts, source text, answers and raw exception messages are excluded. Logging failures do not stop generation. The existing `pka.log` is a separate legacy debug log and retains its existing content policy.

From the project directory, monitor new activity in PowerShell:

```powershell
Get-Content .\data\logs\activity.jsonl -Tail 40 -Wait
```

Settings shows the log location and retention. The file is local to the host and is not exposed by an unauthenticated download endpoint. This monitors application operations, not desktop or browser keystrokes. Restart the backend after upgrading to activate request monitoring.

## Repository review and scope

The inspected GitHub `pinjalu/KT-transfer` master and local HEAD both pointed to `fd89d998ec3cca1a8d24c3a1318c7fc9688e4874`, dated 26 October 2026. Existing uncommitted release work was retained. That initial review did not change Git history. The owner subsequently requested separate feature commits and a push to this repository.

The four generation transports were `service.ollama_answer` (Ask, overview, feature walkthroughs), `test_plans.generate`, `jira_tasks.generate`, and `decisions.generate`. They now build provider-independent requests while preserving their original prompts, Pydantic contracts, citation checks, quote checks and evidence labels. `ollama_answer` retains its public name for compatibility. Retrieval, hybrid ranking, local embeddings, deterministic diagrams and Existing Tests Explorer have not been replaced. Earlier answers remain readable without invented provider metadata.

The minimal architectural change is a shared generation service below the existing feature functions. The new `pka/llm` package owns adapters, validated configuration, privacy gates, quotas, metrics, topic caches and settings endpoints. The existing service continues to own source retrieval, access checks and publication. SQLite changes are additive. Source invalidation also invalidates topic caches.

## Model catalog and initial routes

The catalog is deliberately small and configurable through AI Settings. All cloud model IDs must be in the reviewed allowlist; arbitrary endpoints, paid models and Ollama cloud model names are rejected. An Ollama metadata check also rejects aliases that point to remote models before sending prompts.

| Function | Primary | Fallback |
| --- | --- | --- |
| Project overview | Gemini `gemini-3.8-flash` | Groq `openai/gpt-oss-120b` |
| Ask | Groq `openai/gpt-oss-120b` | Gemini `gemini-3.8-flash` |
| Jira explanation | Groq `openai/gpt-oss-120b` | Gemini `gemini-3.8-flash` |
| Business logic / feature KT | Gemini `gemini-3.8-flash` | Groq `openai/gpt-oss-120b` |
| Test suggestions | Groq `openai/gpt-oss-120b` | Gemini `gemini-3.8-flash` |
| Slack summaries | Gemini `gemini-3.5-flash-lite` | Groq `openai/gpt-oss-120b` |

Groq `openai/gpt-oss-20b` is also selectable. Locally installed `qwen3:1.7b` remains the default final fallback. These assignments are hypotheses, not measured quality rankings. In this release Jira, Slack, local folders and conversation history are privacy-gated to local inference, even when a feature's hypothetical cloud route is configured.

Official documentation reviewed on 27 October 2026:

- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing): the selected Flash models have standard free-tier entries. Free-tier data may be used to improve Google's products.
- [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits): quotas are project-wide; active values must be checked in AI Studio. Local defaults of 2 RPM / 10 RPD are conservative caps, **not provider-reported entitlements**.
- [Gemini GenerateContent reference](https://ai.google.dev/api/generate-content): the adapter uses `generationConfig.responseFormat.text` with JSON schema, fixed HTTPS origin and a header-based API key.
- [Groq structured outputs](https://console.groq.com/docs/structured-outputs): GPT-OSS 120B and 20B support strict JSON schema. The adapter makes every object property required and rejects additional properties without weakening the application's original validators.
- [Groq rate limits](https://console.groq.com/docs/rate-limits): reviewed free ceilings for these models are 30 RPM, 1,000 RPD, 8,000 TPM and 200,000 TPD. Request headers describe daily quotas; token headers describe minute quotas.
- [Groq billing FAQ](https://console.groq.com/docs/billing-faqs): free model availability does not establish the billing status of a particular account.
- [Ollama API types](https://github.com/ollama/ollama/blob/main/api/types.go): `/api/show` includes remote-model metadata, checked before local generation.

Catalog review expires on 26 November 2026. Thereafter cloud generation fails closed until a developer reviews current official pricing/availability and updates the catalog and expiry. No code enables billing, purchases credits, creates accounts or rotates keys to evade quotas.

## Privacy, keys and free-plan activation

Cloud providers start disabled. Enable them only after completing the following setup for the signed-in account:

1. Check the provider's account/project console yourself. Use a free plan with billing disabled and no promotional-credit spending. The application cannot independently verify that account state.
2. Enter a key in **Settings → AI settings**. It is stored in the existing per-account Windows DPAPI vault. Only key-presence flags return to the browser; invalid input and provider error bodies are not echoed. Cloud keys cannot be saved through the legacy plaintext `.env` path.
3. Record the explicit free-plan confirmation. It is a **manual attestation**, bound to that key, expiring after seven days or key changes. Saving/replacing a key disables that provider. Changing keys does not clear usage or cooldowns.
4. Enable the provider and save routing/limits. Set Gemini caps from the actual AI Studio project limits. Configured caps are local safeguards, not authoritative balances.
5. Separately approve the selected connected GitHub repository for each provider. Following the owner's policy update on 27 October 2026, this supports public and private repositories. The server verifies the signed-in account's current GitHub access and pinned snapshot before each cloud attempt. Existing public-only approvals retain their anonymous visibility check until explicitly replaced. Jira and Slack each require a separate source checkbox for the selected project and providers. Existing approvals default to GitHub only. Current Jira/Slack access is checked before saving expanded scope, and project/revision changes abort it. Unapproved projects or source types, local folders and conversation history do not pass this gate. Synthetic CLI tests use only built-in fixture strings and cannot accept private input disguised as a fixture.

Source tokens are entered in **Connections → 1. Add your connection tokens**. GitHub, Jira and Slack each have a visible setup tab; credentials belong to the signed-in account and are not inherited by new members. After saving tokens, use **2. Choose what to read**. Saving an AI key, enabling a provider and approving a project are separate steps; the Settings page displays the saved state and flags unsaved changes.

Cloud providers receive bounded retrieved excerpts and the question, not the entire repository. Existing authenticated workspaces, source permissions, source identity and source revision checks run before and after generation. Revocation or source changes withhold in-flight results. API keys do not enter prompts, logs, URL query strings, metrics or reports.

## Routing, fallback and quota behavior

Automatic mode follows each feature's ordered targets, adding local fallback when allowed. Manual mode pins a model and defaults to **no fallback** for controlled comparisons. All eligibility rules also apply to manual selection.

Focused factual answers use a union between a supported answer and a missing-evidence response. Groq rejects unions whose variants have overlapping required keys. The adapter gives each variant a distinct transport key inside a strict object envelope, preserves every original branch constraint and local schema reference, then unwraps it before applying the unchanged application validators. Malformed envelopes, unsupported citations and answers that violate the factual-answer contract are rejected. A rejected payload does not impose an invented provider-wide cooldown; explicit Retry-After headers and all quota, authentication and server-error cooldowns still apply.

The router makes at most one request to each cloud provider per logical generation. HTTP 429, Retry-After dates/durations, Gemini retry hints, daily exhaustion, temporary server errors, connection errors, timeouts, incomplete responses, invalid JSON/schema and invalid evidence trigger eligible fallback. Exhausted providers enter a persistent cooldown. Provider-reported zero remaining quota also establishes a cooldown before another request. No retry loop spends repeatedly against an exhausted key. Ollama retains its existing single cold-start retry.

Before sending a cloud request, SQLite atomically reserves estimated input (including schema) plus the maximum output allowance. Provider buckets are shared across models, projects, keys and member workspaces on this installation; project-level cloud caps add another limit. Reservations with unknown final usage remain charged conservatively, including cancelled or failed calls. Daily windows use a conservative rolling 24 hours rather than trying to exploit provider reset boundaries.

Groq GPT-OSS reservations use offline o200k token counting, including the strict schema, 32 framing tokens per message, a 10% margin, 128 additional overhead tokens and the full output allowance. These remain local estimates because the provider's internal prompt framing is not exposed. The public vocabulary is bundled with its MIT license and verified against the SHA-256 in [tiktoken's source](https://github.com/openai/tiktoken/blob/0.12.0/tiktoken_ext/openai_public.py); counting makes no network calls. If the dependency or vocabulary is unavailable, the earlier conservative byte estimate is retained. Prompts, retrieved excerpts and output limits are unchanged. Provider-reported usage still replaces estimates after each response.

The usage dashboard separates actual provider-reported usage/headers from local reservations and aggregates. It shows request counts, latency, errors, cooldowns and warnings at 80% of configured local caps. Other applications using the same provider account are not observable; provider 429 responses remain authoritative. Logs/metrics contain controlled error codes and no prompt or response content. Metrics retain 30 days.

If all eligible providers fail, Ask and overview retain retrieved excerpts and show a clear generation error. Jira and Slack retain the already imported source views. A malformed response is discarded; fallback never turns citation validation into a factual-accuracy verdict. Human review remains necessary.

## Overview performance and resume

Topic concurrency is configurable from 1 to 4 (default 2). The existing `PKA_OVERVIEW_CONCURRENCY` environment override is retained for compatibility. A configurable minimum gap of 0–120 seconds between generation starts can pace requests for small free quotas (0 preserves existing behavior). Waiting is cancellable and shown in progress and monitoring logs; cached topics do not wait. Completed validated topics are saved immediately and reused; failed topics are retried through the current route. Per-topic states, actual model metadata, cache reuse and partial coverage are displayed.

Cache identity includes repository, commit, scan coverage/source revision, topic, exact retrieved sources, prompt version and routing/generation configuration. Stored entries also identify the actual provider/model. Changing model routing or project cloud permission creates a different cache identity; source changes purge caches. Concurrency, pacing and quota-only changes do not regenerate explanations. Deterministic facts and architecture diagrams are still derived from source code. Rebuilding does not invent missing information.

## Quality and speed evaluation

**Answer quality** saves actual provider/model, attempts, token usage, elapsed time, timeout rate and validated-response rate. Old reports remain readable. Each run captures routing settings and prompt version; settings changes stop an in-progress evaluation. Human ratings remain bound to the exact retained answer and dataset hash.

For a controlled comparison, select manual mode with fallback disabled, run the same evaluation set for each provider without refreshing sources, then use **Compare model runs**. The server rejects comparisons with different datasets, commits, scans, revisions, prompts or retrieved excerpts, as well as incomplete or unpinned runs. Performance statistics and human correctness/source-sufficiency counts remain separate. Automatic citation or phrase checks are not accuracy scores.

A synthetic harness exercises all six feature contracts using the existing prompts and validators:

```powershell
# Run inside project-knowledge-assistant. No provider is enabled by this command.
.\.venv\Scripts\python.exe -m pka.llm.benchmark --provider ollama --output ..\outputs\local-synthetic.json

# After a free account is explicitly configured, pin one reviewed cloud model:
.\.venv\Scripts\python.exe -m pka.llm.benchmark --provider groq --model openai/gpt-oss-120b --output ..\outputs\groq-synthetic.json
```

The default `--db` uses the owner's existing workspace and shared installation ledger. It uses the DPAPI vault; no key appears in the command. Fixture/input hashes, actual models, outputs, excerpts, latency, usage and missing human ratings are recorded. Disabled providers are reported as unavailable without any API request. Synthetic results do not establish production quality; review every answer and use a larger approved public dataset before selecting winners.

## Risks and remaining acceptance work

- **Account billing state:** manual confirmation is not machine verification. Do not enable an account whose free/no-billing state has not been checked. Existing key-bound confirmations are required even for approved repositories.
- **API compatibility and quotas:** adapters have contract tests and real Gemini/Groq connection checks. Availability and quotas still depend on the account. Catalog expiry protects against silently trusting old pricing forever.
- **Accuracy:** stronger models may still produce incorrect explanations. Existing evidence checks and human ratings are retained. No accuracy or speed improvement is claimed without measured comparisons.
- **Confidential sources:** explicitly approved GitHub repositories may use the selected providers, including private repositories under the owner's updated policy. Jira and Slack require explicit source approval; local folders and conversation history remain local. Permission does not establish a provider's suitability for every organization's data policy.
- **Local inference:** existing hardware and model speed still determine offline latency. The router does not improve the reasoning ability of `qwen3:1.7b` itself.
- **Existing deployment:** office HTTPS activation, certificate trust and firewall rollout remain pending at the user's request.

See the implementation report in `../outputs/llm-router-2026-10-27/` for actual test results and any runtime verification limits.

## Connected GitHub verification — 27 October 2026

The owner authorized connected GitHub repositories regardless of public/private visibility. BSA (`pinjalu/BSA_chatbot`, commit `0cc9ce981956e6e3c352836e8112a06700360947`) now has explicit Gemini/Groq approval after current upstream access was checked. Both providers are enabled using existing key-bound free-plan confirmations. No confirmation was fabricated, quota counter reset, billing enabled or credential copied between accounts.

### Explanation readability update

Overview topics now request beginner-friendly paragraphs explaining component responsibilities, supported steps and useful illustrative examples. Typical guidance is 200–350 words when the excerpts support it; sparse evidence may produce a shorter explanation or an explicit gap. Overview generation may use up to eight separate statements (already supported by the stored answer model); ordinary explanations retain six and simple factual lookups retain their focused contract. Each paragraph must be a separate statement, avoiding provider rejection of oversized text fields. The 1,400-character statement limit, output-token limits, source access checks, citation validation, retrieval and free-tier quotas are unchanged.

Overview instructions explicitly distinguish declared dependencies from demonstrated integrations, and model prompts from implemented workflows. Illustrative examples must use supported steps and must not claim a tested outcome. A first live draft exposed unsupported dependency-to-runtime inferences; regeneration was stopped and these instructions were strengthened before the final rebuild. Prompt changes reduce this failure mode but do not make model-generated prose a verified runtime result.

Every overview view shows all saved paragraphs. Repetitive code/mixed-evidence descriptions are in a closed “Source details” disclosure. Citations, unsupported-file warnings and suggestion/test/unverified labels remain available. Paragraphs, bold headings and inline code render safely as React text; numeric HTML entities and standalone empty list markers are cleaned without executing generated HTML.

The prompt version changed, so rebuilding replaces old terse cached topics with newly generated explanations. Existing answers remain readable. Checks for this change: 142 backend tests passed initially, then 129 routing/answer/conversation tests passed after the final response-format corrections; all 107 frontend tests passed (73 initially, then 34 in the three files whose workers timed out at startup). The production build passed. These automated checks do not replace human review of factual correctness.

Final live BSA rebuild: 8/8 topics processed, zero generation failures and no unknown citation IDs. The final retry reused seven validated topics and completed Technology in 34 seconds overall. Purpose has 299 words, Technology 315 across eight paragraphs, Architecture 308, Runtime Flow 319 with an illustrative example, Interfaces 245 and Data 190. Setup is shorter because of missing source instructions; Testing returned an explicit evidence gap. The controlled diagnostic identified `json_validate_failed`: first an oversized single statement, then eight statements exceeding the prior six-item generation limit. Neither citation rules nor the per-statement limit was relaxed. See `detailed-explanations-live.json` and the XML test reports in the output directory. Source citations and longer prose still do not establish that every described integration is implemented; dependency-only claims require human review.

The saved Ask route is Groq `openai/gpt-oss-120b`, then Gemini `gemini-3.5-flash-lite`, then permitted local Ollama `qwen3:1.7b`. The saved overview route starts with Gemini Flash-Lite, falls back to Groq, and uses concurrency 1 with a 65-second minimum gap. These settings are editable. Flash-Lite was selected after live connection checks; this is not a claim that it is more accurate than another model.

| Live check | Observed result |
| --- | --- |
| BSA overview | 8/8 topics processed, zero generation failures; five Gemini sections and three Groq sections. Groq took over when Gemini reached its configured cap. Total 472.8 seconds including pacing. |
| Cached rebuild | All eight topics reused in 6.5 seconds; shared ledger request count stayed at 29. |
| Broad Ask question | Groq produced three statements with all eight retrieved excerpts retained. Model call: 3.911 seconds; full request including retrieval and source checks: 30.02 seconds. No unknown citation IDs. |
| Focused factual question | Groq returned a valid missing-evidence response. Model call: 3.455 seconds; full request: 22.38 seconds. The model reported that the supplied excerpts did not establish the requested framework. |
| Preservation | Indexed content counts were unchanged during deployment; existing encrypted credential files match the pre-change backup. |

The Ask tests found and fixed two integration defects: a byte estimate rejected an eligible Groq request (9,263 estimated tokens became 7,836 with local model tokenization, retaining all evidence), and Groq rejected overlapping factual-answer union branches. The latter now uses distinct transport wrappers while preserving original branch and citation constraints. Unsupported output is still rejected.

Validation completed: full backend suite **1,085 passed** before the final Ask corrections; **147 focused provider, quota, monitoring, conversation and answer-quality tests passed** after those corrections. The full frontend suite passed **105 tests**, with **33 navigation/conversation/loading tests** rerun after the loading-text change. Production build and dependency consistency checks passed. Reports and content-free runtime metadata are in `../outputs/llm-router-2026-10-27/`, including `backend-private-github-full.xml`, `final-ask-routing-regression.xml`, `frontend-private-github.xml`, `bsa-live-verification.json`, `bsa-cached-verification.json`, `bsa-ask-verification.json` and `bsa-focused-verification.json`.

Remaining limits: two overview topics lack sufficient setup/runtime evidence; seven repository files were skipped by existing scan limits. No human correctness scores were entered and no controlled accuracy comparison is claimed. At the time of those smoke tests Jira/Slack had no cloud approval and Ollama was unreachable. The later source-scope recovery below supersedes that Jira/Slack configuration. Local folders and conversation history still require local inference. Office HTTPS rollout remains pending at the owner's earlier request.

For monitoring, use `data/logs/activity.jsonl` (or the signed-in member's own workspace equivalent). It records routing, fallback, quota decisions, request/job progress and timing with bounded rotation; keys, prompts and source excerpts are excluded.


## Jira/Slack source-scope recovery

On 27 October the owner explicitly approved BSA_chatbot Jira ticket and Slack message excerpts for Gemini and Groq, superseding the earlier local-only choice. The new per-project source scopes preserve GitHub-only behavior for old approvals and leave other projects/accounts unchanged. Source access, freshness, key-bound free-plan confirmation, provider selection, schema/evidence validation and all configured quotas remain enforced. Revoking source scope during generation withholds the answer.

The overview now has a **Retry failed topics** button beside partial coverage. Pacing waits after the previous generation finishes, preventing variable access-check delays from collapsing the intended interval between charged requests. Completed topics are cached; source, permission or model changes can invalidate reuse. A generation failure continues to retain retrieved excerpts.

Validation for this recovery: **111 backend tests passed** across routing, quotas, source scopes, source access, revocation, resumable generation, cancellation, workspace isolation and monitoring. The frontend suite had 109 passes and one new test fixture failure; correcting its simulated busy status yielded 9/9 overview tests, covering all **110 frontend tests** successfully. The production build passed. The BSA permission update passed current GitHub/Jira/Slack access checks. Live rebuild results are recorded separately after completion; these checks do not establish factual accuracy.
