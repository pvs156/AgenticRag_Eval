# Dispute & Scam Resolution Assistant
### Agentic RAG with evaluation-gated deployment (DeepEval, Langfuse, Promptfoo)

Status: planning. Nothing is built yet. Written 2026-10-09.
Evidence labels: **[V]** verified by me directly, **[S]** reported by a secondary source (trade press, law firm, vendor), **[U]** unverified or conflicting. Verify every **[S]** and **[U]** item against primary sources before the knowledge base depends on it.

---

## 1. Problem statement

When a customer says "I don't recognize this charge", "the merchant won't refund me", "I was tricked into sending money", or "my AI shopping agent bought the wrong thing", a bank must decide which rules apply, what deadlines run, what the customer is entitled to, and what happens next. A wrong or evasive answer is a compliance and trust problem, not just a bad customer experience.

### 1.1 Why this is a real, current problem

**Chatbots can cause harm in consumer finance.**
- The CFPB's June 2023 issue spotlight on chatbots flagged inaccurate answers and "doom loops" (repetitive replies with no path to a human) as core risks. [S] Summaries: [Orrick](https://www.orrick.com/en/Insights/2023/06/Artificial-Intelligence-Chatbots-May-Pose-Risks-for-Financial-Institutions-CFPB-Says), [American Banker](https://americanbanker.com/news/cfpb-warns-banks-about-poorly-deployed-chatbots-impeding-consumers). The primary report should be pulled from the CFPB site.

**Disputes are a leading complaint topic in public CFPB data.**
- The CFPB Consumer Complaint API is live and returned records through 2026-10-08. [V] ([API](https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/))
- For credit cards, the top issue is "Problem with a purchase shown on your statement" (58,900 complaints in my query); "Problem with a company's investigation into an existing problem" (22,605) is also in the top five. For checking/savings, "Problem with a lender or other company charging your account" had 25,776. [V, but counts may ignore my date filter and the share with narrative text is unknown; re-verify before quoting.]

**Deadlines drive the work (rules to confirm from primary text).**
- Reg E (debit/electronic transfers): investigation generally 10 business days, extendable to 45; provisional-credit and longer windows for some transaction types. [S, vendor guides]
- Reg Z (credit cards): billing-error acknowledgment in 30 days, resolution within two billing cycles. [From general knowledge, unverified.]
- Card network chargeback windows (commonly ~120 days). [S]
- Source for the regulation text: eCFR API (confirmed reachable). [V]

