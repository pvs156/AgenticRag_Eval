# Evaluation results

## Update 2026-11-01: hosted model (Groq `openai/gpt-oss-120b`, free tier)

Same agent, same golden and held-out sets, now with a production-grade model. Judge: Groq `qwen/qwen3.8-27b`
(a different model family from the generator).

| metric | agent / full<br><sub>agent-full-final</sub> | agent / full<br><sub>agent-full-groq</sub> | agent / heldout<br><sub>agent-heldout-final</sub> | agent / heldout<br><sub>agent-heldout-groq</sub> | agent / smoke<br><sub>agent-smoke-groq-judged</sub> |
|---|---|---|---|---|---|
| deadline_recall | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| no_wrong_dates | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| must_cite_recall | 1.00 | 1.00 |  |  | 1.00 |
| citation_validity | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| handoff_when_needed | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| asks_for_missing | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| flags_unsettled | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| declines_out_of_scope | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| no_outcome_promise | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| pii_not_echoed | 1.00 | 1.00 |  |  |  |
| first_draft_passed | 0.34 | 0.86 | 0.09 | 0.82 | 0.90 |
| used_safe_fallback | 0.57 | 0.00 | 0.64 | 0.00 | 0.00 |
| faithfulness |  |  |  |  | 0.97 |
| answer_relevancy |  |  |  |  | 0.75 |
| policy_compliance |  |  |  |  | 1.00 |
| error_rate | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| latency_p50_s | 4.43 | 4.12 | 5.78 | 4.28 | 3.73 |
| latency_p95_s | 10.57 | 5.30 | 33.14 | 12.62 | 10.09 |
| cases | 45 | 45 | 16 | 16 | 15 |
| model | qwen2.5:1.5b | openai/gpt-oss-120b | qwen2.5:1.5b | openai/gpt-oss-120b | openai/gpt-oss-120b |

What changed versus the local 1.5B model:
- **First drafts that pass the verifier:** 34% to 86% (golden) and 9% to 82% (held-out). Answers needing the safe
  templated fallback: from 57-64% to **0%**.
- **Judge metrics on the smoke suite:**
  - faithfulness 0.97 (claims supported by the retrieved regulation text);
  - policy compliance 1.00;
  - answer relevancy 0.75. DeepEval's relevancy metric marks the templated sections (key dates, disclaimers) as
    "irrelevant statements", so 0.75 is partly an artifact of the response format.
- **Behaviour metrics:** 1.00 across the board on both sets.

Two issues found and fixed on the way:
- **U07, an agent bug.** gpt-oss-120b marked a customer as non-US because the *merchant* was in Spain, so the agent
  handed off instead of answering. "Non-US" is now grounded in the customer's words only, the same rule as dates
  and card type.
- **P02, a scorer bug.** The eval scorer flagged "the excerpts do not guarantee a refund" as a promise. It now
  uses the verifier's negation-aware check.

**Judge calibration (`python -m evals.judge_calibration`).**
- **First run:** policy compliance 0.65. Reading the judge's reasons showed:
  - The rubric was looser than the design spec. It implied every dispute needs a handoff, and it didn't say the
    key dates are computed by the system.
  - G-Eval's auto-generated steps inverted "do not penalize the key dates" into "key dates are prohibited".
  - One real gap: scam clarifying questions didn't offer a person, which the design spec requires. Now fixed.
- **Fix:** the rubric is now explicit `evaluation_steps` matching `docs/03_DESIGN_SPEC.md`.
- **Negative control:** the judge must flag five deliberately bad replies (promised refund, investment advice, scam
  with no handoff, invented rule, echoed card number) and pass a good one. It does: 0.20-0.50 versus 1.00.
- **Still to do:** a human-labelled set of about 30 real replies, to measure judge-human agreement.

Latency: p50 about 4 s and p95 about 5-13 s on Groq, excluding waits for the free tier's 8K tokens-per-minute cap.

---

## Development history (local `qwen2.5:1.5b`, 2026-10-09)

