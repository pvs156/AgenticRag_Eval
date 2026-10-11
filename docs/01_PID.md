# Project Initiation Document (PID)
**Project:** Dispute & Scam Resolution Assistant (agentic RAG, evaluation-gated deployment)
**Owner:** vpilla@inrhythm.com | **Version:** 0.1 draft | **Date:** 2026-10-09
Companion docs: [Project brief](00_PROJECT_BRIEF.md), [Tech spec](02_TECH_SPEC.md), [Design spec](03_DESIGN_SPEC.md)

Evidence labels used in the brief apply here: **[V]** verified, **[S]** secondhand, **[U]** unverified. Items marked **(ASSUMPTION)** are defaults I chose because the open decisions are unanswered; change them freely.

---

## 1. Purpose
Build, deploy and operate a live agentic RAG assistant for card and deposit dispute and scam triage, as a portfolio project for interviews. The deliverable is not only the assistant but the evidence around it: an evaluation suite, a CI quality gate, monitoring, and a documented deployment that the owner can explain end to end.

## 2. Background and problem
See the brief, section 1. In short: wrong or evasive answers on disputes create compliance and trust risk; the CFPB flagged chatbot inaccuracy and "doom loops" [S]; disputes are a leading complaint topic in public CFPB data [V]; 2026 adds the agentic-commerce liability gap [S] and rising authorized push payment (APP) scams [S]; GenAI is excluded from the April 2026 interagency model-risk guidance [S], so banks must evidence control themselves.

## 3. Objectives (SMART)
| # | Objective | Measure | Target |
|---|---|---|---|
| O1 | Correct routing between rule regimes | Regime classification accuracy on golden set | >= 90% |
| O2 | Exact deadline answers | Deadline exact-match on golden set | 100% (deterministic code) |
| O3 | Grounded answers | Faithfulness (judge) / citation accuracy | >= 0.85 / >= 90% (calibrate after baseline) |
| O4 | Safe handling of unsettled or out-of-scope questions | Abstain-and-escalate rate on labeled cases | >= 90% |
| O5 | No doom loops | Human handoff offered within N turns (N=3) when unresolved | 100% of scenario tests |
| O6 | No promised outcomes or advice | Policy violation rate | 0 on red-team suite |
| O7 | Evaluation-gated release | A deliberate regression is blocked by CI | Demonstrated once |
| O8 | Live, observable deployment | Public HTTPS endpoint + dashboards + alerts | Running >= 14 days |
| O9 | Low cost | Total spend | $0 to $10 |

Targets are initial; recalibrate once baselines exist.

## 4. Scope
**In scope**
- Claim types: unauthorized charge, merchant/purchase dispute, scam (APP) report, agent-initiated purchase dispute.
- RAG over public regulation and guidance text; deterministic deadline and regime logic; mock tools (open case, block card, human handoff).
- Tracing, offline and online evaluation, red-teaming, CI/CD, containerization, deployment, monitoring, feedback loop.
- Documentation sufficient to explain every component in an interview.

**Phasing (ASSUMPTION):** MVP = unauthorized + scam; then merchant disputes; then agent-initiated disputes.

**Out of scope**
- Real customer data, real bank integrations, real money movement, identity verification.
- Production compliance certification; legal advice. The system carries a visible "not financial or legal advice; demo" disclaimer.
- Fine-tuning models; voice channels; multi-tenant features.

## 5. Deliverables
1. Source repository (public, MIT or Apache-2.0).
2. Regulation corpus with provenance (URL, retrieval date, hash).
3. Deadline/regime engine with unit tests.
4. Agentic RAG service (FastAPI) and a Next.js/React chat front end with sources, "why this answer", confirm and feedback components (owner decision, 2026-10-09).
5. Golden dataset (~80 cases) and scorers; judge calibration set (~30 human-labeled).
6. CI/CD pipeline with evaluation gate.
7. Container images and compose stack; live deployment.
8. Dashboards (Grafana) and alert rules; Langfuse project.
9. Runbook, architecture diagram, evaluation report, interview talking-points sheet.

## 6. Success criteria / definition of done
- All objectives O1 to O9 met or consciously re-baselined with a written reason.
- A clean-clone `docker compose up` reproduces the stack locally.
- The deployed system survives a restart and restores from backup.
- Owner can explain, unaided, each box in the architecture diagram and each metric.

## 7. Stakeholders and roles
| Role | Who |
|---|---|
| Owner / builder / presenter | vpilla@inrhythm.com |
| Implementation assistant | Claude Code (pair-builds, writes code and docs) |
| Intended audience | Interviewers; InRhythm / Arula colleagues |