**New 2026 pressures.**
- *Agentic commerce liability gap.* Mastercard Agent Pay (2025-04-29) and Visa Intelligent Commerce (2025-04-30) provide credential/authentication rails, not dispute frameworks. [S] Who pays when an agent buys the wrong thing is described as unresolved; merchants currently absorb most loss. [S] ([Forkast](https://forkast.news/the-agentic-commerce-liability-gap-who-pays-when-the-agent-buys-wrong/), [Worldpay](https://www.worldpay.com/en/insights/articles/agentic-commerce-liability-is-still-being-written)). A September 2026 bank-coalition report warned AI shopping agents outpace fraud protections ([Quartz](https://qz.com/banks-ai-shopping-agents-fraud-privacy-risks-092226)). [S]
- *APP (authorized push payment) scams.* Reported US losses are described as tripling since 2022 ([Proof](https://www.proof.com/blog/the-fraud-files-bank-insiders-bec-billions-and-the-ai-threat-to-ach-payments-may-2026)). [S] The UK has had a mandatory reimbursement scheme since October 2024. [S] A December 2024 CFPB proposal on EFTA liability for fraud-induced payments exists; whether it was finalized is unknown. [U]
- *Regulators exclude GenAI from model-risk guidance.* The April 17, 2026 interagency model risk guidance (OCC Bulletin 2026-13, Fed SR 26-2) explicitly excludes generative and agentic AI, with a request for information expected ([Orrick](https://www.orrick.com/en/Insights/2026/04/Agencies-Overhaul-Model-Risk-Management-Guidance-for-Banks-Heres-What-Changed), [Sullivan & Cromwell](https://www.sullcrom.com/insights/memo/2026/April/OCC-Fed-FDIC-Issue-Revised-Guidance-Model-Risk-Management)). [S] Banks therefore need their own evidence of control; continuous evaluation, audit trails and human escalation are how a team would show it.

**Claims I could not confirm (do not put into the knowledge base without a primary source):**
- A January 2026 CFPB advisory saying Reg Z dispute rights survive delegation to an agent. [U]
- Mastercard introducing agent-specific dispute categories ("unauthorized agent behavior", "delegation disputes"). [U, sources conflict]
- American Express "Agent Purchase Protection" (April 2026) and Visa's tightened merchant dispute threshold (1.5% from 2026-04-01). [U]

### 1.2 The gap this project addresses

An assistant that handles these claims must (a) route correctly between regimes, (b) compute deadlines exactly, (c) cite rules faithfully, (d) say "this is unsettled, here is the path" instead of inventing a rule, (e) never promise outcomes, (f) escalate to a human instead of looping, and (g) leave an auditable trace of every decision. Most demos only measure answer fluency; this project measures the above.

---

## 2. Proposed solution

One agentic RAG assistant that triages four claim types and routes each to the right rules.

| Claim type | Rules involved | What evaluation checks |
|---|---|---|
| Unauthorized card/debit charge | Reg Z / Reg E, network rules | Correct regime, correct deadlines |
| Merchant/purchase dispute | Reg Z billing errors, chargeback rules | Eligibility, evidence checklist |
| Scam (APP) report | Reg E and CFPB position; UK scheme as reference | Handling of "you authorized it", tone, escalation |
| Agent-initiated purchase dispute | Existing rules where they apply; explicit "unsettled" handling where they do not | Abstains and escalates instead of inventing rules |

### 2.1 Architecture

```
User ─▶ API (FastAPI) ─▶ Input guardrails (PII redaction, injection check)
                              │
                       LangGraph agent
 classify claim ─▶ retrieve ─▶ rerank ─▶ generate ─▶ verify ──pass──▶ answer + citations
        │             ▲                                 │fail
        │             └─── rewrite / widen / regen ◀── diagnose (max 2 retries, else abstain)
        ├─▶ deadline calculator (deterministic, tested code, not LLM)
        └─▶ tools (mock): open dispute case, block card, human handoff
                              │
              OTel traces ──▶ Langfuse (live)      DeepEval (offline evals + CI gate)
```

Design principles:
- Deadlines and regime math are **code**, not model output.
- Bounded retries (max 2), then abstain or hand off. No doom loops: escalate within N turns.
- Write actions (mock card block, open case) require explicit confirmation.
- Every step is a trace span, so a regulator-style replay of decisions is possible.
- Public documents and synthetic data only. Never real customer data. Explicit disclaimer: not financial advice, lab project.

### 2.2 Knowledge base (all public)
- Regulation text via eCFR: Reg E (12 CFR 1005) and Reg Z (12 CFR 1026).
- CFPB guidance and public bank dispute policies.
- Network dispute and agent-payment documentation, only where publicly accessible.
- Each document records its source URL and retrieval date, since rules in this area are changing.

### 2.3 Frameworks and roles

| Concern | Tool | Role |
|---|---|---|
| Live tracing, cost/latency, sampled online scoring, human annotation queue | **Langfuse** | Production observability and review |
| Offline evals, metrics (faithfulness, context recall, custom policy rubrics, multi-turn), CI gate | **DeepEval** (primary) | pytest-style tests; run files and a committed baseline form the release record |
| Optional extra retrieval metrics | **Ragas** | Only if DeepEval lacks a needed metric |
| Red-team and prompt regression | **Promptfoo** (optionally garak) | Injection, jailbreak, policy-violation probes |
| Metrics and alerts | **Prometheus + Grafana** | Retry rate, abstain rate, escalation rate, p95 latency, token cost |
| Packaging and CI/CD | **Docker, GitHub Actions** | Smoke eval on PRs, full eval on merge, gated promotion |

Instrument once with OpenTelemetry (or the Langfuse SDK) and send to Langfuse; confirm current LangGraph support. MLflow was dropped by the owner on 2026-10-09: it stores runs but computes no metrics, and git plus Langfuse cover the record.

---

## 3. Evaluation plan (the interview centerpiece)

Golden set: about 80 cases, seeded from real public CFPB complaint narratives where available, hand-checked, plus synthetic agent-commerce and scam cases. Include cases that should abstain, escalate, or be refused.

| Dimension | Metric | Method |
|---|---|---|
| Regime classification | Accuracy | Exact match |
| Deadline correctness | Exact match | Deterministic, no judge |
| Faithfulness to rules | Faithfulness, citation accuracy | DeepEval / Ragas judges |
| Retrieval | Context recall / precision | Ragas / DeepEval |
| Unsettled-question handling | Abstain-and-escalate rate | Labeled cases |
| No promised outcomes / no financial advice | Policy violation rate | Custom scorer + Promptfoo |
| Doom-loop avoidance | Turns to human offer | Scenario tests |
| Tool use | Correct tool, args, confirmation | Trace assertions |
| Safety | Injection / jailbreak pass rate | Promptfoo / garak, nightly |
| Healing loop value | Gain vs no-retry baseline; added latency and cost | A/B eval runs (DeepEval), compared via run files and Langfuse |

Judge calibration: compare the LLM judge against about 30 human-labeled examples before it gates anything.

---

## 4. Deployment and monitoring (learning goals)

1. Containerize: multi-stage Dockerfile, non-root user, health checks, pinned dependencies.
2. Compose stack: API, vector DB, Langfuse (or cloud free tier), Prometheus, Grafana.
3. CI/CD: GitHub Actions runs lint, unit tests (deadline logic), smoke eval on PRs and the full eval suite on merge; promotion blocked when scores fall below baseline.
4. Deploy to a VM with HTTPS reverse proxy, secrets management, and backups.
5. Monitor: dashboards and alerts for quality, latency, cost, abstain/escalation rates.
6. Feedback loop: sampled live scoring; low-scoring traces go to a Langfuse annotation queue; reviewed failures are promoted into the golden set.

### 4.1 Zero-to-$10 budget plan
Estimates from general knowledge; verify current free-tier terms at signup.

| Need | Option |
|---|---|
| Embeddings, vector DB | Local open embedding model plus Qdrant or Chroma ($0) |
| Generator LLM | Free-tier API (Gemini or Groq) or local model via Ollama |
| Judge LLM | Cheap paid model for golden-set runs; main use of the $5 to $10 budget |
| Hosting | Free cloud VM tier if obtainable, else roughly $5/month VPS |
| CI/CD, registry | GitHub Actions and GHCR (free for public repos) |
| Monitoring | Self-hosted Prometheus and Grafana ($0) |
| Langfuse | Self-hosted needs more RAM (ClickHouse, Postgres, Redis); fall back to Langfuse cloud free tier if the VM is too small |

---

## 5. Build phases

1. Corpus: ingest eCFR regulations and public guidance; build and unit-test the deadline calculator.
2. Golden set: ~80 cases from CFPB complaints plus synthetic ones; hand-check a subset.
3. Baseline RAG and baseline eval scores.
4. Instrumentation: tracing to Langfuse; dashboards.
5. Agentic upgrade: claim classifier, verifier, bounded retries, abstention, escalation; compare to baseline.
6. Tools and safety: guardrails, confirmation on write actions, red-team scans.
7. CI gate and containerized deployment with monitoring.
8. Live loop: sampled scoring, annotation queue, failures promoted to golden set.
9. Demo: introduce a deliberate regression (bad prompt or weaker embedding) and show CI blocking it; show a production failure caught and added to the dataset.

## 6. Interview talking points
- Why deadlines are code and judgment is model: reliability where rules are exact.
- How abstention is measured when ground truth does not exist (agent-initiated disputes).
- Why GenAI being excluded from the 2026 model-risk guidance makes continuous evaluation and audit trails the control evidence (verify against the primary guidance first).
- Evaluation-gated deployment: a regression blocked in CI, a production failure turned into a test.
- Cost discipline: running the whole stack for $0 to $10.

## 7. Open decisions
1. Scope: all four claim types, or start with a subset (e.g. unauthorized + scam)?
2. Hosting: free VM attempt, or paid VPS (~$5/month)?
3. LLM: any provider restrictions? Free-tier generator acceptable?
4. ~~Dual Langfuse + MLflow~~ Resolved 2026-10-09: DeepEval primary, Langfuse for live, MLflow dropped.

## 8. Sources
- [CFPB Consumer Complaint API](https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/)
- [Orrick on CFPB chatbot report](https://www.orrick.com/en/Insights/2023/06/Artificial-Intelligence-Chatbots-May-Pose-Risks-for-Financial-Institutions-CFPB-Says)
- [American Banker on CFPB chatbot warning](https://americanbanker.com/news/cfpb-warns-banks-about-poorly-deployed-chatbots-impeding-consumers)
- [Forkast: agentic commerce liability gap](https://forkast.news/the-agentic-commerce-liability-gap-who-pays-when-the-agent-buys-wrong/)
- [Worldpay: agentic commerce liability](https://www.worldpay.com/en/insights/articles/agentic-commerce-liability-is-still-being-written)
- [Quartz: banks warn AI shopping agents outpace fraud protections](https://qz.com/banks-ai-shopping-agents-fraud-privacy-risks-092226)
- [Proof: Fraud Files, May 2026](https://www.proof.com/blog/the-fraud-files-bank-insiders-bec-billions-and-the-ai-threat-to-ach-payments-may-2026)
- [24/7 Wall St: "you authorized it" scams](https://247wallst.com/personal-finance/2026/09/30/banks-say-you-authorized-it-the-ai-scam-that-costs-victims-everything/)
- [Orrick: revised model risk guidance, April 2026](https://www.orrick.com/en/Insights/2026/04/Agencies-Overhaul-Model-Risk-Management-Guidance-for-Banks-Heres-What-Changed)
- [Sullivan & Cromwell: model risk guidance](https://www.sullcrom.com/insights/memo/2026/April/OCC-Fed-FDIC-Issue-Revised-Guidance-Model-Risk-Management)
- [Lyzr: dispute management playbook](https://www.lyzr.ai/playbook/bfsi-guide-to-dispute-management/)
- Frameworks: [Langfuse](https://github.com/langfuse/langfuse), [DeepEval](https://github.com/confident-ai/deepeval), [Ragas (optional)](https://github.com/vibrantlabsai/ragas), [Promptfoo](https://github.com/promptfoo/promptfoo), [garak](https://github.com/NVIDIA/garak)
- Reference repos: [agentic-rag-for-dummies](https://github.com/GiovanniPasq/agentic-rag-for-dummies), [production_rag](https://github.com/rajarshidattapy/production_rag)