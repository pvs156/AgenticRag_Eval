# Technical Specification
**Project:** Dispute & Scam Resolution Assistant | **Version:** 0.1 draft | **Date:** 2026-10-09
Related: [PID](01_PID.md), [Design spec](03_DESIGN_SPEC.md)

Version numbers are intentionally unpinned here; pin them at build time and record them in `pyproject.toml` / lockfiles. Library API names below are from general knowledge and must be checked against current docs when implemented.

---

## 1. Technology stack

| Layer | Choice | Why / alternative |
|---|---|---|
| Language | Python 3.12 | Ecosystem for all eval tools |
| API | FastAPI + Uvicorn | Async, typed, easy health/metrics endpoints |
| Agent orchestration | LangGraph | Explicit state graph: retries, branches, handoff |
| LLM access | Thin provider interface (own wrapper, optionally LiteLLM) | Swap free-tier / local / paid without code change |
| Embeddings | Local open model (e.g. bge-small class) via fastembed or sentence-transformers | $0, runs on CPU |
| Vector store | Qdrant (container) | Hybrid-friendly, lightweight; alt. Chroma |
| Lexical search | BM25 (rank_bm25 or Qdrant sparse) | Rule text is keyword-heavy (section numbers) |
| Reranker | Small cross-encoder (CPU) | Quality lift; optional behind flag |
| Relational store | SQLite (dev) / Postgres (compose) | Case records, audit events |
| Tracing | OpenTelemetry SDK (or Langfuse SDK) exporting to Langfuse | One instrumentation, one backend; OTel keeps it portable |
| Live observability and review | Langfuse (cloud free tier default; self-host stretch) | Trace-linked scores, annotation queue |
| Evaluation framework and release gate | **DeepEval** (primary): pytest-style tests, built-in and custom (G-Eval style) metrics, multi-turn/agent metrics | One framework for offline evals and the CI gate. MLflow was considered and dropped (owner decision, 2026-10-09): it added a service without adding a metric. |
| Run records and baseline | JSON result files per run in `evals/runs/` (CI artifacts), a committed `evals/baseline.json`, and Langfuse datasets/experiments for run comparison | Git history is the version ledger; no extra server |
| Optional second metric source | Ragas | Only if DeepEval lacks a needed retrieval metric; not a default dependency |
| Red-team | Promptfoo (CI), garak (nightly, optional) | Injection / policy probes |
| Metrics | Prometheus client + Prometheus + Grafana | Retry/abstain/escalation, latency, cost |
| Frontend | Next.js (App Router) + React + TypeScript, Tailwind CSS, `output: 'standalone'` | Chosen by owner; also demonstrates front-end skills. Served as its own container |
| Frontend tests | Vitest + React Testing Library; Playwright for one end-to-end smoke test; axe for accessibility checks | Keeps the UI honest without heavy effort |
| Packaging | Docker (multi-stage), docker compose | Reproducible |
| CI/CD | GitHub Actions + GHCR | Free for public repos |
| Reverse proxy / TLS | Caddy | Automatic HTTPS, simple config |
| Secrets | `.env` locally; GitHub Actions secrets; VM env file with restricted perms | No secrets in git |
| Lint/test | ruff, mypy (selective), pytest, pre-commit | Quality gates |

## 2. Repository layout
```
dispute-assistant/
  app/
    api/            # FastAPI routes, schemas
    agent/          # LangGraph graph, nodes, state, prompts
    rag/            # ingestion, chunking, retrieval, rerank
    rules/          # deadline + regime engine (pure functions)
    tools/          # mock tools: open_case, block_card, handoff
    guardrails/     # PII redaction, injection checks, output policy
    llm/            # provider interface, spend cap, cache
    obs/            # OTel setup, Prometheus metrics, score writers
    config.py
  web/              # Next.js app (see 3.12)
    app/            # routes: /, /interviewer, /api/chat (BFF proxy)
    components/     # Chat, MessageList, SourcesPanel, WhyPanel, ConfirmDialog, HandoffButton, Feedback
    lib/            # API client, types shared with backend schema
    Dockerfile
  corpus/
    sources.yaml    # provenance: url, retrieved_at, sha256, license
    raw/ processed/
  evals/
    datasets/       # golden.jsonl, calibration.jsonl
    scorers/        # deterministic + judge scorers
    run_eval.py     # offline runner (DeepEval); writes runs/<sha>.json
    runs/           # per-run results (gitignored; CI artifacts)
    baseline.json   # committed reference scores for the gate
    promptfoo/      # red-team config
    thresholds.yaml
  tests/            # unit, integration, scenario
  deploy/
    docker/ compose/ caddy/ prometheus/ grafana/
  .github/workflows/
  docs/
```