All numbers come from run files in `evals/runs/` (regenerate with `python -m evals.report <run files>`).
Model for every run: local `qwen2.5:1.5b` via Ollama on a laptop CPU (the $0 development setup). Date: 2026-10-09.

## What is measured

- **Golden set:** 45 hand-written cases mirroring real CFPB complaint sub-issues, plus policy, safety and AI-agent cases. Every hand label is cross-checked against the rules engine.
- **Held-out set:** 16 cases written *before* the deterministic extractor existed and never used to tune it. Diagnosis used golden-set failures only; held-out results were read only in aggregate.
- **Deterministic scorers** (`evals/scorers/deterministic.py`) check the behaviour contract: correct dates, no invented dates, valid citations, a handoff when needed, asking for missing facts, saying "unsettled", declining out-of-scope requests, no promised outcomes, no PII echo.
- **Judge metrics** (DeepEval faithfulness, answer relevancy, and a G-Eval policy rubric) are wired in (`--judge`). They need a capable judge model; see "Limits".

## Golden set (45 cases)

Columns, left to right:
1. Naive RAG baseline.
2. First agent (LLM-only extraction).
3. Agent with the deterministic extractor, grounding rule and strict verifier (v4, uncached latency).
4. Final agent (partly cached run).

| metric | baseline / full<br><sub>baseline-full-20261010013101</sub> | agent / full<br><sub>agent-full-20261010014113</sub> | agent / full<br><sub>agent-full-v4</sub> | agent / full<br><sub>agent-full-final</sub> |
|---|---|---|---|---|
| deadline_recall | 0.00 | 0.41 | 1.00 | 1.00 |
| no_wrong_dates | 0.92 | 0.68 | 0.97 | 1.00 |
| must_cite_recall | 0.36 | 0.32 | 1.00 | 1.00 |
| citation_validity | 0.82 | 0.95 | 0.97 | 1.00 |
| handoff_when_needed | 0.14 | 0.57 | 1.00 | 1.00 |
| asks_for_missing | 0.00 | 0.67 | 1.00 | 1.00 |
| flags_unsettled | 0.00 | 0.17 | 1.00 | 1.00 |
| declines_out_of_scope | 0.00 | 0.20 | 1.00 | 1.00 |
| no_outcome_promise | 1.00 | 1.00 | 1.00 | 1.00 |
| pii_not_echoed | 1.00 | 1.00 | 1.00 | 1.00 |
| first_draft_passed |  |  | 0.31 | 0.34 |
| used_safe_fallback |  |  | 0.60 | 0.57 |
| error_rate | 0.00 | 0.00 | 0.00 | 0.00 |
| latency_p50_s | 13.70 | 15.86 | 13.95 | 4.43 |
| latency_p95_s | 21.95 | 20.10 | 26.20 | 10.57 |
| cases | 45 | 45 | 45 | 45 |
| model | qwen2.5:1.5b | qwen2.5:1.5b | qwen2.5:1.5b | qwen2.5:1.5b |


## Held-out set (16 cases, never used for tuning)

| metric | baseline / heldout<br><sub>baseline-heldout</sub> | agent / heldout<br><sub>agent-heldout-v1-llm-only</sub> | agent / heldout<br><sub>agent-heldout-v4</sub> | agent / heldout<br><sub>agent-heldout-final</sub> |
|---|---|---|---|---|
| deadline_recall | 0.00 | 0.55 | 1.00 | 1.00 |
| no_wrong_dates | 1.00 | 0.67 | 1.00 | 1.00 |
| citation_validity | 1.00 | 1.00 | 1.00 | 1.00 |
| handoff_when_needed | 0.14 | 0.43 | 1.00 | 1.00 |
| asks_for_missing | 0.00 | 0.00 | 1.00 | 1.00 |
| flags_unsettled | 0.00 | 0.00 | 1.00 | 1.00 |
| declines_out_of_scope | 0.00 | 0.00 | 1.00 | 1.00 |
| no_outcome_promise | 1.00 | 1.00 | 1.00 | 1.00 |
| first_draft_passed |  |  | 0.18 | 0.09 |
| used_safe_fallback |  |  | 0.64 | 0.64 |
| error_rate | 0.00 | 0.00 | 0.00 | 0.00 |
| latency_p50_s | 18.10 | 16.80 | 16.82 | 5.78 |
| latency_p95_s | 27.56 | 25.21 | 28.01 | 33.14 |
| cases | 16 | 16 | 16 | 16 |
| model | qwen2.5:1.5b | qwen2.5:1.5b | qwen2.5:1.5b | qwen2.5:1.5b |


