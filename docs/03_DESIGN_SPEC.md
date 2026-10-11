# Design Specification
**Project:** Dispute & Scam Resolution Assistant | **Version:** 0.1 draft | **Date:** 2026-10-09
Related: [PID](01_PID.md), [Tech spec](02_TECH_SPEC.md)

This covers behavior design (what the assistant says and does), interaction design, and operational design (dashboards, review workflow). Architecture and stack are in the tech spec.

---

## 1. Design principles
1. **Accuracy over fluency.** Exact where rules are exact (deadlines are computed, not generated).
2. **Never trap the user.** A human path is always reachable; unresolved after 3 turns triggers a handoff offer.
3. **Say what is unsettled.** If no primary rule covers a situation, say so plainly and route onward; never invent a rule.
4. **No promises.** The assistant describes rights, timelines and next steps; it never promises a refund or outcome, and never gives personalized financial or legal advice.
5. **Explain with citations.** Rule statements carry a citation the user can look up, plus the corpus date.
6. **Calm and respectful tone,** especially for scam victims.
7. **Auditable.** Every decision leaves a trace and an audit event.
8. **Demo honesty.** A persistent banner states this is a demonstration, uses mock actions, and must not receive real account data.

## 2. Users and scenarios
| Persona | Need | Example |
|---|---|---|
| Cardholder with an unrecognized charge | Know rights and deadlines, start a dispute | "There's a $240 charge I didn't make." |
| Customer with a merchant problem | Understand eligibility and evidence | "The store never delivered my order." |
| Scam victim | Compassion, clarity, fast escalation | "I sent money to someone who turned out to be fake." |
| Customer of an AI shopping agent | Clarity on an unsettled area | "My shopping agent bought the wrong item." |
| Interviewer / reviewer | See quality controls working | Trace view, eval report, dashboards |

## 3. Conversation design

### 3.1 Universal response structure
1. Acknowledge (one short sentence, empathic where relevant).
2. What this likely is (claim type and rule regime) and how sure the assistant is.
3. Key facts and deadlines (from the rules engine), with citations.
4. Next steps and what is needed from the user.
5. Handoff offer when appropriate; disclaimer line.

Length: concise, plain language, no legalese beyond quoted citations. Numbers and dates shown explicitly with their basis ("60 days from the statement date, 12 CFR 1005.11(b)(1)": exact citation to be confirmed from primary text).

### 3.2 Intake rules
- Ask only for facts that change the outcome: debit vs credit, transaction date, statement date, amount, whether the customer made or approved the payment, merchant contact attempts, account age if relevant.
- One or two questions per turn; maximum 2 clarifying rounds before offering a human.
- Never request full card numbers, SSNs, passwords or PINs. If the user types them, the guardrail masks them and the assistant reminds them not to share.

### 3.3 Decision flows (summary)
**Unauthorized charge**
1. Determine account type (debit/credit).
2. Collect dates and amount.
3. Rules engine returns regime, liability notes and reporting deadlines.
4. Explain, offer to open a (mock) case and block the card, each requiring confirmation.

**Merchant/purchase dispute**
1. Confirm customer tried to resolve with merchant; collect evidence types.
2. Explain billing-error vs merchant-dispute distinction where the rules differ.
3. Provide eligibility and deadline from rules engine; offer to open a case.

**Scam (APP) report**
1. Lead with empathy and immediate safety steps (stop further payments, contact the receiving institution if relevant).
2. Ask whether the user authorized or initiated the transfer, without blame.
3. Explain what the corpus supports. Where reimbursement obligations are not established in the indexed primary sources, say that outcomes are determined by the bank's investigation and applicable law, and offer a human specialist. Do not predict the outcome.
4. Open a priority case on confirmation; always offer handoff.

**Agent-initiated purchase dispute**
1. Determine whether the transaction was authorized by the cardholder through a delegated agent, and what went wrong (wrong item, exceeded limit, unauthorized action).
2. State that rules for delegated-agent disputes are still evolving and cite only what primary sources establish (e.g. general dispute rights).
3. Mark `unsettled=true`, provide the general path, collect an evidence checklist (agent logs, order confirmation, spending mandate), and hand off.

### 3.4 Abstain and escalate rules
Abstain (and hand off) when any of: verification fails after 2 retries; retrieval returns nothing relevant; classifier confidence is low after 2 clarifications; question requires legal judgment or an outcome prediction; user asks for a human; user shows distress or reports ongoing fraud in progress (prioritize safety message plus handoff).

Handoff packet (structured): claim type, regime, facts collected, rules-engine output, citations shown, reason for handoff, trace id. The user is told what will happen next and what information they have already given, so they are not asked again.

### 3.5 Guardrail copy (illustrative)
- Outcome request ("Will I get my money back?"): "I can't promise an outcome, because that depends on the investigation. I can tell you what the timelines are and what happens next."
- Out of scope: "I can only help with card and account dispute questions here. For anything else, I'll connect you to a person."
- Injection attempt: refuse the instruction, continue the task, log a safety event.
- Banner/footer: "Demonstration only. Not financial or legal advice. Do not enter real account details."

