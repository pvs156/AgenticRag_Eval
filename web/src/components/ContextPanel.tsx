import type { AssistantReply, ChatResponse } from "@/lib/types";

const REGIME: Record<string, string> = {
  reg_e: "Regulation E (debit cards and electronic transfers)",
  reg_z: "Regulation Z (credit cards)",
  not_covered: "Outside federal error-resolution rules",
  unknown: "Not yet known",
};
const CLAIM: Record<string, string> = {
  unauthorized: "Charge you didn't make",
  merchant: "Problem with a purchase",
  scam: "Scam report",
  agent_initiated: "Purchase made by an AI agent",
};

function fmt(d: string) {
  return new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function ContextPanel({ last, interviewer }: { last: ChatResponse | null; interviewer: boolean }) {
  const r: AssistantReply | undefined = last?.result;
  if (!r) {
    return (
      <p className="text-sm text-[var(--muted)]">
        As we talk, this panel shows how the assistant reads your situation: which rules apply, the key dates, and the
        exact regulation text behind each answer.
      </p>
    );
  }
  return (
    <div className="space-y-5 text-sm">
      <section aria-labelledby="why-h">
        <h2 id="why-h" className="panel-h">
          Why this answer
        </h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-[var(--muted)]">Situation</dt>
          <dd>{r.claim_type ? CLAIM[r.claim_type] ?? r.claim_type : "Still working it out"}</dd>
          <dt className="text-[var(--muted)]">Rules</dt>
          <dd>{r.regime ? REGIME[r.regime] ?? r.regime : "Not yet known"}</dd>
          {r.unsettled && (
            <>
              <dt className="text-[var(--muted)]">Status</dt>
              <dd className="font-medium text-[var(--warn)]">Unsettled area of the rules</dd>
            </>
          )}
          {r.handoff_offered && (
            <>
              <dt className="text-[var(--muted)]">Specialist</dt>
              <dd>Recommended</dd>
            </>
          )}
        </dl>
      </section>

      {r.deadlines.length > 0 && (
        <section aria-labelledby="dates-h">
          <h2 id="dates-h" className="panel-h">
            Key dates
          </h2>
          <ul className="space-y-2">
            {r.deadlines.map((d, i) => (
              <li key={i} className="rounded-md border border-[var(--line)] p-2">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium">{d.party === "customer" ? "You" : "Bank"}</span>
                  <span className="tabular-nums">{d.due ? fmt(d.due) : "Need statement date"}</span>
                </div>
                <div className="text-[var(--muted)]">{d.name}</div>
                <div className="cite mt-1 inline-block">{d.basis}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {r.sources.length > 0 && (
        <section aria-labelledby="src-h">
          <h2 id="src-h" className="panel-h">
            Sources
          </h2>
          <ul className="space-y-2">
            {r.sources.map((s, i) => (
              <li key={i}>
                <details className="rounded-md border border-[var(--line)] p-2">
                  <summary className="cursor-pointer">
                    <span className="cite">{s.citation}</span>
                  </summary>
                  <p className="mt-2 whitespace-pre-line text-[var(--muted)]">{s.quote.slice(0, 900)}</p>
                  <p className="mt-2 text-xs text-[var(--muted)]">
                    eCFR text as of {s.as_of} ·{" "}
                    <a className="underline" href={s.url} target="_blank" rel="noreferrer">
                      open on eCFR
                    </a>
                  </p>
                </details>
              </li>
            ))}
          </ul>
        </section>
      )}

      {interviewer && (
        <section aria-labelledby="int-h" className="rounded-md border border-dashed border-[var(--accent)] p-2">
          <h2 id="int-h" className="panel-h">
            Interviewer view
          </h2>
          <p>
            Trace:{" "}
            {last?.trace_url ? (
              <a className="underline" href={last.trace_url} target="_blank" rel="noreferrer">
                open in Langfuse
              </a>
            ) : (
              <span className="text-[var(--muted)]">{last?.trace_id ?? "tracing not configured"}</span>
            )}
          </p>
          <p className="mt-1">
            Online scores:{" "}
            {Object.entries(last?.online_scores ?? {})
              .map(([k, v]) => `${k}=${v.toFixed(2)}`)
              .join(", ") || "none"}
          </p>
          <details className="mt-1">
            <summary className="cursor-pointer">Agent steps ({r.steps.length})</summary>
            <pre className="mt-1 max-h-72 overflow-auto text-xs">{JSON.stringify(r.steps, null, 1)}</pre>
          </details>
        </section>
      )}
    </div>
  );
}