## 3. Component specifications

### 3.1 Corpus ingestion
- Sources recorded in `sources.yaml` with: id, title, URL, publisher, retrieved_at, sha256, status (`primary` | `secondary`), claim types served.
- **Provenance gate:** only `primary` documents are indexed. Secondary sources (trade press, law-firm summaries) are used for background in docs, not retrieval.
- Initial primary sources: Reg E (12 CFR Part 1005) and Reg Z (12 CFR Part 1026) via the eCFR API (reachability verified 2026-10-09); CFPB guidance pages; any public network or bank dispute documentation actually accessible.
- Chunking: by legal structure (section / paragraph), preserving citation identifiers (e.g. `12 CFR 1005.11(c)`); target 200 to 500 tokens, with parent-section metadata.
- Metadata per chunk: `source_id, citation, section_path, regime (E|Z|network|guidance), effective_date, retrieved_at`.
- Re-ingestion is idempotent; changed hash produces a new corpus version tag (recorded in every eval run file and as a Langfuse trace attribute).

### 3.2 Retrieval
- Hybrid: dense + BM25, fused (reciprocal rank fusion), top-k 20, rerank to 5.
- Filter by `regime` when the classifier is confident; widen when not.
- Output: chunks with citation ids; the generator may cite only returned ids (enforced in verification).

### 3.3 Rules engine (`app/rules/`, deterministic, no LLM)
Pure functions with unit tests and property tests.

Inputs: `account_type` (debit | credit | prepaid | other), `transaction_type`, `claim_type`, `dates` (transaction, statement, report), `account_age`, `jurisdiction=US`.

Outputs: `regime`, `applicable_provisions[]` (citations), `deadlines[]` (name, date, basis citation), `liability_notes[]`, `confidence`, `needs_human: bool`, `unsettled: bool`.

Rule tables to be populated from primary text in Phase 1. Starting hypotheses **from general knowledge, to be verified against eCFR before use**:
- Reg E error resolution (12 CFR 1005.11): consumer notice generally within 60 days of the statement; institution investigates within 10 business days, may extend up to 45 days if provisional credit is given; up to 90 days for certain cases (new accounts, point-of-sale, foreign-initiated). Consumer liability tiers for unauthorized transfers (12 CFR 1005.6) depend on how quickly the loss is reported.
- Reg Z billing errors (12 CFR 1026.13): notice within 60 days of statement; creditor acknowledges within 30 days; resolves within two billing cycles, not over 90 days. Unauthorized-use liability limit (12 CFR 1026.12).
- Network chargeback windows: not encoded unless a primary public source is found.
- `unsettled=true` for agent-initiated disputes where no primary rule exists; the agent must say so.

Dates use business-day calendars (US federal holidays) via a tested helper; timezone-naive dates only.

### 3.4 Agent graph (LangGraph)
State (typed): `messages, claim_type, account_facts, missing_fields[], regime, retrieved[], draft, verification, retries, turns_unresolved, escalate, case_id`.

Nodes:
1. `guard_in`: PII redaction (mask card numbers, SSN patterns), injection heuristic.
2. `classify`: LLM + rules hints -> claim type, regime candidates, missing intake fields. Low confidence -> ask a clarifying question (max 2) or hand off.
3. `intake`: collects missing facts (dates, amount, account type, whether the customer made/approved the payment). No retrieval until minimum facts exist, except for general questions.
4. `rules`: call rules engine with facts.
5. `retrieve` -> `rerank`.
6. `generate`: answer plan constrained to retrieved citations and rules-engine outputs.
7. `verify`: deterministic checks first (citation ids exist, deadlines match rules engine, no banned phrases), then LLM judge (faithfulness).
8. `diagnose`: on failure, classify cause (RETRIEVAL | CONTEXT | GENERATION | CITATION | FACTS_MISSING).
9. `repair`: rewrite query / widen k / regenerate with repair prompt / ask user. **Max 2 retries**, then `abstain`.
10. `abstain_or_handoff`: structured handoff packet to a human (summary, facts, rules output, citations, reason).
11. `tools`: mock `open_case`, `block_card`; **write actions require explicit user confirmation** in a prior turn.
12. `guard_out`: output policy (no outcome promises, no personalized financial advice, disclaimer, PII scrub).