## 8. Assumptions and constraints
- **(ASSUMPTION) Hosting:** one small VPS (~$5/month class) or a free cloud VM if obtainable. Free-tier terms must be re-checked at signup.
- **(ASSUMPTION) LLMs:** provider-agnostic interface; free-tier generator (e.g. Gemini or Groq) or local Ollama; a cheap paid model as judge for golden-set runs.
- **(ASSUMPTION) Embeddings:** local open model, no API cost.
- **Evaluation and observability (owner decision, 2026-10-09):** DeepEval is the primary evaluation framework and CI gate; Langfuse handles live traces, scoring and run comparison. MLflow is dropped. Langfuse cloud free tier by default because self-hosting needs more memory than a small VPS offers; self-host is a stretch goal. Ragas is optional, only if DeepEval lacks a needed metric.
- Public data only. Rules in this domain are changing; every source carries a retrieval date.
- Part-time effort; timeline below is elapsed estimate, not effort commitment.

## 9. Budget
| Item | Estimate |
|---|---|
| Judge LLM calls for eval runs | $3 to $7 (cap enforced in config) |
| VPS (if free VM unavailable) | ~$5 per month |
| Domain (optional) | ~$10 per year, skip if over budget |
| Everything else | $0 |
Hard rule: spend cap on judge calls; evals use sampling and caching. Total target $0 to $10; if a paid VPS is needed for more than one month, the budget is exceeded and must be re-approved.

## 10. Timeline (estimate, ~7 to 8 weeks part-time, including the Next.js front end)
| Phase | Content | Est. |
|---|---|---|
| P0 | Spec sign-off, repo, environments | 2 days |
| P1 | Corpus ingestion, deadline/regime engine + tests | 1 week |
| P2 | Golden set, baseline RAG, baseline scores | 1 week |
| P3 | Tracing (Langfuse), dashboards | 3 to 4 days |
| P4 | Agent graph: classify, verify, retry, abstain, handoff | 1 week |
| P5 | Tools, guardrails, red-team suite | 4 days |
| P5b | Next.js front end: chat, panels, BFF proxy, tests | 4 to 5 days |
| P6 | CI gate, containers (api + web), deployment, monitoring | 1 week |
| P7 | Live feedback loop, regression demo, report | 4 days |

## 11. Risks and mitigations
| Risk | L | I | Mitigation |
|---|---|---|---|
| Regulation text misread or outdated | M | H | Pull primary text from eCFR; version and date every source; deadline logic as tested code; human review of rule tables |
| Unverified 2026 claims leak into knowledge base | M | H | Provenance gate: only documents with a primary URL are indexed; [S]/[U] items stay out |
| LLM judge unreliable | M | M | Calibrate against human labels; deterministic metrics wherever possible; judge agreement reported |
| Free-tier rate limits slow evals | H | M | Caching, batching, small golden set, retry with backoff |
| Budget overrun on judge calls | M | M | Config-level spend cap; sample live scoring |
| Small VPS too weak for the stack | M | M | Cloud free tier for Langfuse; lightweight vector DB; resource limits in compose |
| Langfuse/LangGraph integration friction | M | L | Fallback to the Langfuse SDK or callback handler instead of OTel; Langfuse cloud free tier |
| No run registry after dropping MLflow | L | L | Run JSON files as CI artifacts, committed `baseline.json`, Langfuse dataset runs; git history is the ledger |
| Free VM signup or capacity fails | M | L | Paid VPS fallback |
| Appearing to give real financial advice | L | H | Disclaimers, scope guardrails, mock tools only |
| Scope creep | H | M | Phased claim types; MVP first |
| Front end consumes time better spent on eval/deploy | M | M | Time-box P5b to ~5 days; one page, six components; no custom admin UI (use Grafana and Langfuse) |
| Extra Node container strains small VPS memory | M | M | Standalone build, memory limit, measure on host; fallback to managed front-end hosting |

## 12. Dependencies
Access to: eCFR API [V reachable], CFPB complaints API [V reachable], an LLM provider key, a hosting account, GitHub account (Actions, container registry).

## 13. Governance and change control
- Specs live in `docs/`; changes via pull request with a short rationale.
- Evaluation thresholds change only with a written baseline comparison.
- Decision log appended to this file (section 14).

## 14. Decision log
| Date | Decision | Reason |
|---|---|---|
| 2026-10-09 | Combined assistant with four claim types, phased | Maximizes interview story; MVP first limits risk |
| 2026-10-09 | DeepEval as primary evaluation framework; MLflow dropped (owner decision) | MLflow stores runs but computes no metrics; one fewer service; git + Langfuse cover the run record |
| 2026-10-09 | (ASSUMPTION) Provider-agnostic LLM layer, local embeddings | Keeps cost near zero; avoids lock-in |
| 2026-10-09 | Front end is React on Next.js (owner decision) | Interview-visible demo; shows front-end skill; BFF keeps secrets server-side |

## 15. Open questions
1. Confirm or change each **(ASSUMPTION)** above.
2. Hosting choice: free VM attempt vs paid VPS.
3. Public repo acceptable (it is a portfolio project), or keep private?