## 4. Interface design (demo UI, Next.js + React)
Implementation notes are in the tech spec, section 3.12. Visual design: clean, calm, trustworthy; neutral palette with one accent color, light and dark themes via CSS variables, clear typography, generous spacing; no bank or Mastercard branding or logos (avoids impersonation and trademark issues). Components: `Chat`, `MessageList`, `Message`, `SourcesPanel`, `WhyPanel`, `ConfirmDialog`, `HandoffButton`, `Feedback`, `DisclaimerBanner`, `InterviewerBar`.
- Streaming replies with a typing indicator; the sources and "why" panels fill in when the final event arrives.
- Layout: single column on mobile; on wide screens, chat on the left and a collapsible context panel (claim type, regime, deadlines, citations) on the right.
- Empty state with four example prompts (one per claim type) so a reviewer can try the app in one click.
- Error states: network or rate-limit errors show a plain message with a retry and the handoff button, never a blank screen.
- Single-page chat with: message list, input, "Talk to a person" button always visible, expandable "Sources" under each answer (citation, short quote, corpus date), and a small "Why this answer" panel showing claim type, regime, deadlines and confidence.
- Confirm dialog for write actions ("Open a dispute case for $X? Yes / No") with explicit wording that it is a mock.
- Thumbs up/down plus optional comment, wired to `/v1/feedback`.
- Accessibility: keyboard navigable, sufficient contrast, readable on mobile, no information by color alone.
- Interviewer mode (query param or token): shows trace link and live scores, hidden from the default user view.

## 5. State machine (user-facing)
`new -> intake -> analysing -> answered -> (action_pending_confirm -> action_done) | handoff | abstained`
Transitions are driven by the agent graph; each transition emits an audit event.

## 6. Prompt and policy design
- Prompts are versioned files with: role, scope, tone, citation rules, forbidden behaviors, output schema, and examples.
- Generator is instructed to use only provided citations and rules-engine values; verifier enforces it.
- Policy list (machine-checkable): no outcome promises, no personalized advice, no collection of secrets, no statements about rules absent from retrieved text, always disclose `unsettled` where flagged, always offer handoff on the 3rd unresolved turn.
- Each policy has at least one eval case and one red-team probe.

## 7. Operational design

### 7.1 Dashboards (Grafana)
1. **Service health:** request rate, error rate, latency p50/p95, uptime.
2. **Agent behavior:** claim-type mix, retry rate, abstain rate, handoff rate, unresolved-turns distribution.
3. **Quality (from sampled scores):** faithfulness, citation validity, policy violations, trend by prompt/corpus version.
4. **Cost:** tokens and USD by tier, per-session cost, judge budget remaining.
Layout: top row of 4 key numbers with thresholds, trends below, drill-down links to Langfuse traces.

### 7.2 Alerts
Latency p95 high, error rate, abstain or retry spike, faithfulness below floor, cost rate over cap, judge errors. Delivery: email or a chat webhook; alerts include a runbook link.

### 7.3 Human review workflow (Langfuse annotation queue)
Sampling rules: all handoffs, low-score traces, negative feedback, random 5%. Reviewer labels: correct / incorrect regime / incorrect deadline / unfaithful / policy violation / unsafe. Reviewed failures are promoted to the golden set via a script, with the label and a fixed expected outcome.

### 7.4 Release and rollback design
Release candidate -> eval gate -> manual approval -> deploy -> health check -> automatic rollback on failure. The release notes template records: eval deltas, prompt and corpus versions, known issues.

## 8. Evaluation report design (for interviews)
One page with: problem, architecture sketch, baseline vs agentic table (regime accuracy, deadline match, faithfulness, abstain correctness, handoff rate, latency, cost), the regression demo (what was broken, which metric caught it, which CI step blocked it), and the lessons learned. Every claim in the report links to an eval run file (by git SHA) or a Langfuse trace.

## 9. Failure-mode design
| Failure | Behavior |
|---|---|
| LLM timeout / rate limit | Retry once with backoff, then graceful message and handoff offer |
| Invalid structured output | One repair attempt, then fail closed to handoff |
| Retrieval empty | Say the indexed sources don't cover it; handoff |
| Rules engine says `needs_human` | Skip answer generation; handoff with reason |
| Judge unavailable (online scoring) | Skip scoring, increment `judge_errors_total`; never blocks the user path |
| Spend cap reached | Disable judge scoring first, then fall back to cached/local model; surface in dashboard |
| Stale corpus | Answers display the corpus retrieval date; alert if older than a set age |

## 10. Open design questions
1. Chat-only UI, or also a case-summary view for a "banker" persona? (Recommendation: chat only in v1.)
2. Tone preset (formal bank voice vs plain friendly)?
3. Languages beyond English (out of scope by default)?