Termination: answer delivered, handoff, or clarifying question. `turns_unresolved >= 3` forces a handoff offer (anti doom-loop).

### 3.5 LLM layer
- Interface: `generate(messages, schema?, tier)` with `tier in {generator, judge}`.
- Features: retry with backoff, timeout, response cache (hash of prompt+model) for evals, token/cost accounting, **hard spend cap** (env `JUDGE_BUDGET_USD`), model names only from config.
- Structured outputs validated with Pydantic; invalid -> one repair attempt -> fail closed (handoff).

### 3.6 API contract (v1)
- `POST /v1/chat` `{session_id?, message}` -> `{session_id, reply, citations[], state:{claim_type, regime, deadlines[], unsettled}, handoff:{offered:bool, reason?}, trace_id}`
- `POST /v1/confirm` `{session_id, action_id, confirm:bool}` -> action result (mock)
- `POST /v1/feedback` `{trace_id, rating, comment?}` -> writes a Langfuse score
- `GET /healthz` (liveness), `GET /readyz` (deps), `GET /metrics` (Prometheus)
- Rate limiting per IP; request size caps; no auth for demo (see 8), simple shared-token header recommended.

### 3.7 Data model (Postgres/SQLite)
`sessions`, `messages` (redacted), `cases` (mock), `audit_events` (append-only: timestamp, session, node, decision, tool call, trace_id), `feedback`. Retention: demo data auto-purged after 30 days. No real PII is accepted by design; redaction runs before persistence.

### 3.8 Observability
Instrument once with OpenTelemetry (or the Langfuse SDK/LangChain callback if OTel support for LangGraph proves awkward); export to Langfuse. Verify current integration details at build time.

Span names: `agent.guard_in, agent.classify, agent.rules, rag.retrieve, rag.rerank, agent.generate, agent.verify, agent.repair, agent.handoff, tool.<name>`.
Attributes: `claim_type, regime, retries, abstained, escalated, unsettled, corpus_version, model, prompt_version, tokens_in/out, cost_usd`.

Scores written to traces: `faithfulness`, `citation_valid`, `deadline_match`, `policy_violation`, plus user feedback.
Online scoring: sample rate configurable (default 10%), judge budget respected.

Prometheus metrics: `requests_total{claim_type}`, `latency_seconds` histogram, `retries_total`, `abstain_total`, `handoff_total`, `llm_tokens_total{tier}`, `llm_cost_usd_total`, `judge_errors_total`.
Alerts: p95 latency, error rate, abstain-rate spike, retry-rate spike, cost-rate, faithfulness drop (from sampled scores).

### 3.9 Evaluation system
**Datasets** (`evals/datasets/*.jsonl`), fields: `id, claim_type, user_turns[], facts, expected_regime, expected_deadlines, must_cite[], must_abstain, must_escalate, forbidden[], source (cfpb|synthetic), notes`.
Composition (~80): unauthorized 20, merchant 15, scam 20, agent-initiated 15, adversarial/refusal 10. CFPB-seeded cases use public narratives, paraphrased and stripped of identifying details.

**Scorers**
- Deterministic: regime accuracy, deadline exact match, citation validity (ids exist in retrieved set), forbidden-phrase check, tool-call/confirmation assertions, turns-to-handoff.
- Judge-based (DeepEval/Ragas): faithfulness, answer relevancy, context recall/precision; custom rubric for "unsettled handled correctly" and "no outcome promise".
- Judge calibration: ~30 human-labeled examples; report agreement; judge gates only after acceptable agreement (target >= 80%, to be reviewed).

**Runs**
- `run_eval.py --suite smoke|full --candidate <version>` runs the dataset through the assistant with DeepEval, then writes `evals/runs/<git-sha>.json`: params, per-case results, aggregate metrics, corpus version, prompt version, model names, cost. The same results are pushed to a Langfuse dataset run so runs can be compared in its UI (verify the current datasets/experiments API at build time).
- DeepEval test files (`tests/evals/test_*.py`) wrap the metrics as assertions so `deepeval test run` or plain pytest produces the pass/fail used in CI. Deterministic checks (regime, deadlines, citation validity) stay plain pytest assertions; judge-based metrics use DeepEval metrics, with custom criteria metrics for policy rules ("no outcome promised", "unsettled handled correctly").
- Baseline = non-agentic RAG; candidate = agentic graph. Report delta, added latency and cost.
- `thresholds.yaml` defines gate rules: absolute floors and "no worse than `baseline.json` minus tolerance" per metric. Updating `baseline.json` requires a pull request with the run file attached, so the history of accepted baselines lives in git.

