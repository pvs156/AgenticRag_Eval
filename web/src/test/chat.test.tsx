import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Chat } from "@/components/Chat";
import { RichText } from "@/components/RichText";
import type { ChatResponse } from "@/lib/types";

const REPLY: ChatResponse = {
  session_id: "s1",
  trace_id: "t1",
  trace_url: null,
  online_scores: { citation_validity: 1 },
  result: {
    reply: "This is an unauthorized transfer [12 CFR 1005.11(c)].\n\n**Key dates**\n- You: report by **November 29, 2026**",
    sources: [
      { citation: "12 CFR 1005.11(c)", heading: "x", quote: "A financial institution shall investigate promptly", url: "https://www.ecfr.gov/x", as_of: "2026-10-07" },
    ],
    claim_type: "unauthorized",
    regime: "reg_e",
    deadlines: [{ name: "Customer reports the error", due: "2026-11-29", party: "customer", basis: "12 CFR 1005.11(b)(1)", note: "" }],
    handoff_offered: false,
    handoff_reason: null,
    unsettled: false,
    asked_for: [],
    abstained: false,
    suggested_actions: ["open_dispute_case"],
    steps: [{ node: "verify", ok: true }],
    corpus_version: "abc",
  },
};

function mockFetch() {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/chat") return new Response(JSON.stringify(REPLY), { status: 200 });
    if (url === "/api/actions") {
      const body = JSON.parse(String(init?.body));
      return new Response(
        JSON.stringify(body.confirm ? { ok: true, status: "done", reference: "OPE-1", message: "Demo dispute case OPE-1 created." } : { ok: true, status: "declined" }),
        { status: 200 },
      );
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("RichText", () => {
  it("renders markdown subset as elements and never injects HTML", () => {
    const { container } = render(<RichText text={'**bold** <img src=x onerror="alert(1)"> [12 CFR 1005.6(b)]'} />);
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".cite")?.textContent).toBe("12 CFR 1005.6(b)");
  });
});

describe("Chat", () => {
  it("sends a message and shows the reply, dates and sources", async () => {
    const fetch = mockFetch();
    render(<Chat />);
    await userEvent.type(screen.getByLabelText("Your message"), "charge I didn't make{enter}");
    await screen.findByText(/This is an unauthorized transfer/);
    expect(fetch).toHaveBeenCalledWith("/api/chat", expect.anything());
    // a fresh page never reuses an earlier conversation's session
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body)).session_id).toBeNull();
    const details = screen.getByRole("complementary", { name: "Details" });
    expect(within(details).getByText("Nov 29, 2026")).toBeInTheDocument();
    expect(within(details).getAllByText("12 CFR 1005.11(c)").length).toBeGreaterThan(0);
  });

  it("asks for confirmation before a write action", async () => {
    const fetch = mockFetch();
    render(<Chat />);
    await userEvent.click(screen.getByText(/\$214 charge/));
    await userEvent.click(await screen.findByRole("button", { name: "Open a dispute case" }));
    expect(screen.getByText("Open a dispute case?")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalledWith("/api/actions", expect.anything());
    await userEvent.click(screen.getByRole("button", { name: "Yes, go ahead" }));
    await waitFor(() => expect(screen.getByText("Demo dispute case OPE-1 created.")).toBeInTheDocument());
  });

  it("shows a friendly error when the backend fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Unavailable." }), { status: 503 })));
    render(<Chat />);
    await userEvent.type(screen.getByLabelText("Your message"), "hello{enter}");
    expect(await screen.findByText(/Unavailable\. You can try again or ask for a person\./)).toBeInTheDocument();
  });
});