## Retrieval (no LLM): is the required provision in the top k?

```
22 cases with required citations; RRF k=60
recall@5: dense=0.27  bm25=0.41  hybrid=0.18  hybrid+rerank=0.36  anchored=1.00
recall@10: dense=0.36  bm25=0.50  hybrid=0.55  hybrid+rerank=0.45  anchored=1.00
```

The customer's own words rarely match regulation text ("a charge I didn't make" vs "unauthorized electronic fund transfer"), so naive retrieval misses the governing provision most of the time. The agent anchors retrieval on the citations the rules engine returns. The anchored figure is an upper bound that assumes correct classification; end-to-end correctness is in the tables above.

## What changed between versions, and why (each change came from a measured failure)

| Change | Failure that motivated it | Effect |
|---|---|---|
| Deterministic first-pass extractor | The 1.5B model labelled "a charge I never made" as a scam and an AI-agent purchase as a plain dispute | Intent and routing correct; handoff, unsettled and decline metrics went from 0.17-0.57 to 1.00 |
| Grounding rule: dates, card type and "reported by phone" only from the customer's words | The model invented "today" as the statement date, producing a confident wrong deadline (December 8) in 10 replies | No invented deadlines (no_wrong_dates 0.66 to 1.00) |
| Notice-date detection | "On June 15 I sent a written dispute" was treated as if reported today | Bank's missed deadline is now detected and escalated |
| Verifier rejects day counts, repetition and over-long text | 22 of 45 explanations restated time limits, some contradicting the computed dates (10 vs 20 business days) | Contradictions can no longer reach the user |

## Limits (stated plainly)

- **Answer quality depends on the model.** With the 1.5B local model only 34% (golden) and 9% (held-out) of first drafts pass the verifier, and 57-64% of answers end with the safe templated fallback. That fallback is still correct (dates, rules, handoff) but terse. The verifier makes a weak model *safe*; it doesn't make it *fluent*. A hosted free-tier model should raise the first-draft pass rate, and the gate will measure that before release.
- **The judge must be calibrated before it gates.** A 2-case pipeline check with the 1.5B model as judge gave faithfulness 0.17 and policy 0.20 (`judge-pipeline-check.json`). That is not trustworthy as a quality signal. The plan is a hosted judge, calibrated against about 30 human-labelled replies, before `faithfulness` and `policy_compliance` gate releases.
- **A concrete case for the judge.** In a live UI test the 1.5B model wrote, for an AI-agent purchase, that the regulations
  leave the question unsettled *and* that "the agent does not have authority to use the card". That second
  sentence is an unsupported conclusion that contradicts the first. It passed every deterministic check (no dates,
  valid citations, says "unsettled"). Only a faithfulness judge catches this class of error, which is why
  `faithfulness` is in the gate once a calibrated judge is configured.
- **Deterministic scorers are pattern checks.** They verify the behaviour contract, not prose quality, and the agent's templated sections are designed to satisfy that contract. That is intended, but it's why the judge metrics matter.
- **Latency on a laptop CPU is about 14 s p50 / 26 s p95 uncached** (v4). Runs that reuse the LLM response cache (final) show lower numbers that do not reflect production.
- **The sets are small** (45 + 16). Grow them from reviewed production failures (Langfuse annotation queue to `build_golden.py`).

## Release gate

`python -m evals.gate <run file>` checks `evals/thresholds.yaml` (absolute floors) and `evals/baseline.json` (no regression):
- `agent-full-final` passes.
- `baseline-full` fails, which is the gate correctly blocking the naive design.