**Red-team**: Promptfoo config for injection, jailbreak, PII exfiltration, outcome-promise elicitation; runs in CI (small) and nightly (larger).

### 3.10 CI/CD
Workflows:
1. `pr.yml`: ruff, mypy (selective), unit tests (rules engine incl. property tests); web: lint, type-check, Vitest, build; build both images, `run_eval --suite smoke` (cached judge, ~20 cases), Promptfoo small suite. Fails on threshold breach.
2. `main.yml`: full eval; on pass, push image to GHCR tagged with git SHA; attach the run file as a release artifact; deploy step (SSH/compose pull) gated by a manual approval environment.
3. `nightly.yml`: garak/Promptfoo large suite, report artifact.
Eval gate compares the run file against `baseline.json` and `thresholds.yaml`; secrets only via Actions secrets; fork PRs do not receive secrets (smoke eval uses cached outputs or is skipped with a notice).

### 3.11 Containers and deployment topology
Images: `app` (multi-stage, slim, non-root, healthcheck), others from upstream images pinned by digest.

Routing: Caddy sends `/` to the `web` (Next.js) container; `web` calls `app` (FastAPI) over the internal network. FastAPI is not exposed publicly. Grafana sits behind Caddy on a separate path or subdomain with authentication.

Compose services: `caddy`, `web`, `app`, `qdrant`, `postgres`, `prometheus`, `grafana`, (optional) `langfuse` stack. Resource limits per service; named volumes; restart policy `unless-stopped`; internal network, only Caddy exposed (80/443).

Host: single Linux VPS; firewall allowing 22 (key-only), 80, 443; automatic security updates; backups of Postgres, Qdrant snapshot and Grafana volumes to object storage or local rotated archive; restore test documented in the runbook.

Release: pull new image by SHA, `docker compose up -d`, health check, automatic rollback to previous SHA on failed `/readyz`.

### 3.12 Frontend (Next.js)
- **Structure:** App Router. Pages: `/` (chat), `/interviewer` (token-gated view with trace links and live scores). Components as listed in the repo layout; UI behavior is defined in the design spec, section 4.
- **BFF pattern:** the browser calls Next.js route handlers (`/api/chat`, `/api/confirm`, `/api/feedback`), which forward to the FastAPI service on the internal network. The shared demo token and any backend URLs stay server-side and never reach the browser. This also removes the need for CORS configuration.
- **Streaming:** the chat endpoint streams the reply (Server-Sent Events or a streamed fetch response) so the user sees text as it is generated; the final event carries citations, state, deadlines and `trace_id`. If streaming proves fragile through the proxy, fall back to a single JSON response; this is a feature flag, not a redesign.
- **Types:** a TypeScript type module mirrors the API schemas. Generate it from the FastAPI OpenAPI document in CI to prevent drift (tool choice at build time).
- **Rendering:** client components only where interactive (chat, dialogs); the shell and static content stay server-rendered. Escape all model output; render only a small markdown subset; never use `dangerouslySetInnerHTML` on model text.
- **State:** `session_id` kept in memory plus a cookie or `sessionStorage`; no real PII persisted client-side.
- **Quality gates:** TypeScript strict mode, ESLint, Vitest component tests (chat, sources panel, confirm dialog), one Playwright smoke test against the compose stack, axe accessibility checks on the main page, Lighthouse as an informational CI step.
- **Build and image:** multi-stage Dockerfile; `output: 'standalone'` for a small runtime image; non-root user; health check at `/api/health`. Expect roughly 150 to 300 MB RAM at idle, so set a memory limit in compose and verify on the chosen host.
- **Hosting choice:** self-hosted container behind Caddy by default, so the whole deployment (containers, proxy, TLS, monitoring) is yours to explain. Hosting only the frontend on a managed free tier is a fallback if the VPS is memory-constrained; it would add a cross-origin or public-API consideration and is not the default.
- **Telemetry:** basic web vitals and error reporting to the app's own metrics endpoint (or console in dev); no third-party analytics.

