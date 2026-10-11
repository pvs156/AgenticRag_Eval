"use client";

import { useEffect, useRef, useState } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ContextPanel } from "@/components/ContextPanel";
import { RichText } from "@/components/RichText";
import type { ActionName, ActionResponse, ChatResponse } from "@/lib/types";

type Msg =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; data?: ChatResponse; rated?: number }
  | { role: "system"; text: string };

const EXAMPLES = [
  "There's a $214 charge on my debit card I never made. My statement came out September 30.",
  "I ordered a couch with my credit card and it never arrived.",
  "Someone posing as my bank got me to send $3,000 by bank transfer.",
  "My AI shopping agent bought the wrong jacket with my credit card.",
];

const ACTION_COPY: Record<ActionName, { label: string; title: string; body: string }> = {
  open_dispute_case: {
    label: "Open a dispute case",
    title: "Open a dispute case?",
    body: "This records your dispute with the details you've shared, which starts the bank's investigation timeline.",
  },
  block_card: {
    label: "Block my card",
    title: "Block your card?",
    body: "Blocking stops new charges on this card. You'd need a replacement card to keep using it.",
  },
  handoff: {
    label: "Talk to a person",
    title: "Connect with a specialist?",
    body: "A specialist will receive a summary of this conversation so you don't need to repeat yourself.",
  },
};

const PROGRESS = ["Reading your message…", "Checking which rules apply…", "Looking up the regulation text…", "Checking the answer…"];

export function Chat({ interviewer = false }: { interviewer?: boolean }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  // The session lives only as long as the visible conversation: a reload starts fresh, so the backend never
  // remembers facts the user can no longer see.
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [last, setLast] = useState<ChatResponse | null>(null);
  const [pending, setPending] = useState<ActionName | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setProgress((p) => Math.min(p + 1, PROGRESS.length - 1)), 2500);
    return () => clearInterval(t);
  }, [busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: message }]);
    setProgress(0);
    setBusy(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Something went wrong.");
      const chat = data as ChatResponse;
      setSessionId(chat.session_id);
      setLast(chat);
      setMessages((m) => [...m, { role: "assistant", text: chat.result.reply, data: chat }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong.";
      setMessages((m) => [...m, { role: "system", text: `${msg} You can try again or ask for a person.` }]);
    } finally {
      setBusy(false);
    }
  }

  async function runAction(action: ActionName, confirm: boolean) {
    setPending(null);
    if (!sessionId) return;
    const res = await fetch("/api/actions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, action, confirm }),
    });
    const data = (await res.json()) as ActionResponse;
    const text = !res.ok
      ? "That action couldn't be completed. Please try again."
      : data.status === "declined"
        ? "Okay, I haven't done anything."
        : (data.message ?? "Done.");
    setMessages((m) => [...m, { role: "system", text }]);
  }

  async function rate(index: number, rating: number) {
    const msg = messages[index];
    if (msg.role !== "assistant" || msg.rated !== undefined) return;
    setMessages((m) => m.map((x, i) => (i === index ? { ...x, rated: rating } : x)) as Msg[]);
    await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating, session_id: sessionId, trace_id: msg.data?.trace_id ?? null }),
    }).catch(() => undefined);
  }

  function reset() {
    setMessages([]);
    setLast(null);
    setSessionId(null);
  }

  const lastActions = (last?.result.suggested_actions ?? []) as ActionName[];

  return (
    <div className="mx-auto grid w-full max-w-6xl flex-1 gap-4 px-4 py-4 md:grid-cols-[1fr_22rem]">
      <section aria-label="Conversation" className="flex min-h-[60vh] flex-col rounded-xl border border-[var(--line)] bg-[var(--panel)]">
        <div className="flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite">
          {messages.length === 0 && (
            <div>
              <h1 className="text-xl font-semibold">How can I help with your card or account?</h1>
              <p className="mt-1 text-sm text-[var(--muted)]">
                Tell me what happened in your own words. I&apos;ll explain which rules apply, the key dates, and what
                happens next. Please don&apos;t share full card numbers or passwords.
              </p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {EXAMPLES.map((e) => (
                  <button key={e} type="button" className="example" onClick={() => send(e)}>
                    {e}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div className={`bubble ${m.role}`}>
                {m.role === "assistant" ? <RichText text={m.text} /> : <p>{m.text}</p>}
                {m.role === "assistant" && (
                  <div className="mt-2 flex items-center gap-2 text-xs text-[var(--muted)]">
                    <span>Helpful?</span>
                    <button type="button" aria-label="Helpful" aria-pressed={m.rated === 1} className="rate" disabled={m.rated !== undefined} onClick={() => rate(i, 1)}>
                      👍
                    </button>
                    <button type="button" aria-label="Not helpful" aria-pressed={m.rated === -1} className="rate" disabled={m.rated !== undefined} onClick={() => rate(i, -1)}>
                      👎
                    </button>
                    {m.rated !== undefined && <span>Thanks for the feedback.</span>}
                  </div>
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex justify-start">
              <div className="bubble assistant text-[var(--muted)]" role="status">
                <span className="dot" /> {PROGRESS[progress]}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {lastActions.length > 0 && !busy && (
          <div className="flex flex-wrap gap-2 border-t border-[var(--line)] px-4 py-2">
            {lastActions.map((a) => (
              <button key={a} type="button" className="btn-secondary" onClick={() => setPending(a)}>
                {ACTION_COPY[a].label}
              </button>
            ))}
          </div>
        )}

        <form
          className="flex gap-2 border-t border-[var(--line)] p-3"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <label htmlFor="msg" className="sr-only">
            Your message
          </label>
          <textarea
            id="msg"
            rows={2}
            maxLength={2000}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Describe the charge or problem…"
            className="min-h-11 flex-1 resize-none rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2"
          />
          <button type="submit" className="btn-primary self-end" disabled={busy || !input.trim()}>
            Send
          </button>
        </form>
      </section>

      <aside aria-label="Details" className="h-fit space-y-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 md:sticky md:top-4">
        <div className="flex items-center justify-between gap-2">
          <button type="button" className="btn-primary" onClick={() => setPending("handoff")} disabled={!sessionId}>
            Talk to a person
          </button>
          <button type="button" className="btn-secondary" onClick={reset}>
            New conversation
          </button>
        </div>
        <ContextPanel last={last} interviewer={interviewer} />
      </aside>

      <ConfirmDialog
        open={pending !== null}
        title={pending ? ACTION_COPY[pending].title : ""}
        body={pending ? ACTION_COPY[pending].body : ""}
        onConfirm={() => pending && runAction(pending, true)}
        onCancel={() => pending && runAction(pending, false)}
      />
    </div>
  );
}
