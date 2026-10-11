# Dispute & Scam Resolution Assistant

An agentic RAG assistant for bank customers with card and account disputes, scam reports, and purchases made by AI shopping agents.

- **Grounded:** every answer rests on the official text of Regulation E and Regulation Z.
- **Exact deadlines:** they are computed by tested code, never by the model.
- **Gated releases:** a DeepEval-style eval suite runs on every pull request.
- **Monitored:** Langfuse traces and scores live traffic, and Prometheus and Grafana track the service.

> Demonstration project. Not financial or legal advice. Uses public regulation text only; never enter real account details.

Specs: [PID](docs/01_PID.md) · [tech spec](docs/02_TECH_SPEC.md) · [design spec](docs/03_DESIGN_SPEC.md) · Results: [evals/RESULTS.md](evals/RESULTS.md) · Deploy: [deploy/README.md](deploy/README.md)

## Why it exists

- **Volume.** Disputes are a top consumer complaint. Since October 2025 the CFPB database holds:
  - 23,800 credit-card complaints about a card company not resolving a purchase dispute;
  - 10,236 checking-account complaints about unauthorized transactions;
  - 11,294 money-transfer fraud and scam complaints.

  Source: [`evals/datasets/cfpb_taxonomy.json`](evals/datasets/cfpb_taxonomy.json).
- **Regulator concern.** The CFPB has warned that bank chatbots give inaccurate answers and trap customers in loops with no route to a human.
- **New 2026 questions.** Who pays when an AI agent buys the wrong thing is unsettled. The assistant must say so instead of inventing a rule.

## How a turn works

```
message ─▶ guard_in (PII redaction, injection / human-request / urgency detection)
        ─▶ understand (deterministic patterns first; the LLM fills gaps; dates and card type must be grounded)
        ─▶ route ──▶ refuse (out of scope, injection) | hand off (asked for a person, non-US)
        ─▶ rules (deterministic: regime, deadlines, liability, missing facts) ──▶ ask (max 2 rounds)
        ─▶ retrieve (anchored on the engine's citations + hybrid search: bge-small/Qdrant + BM25, rerank)
        ─▶ explain (LLM writes the plain-language part only)
        ─▶ verify (no invented dates, citations must be in sources, no promises, says "unsettled" when it is)
             └─ fail ─▶ repair (max 2 retries) ─▶ safe fallback with handoff
        ─▶ finalize (templated key dates, liability, handoff offer, disclaimer, mock actions needing confirmation)
```

## Repository layout

```
app/            rules engine, agent graph, retrieval, LLM client, guardrails, API, observability, store
corpus/         eCFR sources (pinned date) and processed chunks with legal citations
evals/          golden (45) and held-out (16) sets, scorers, DeepEval judge, gate, reports, red-team config
web/            Next.js front end (chat, sources, key dates, confirm dialogs, interviewer view)
deploy/         Caddy, Prometheus rules, Grafana dashboard-as-code, VM scripts, runbook
.github/        CI (tests, front end, eval gate, images), deploy (manual approval), nightly (full eval, red team)
```

## Quick start (local, $0)

```bash
python -m venv .venv && .venv/Scripts/activate        # Windows; use bin/activate elsewhere
pip install -e ".[dev]"
cp .env.example .env                                    # defaults to a local Ollama model
ollama pull qwen2.5:1.5b
python -m app.rag.ingest                                # fetch + chunk the regulations (pinned date)
python -m evals.datasets.build_golden                   # golden + held-out sets, cross-checked with the engine
pytest                                                  # 100+ tests, no models or network needed
uvicorn app.api.main:app --port 8000                    # API
npm --prefix web install && npm --prefix web run dev    # UI at http://localhost:3000
python -m evals.run_eval --system agent --suite smoke   # eval run; gate with: python -m evals.gate <run file>
```

## Verified rules (eCFR text as of 2026-10-07)

| Rule | Value | Source |
|---|---|---|
| Debit: customer reports error | 60 days after statement sent | 12 CFR 1005.11(b)(1) |
| Debit: bank investigates | 10 business days (20 for new accounts) | 1005.11(c)(1), (c)(3)(i) |
| Debit: extended investigation with provisional credit | 45 days; 90 for POS debit, foreign, new accounts | 1005.11(c)(2), (c)(3)(ii) |
| Debit: lost card liability | $50 if reported within 2 business days, else up to $500 | 1005.6(b)(1)-(2) |
| Debit: fraud-obtained credentials | transfer is unauthorized | Supp. I comment 2(m)-3 |
| Credit: billing error notice | written, within 60 days of statement | 1026.13(b)(1) |
| Credit: issuer acknowledges / resolves | 30 days / 2 billing cycles, max 90 days | 1026.13(c) |
| Credit: unauthorized use liability | lesser of $50 or amount before notice | 1026.12(b)(1)(ii) |
| Credit: quality disputes on accepted goods | not a billing error; claims and defenses route | Supp. I 13(a)(3)-1.ii, 1026.12(c) |

Business days assume Monday to Friday excluding Federal Reserve holidays. The regulation lets each bank define its own business days (1005.2(d)), and every answer says so.