## 4. Non-functional requirements
| NFR | Target (initial) |
|---|---|
| Latency p95, single turn | <= 8 s without retries; <= 15 s with retries (free-tier LLM dependent) |
| Availability | Best effort; auto-restart; no SLA |
| Cost | Whole project $0 to $10; per-session cost logged |
| Privacy | No real PII; redaction before logging/persistence |
| Reproducibility | Pinned deps, corpus version tags, prompt versions, seed where possible |
| Auditability | Every decision traceable by `trace_id` and `audit_events` |
| Maintainability | Rules and prompts in versioned files, not inline strings |

## 5. Testing strategy
- Unit: rules engine (table-driven + property tests on business-day math), guardrails, citation validator.
- Integration: retrieval on a small fixture corpus; API contract tests.
- Scenario tests: scripted multi-turn conversations for doom-loop, confirmation-before-write, injection attempts.
- Eval suites: smoke (PR) and full (main), plus red-team.
- Chaos-lite: LLM timeout and invalid JSON paths must fail closed to handoff.

## 6. Configuration
Environment variables only (12-factor): provider keys, model names per tier, `JUDGE_BUDGET_USD`, sample rates, backend URLs, feature flags (`ENABLE_RERANK`, `ENABLE_HEALING`, `ENABLE_AGENT_CLAIMS`). Flags enable baseline vs candidate comparisons and phased claim types.

## 7. Versioning
- Prompts, rule tables and thresholds are versioned files; each eval run records git SHA, prompt version, corpus version, model names.
- Semantic version tags per release; image tag = git SHA.

## 8. Security
- No secrets in git (pre-commit secret scan); least-privilege tokens.
- Input: size limits, injection heuristics, output policy; mock tools only, with confirmation; no outbound calls from tools.
- Container hardening: non-root, read-only filesystem where possible, dependency scanning in CI.
- Demo access: shared token held server-side in the Next.js BFF (never in browser code) plus rate limiting to protect the free-tier quota. Security headers (CSP, frame-ancestors, referrer policy) set in Caddy or Next config; cookies `HttpOnly`, `Secure`, `SameSite`.
- Frontend supply chain: lockfile committed, `npm audit` (or equivalent) in CI, no secrets in `NEXT_PUBLIC_*` variables.
- Threat model summary: prompt injection to trigger tools, PII leakage in logs, quota exhaustion, outdated rule text served as current (mitigated by corpus date display in answers).

## 9. Known unknowns to resolve in Phase 0/1
1. Exact OTel/LangGraph export support for the Langfuse version in use, and the current Langfuse datasets/experiments API for pushing DeepEval results.
2. Which dispute/network documents are publicly accessible and licensable for indexing.
3. Free-tier LLM limits and terms at build time.
4. Whether the Langfuse self-host stack fits the chosen host.

---

## 10. As-built notes (2026-10-09)

The build in `dispute-assistant/` deliberately differs from this spec in these places:

| Spec said | As built | Why |
|---|---|---|
| Postgres for sessions/audit | SQLite on a Docker volume (`app/store.py`), nightly online backup | Single instance on a small VM; one less service. Swapping to Postgres touches only `store.py`. |
| ~80 golden cases | 45 golden + 16 held-out cases | Quality over count. The held-out set was written before the deterministic extractor and never used to tune it. |
| Golden set seeded from CFPB narratives | Hand-written cases mirroring real CFPB sub-issue volumes (`evals/datasets/cfpb_taxonomy.json`) | The CFPB API no longer returns narrative text (checked 2026-10-09). |
| LLM extracts all facts | Deterministic first pass (`app/agent/heuristics.py`); the LLM fills the gaps | The small local model misclassified intent often (measured); patterns are testable and free. |
| Streaming replies | Single JSON response with staged progress messages in the UI | The graph runs verification before anything is shown; streaming unverified text would defeat the verifier. The spec allowed this fallback. |
| MLflow | Removed (owner decision) | DeepEval plus run files plus Langfuse cover the record. |
| Ragas | Not used | DeepEval covers the needed metrics. |
| LLM | Local Ollama `qwen2.5:1.5b` for development; hosted free tier for deployment | `qwen3.5:4b` generated about 4 tokens/s on the dev laptop, too slow for evals. |
| Verified rule values | See README "Verified rules"; all checked against eCFR text as of 2026-10-07 | |
