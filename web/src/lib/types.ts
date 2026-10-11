// Mirrors app/schemas.py and app/api/main.py (keep in sync; CI type-checks the BFF routes against these).

export type Deadline = {
  name: string;
  due: string | null;
  party: "customer" | "institution";
  basis: string;
  note: string;
};

export type SourceRef = {
  citation: string;
  heading: string;
  quote: string;
  url: string;
  as_of: string;
};

export type AssistantReply = {
  reply: string;
  sources: SourceRef[];
  claim_type: string | null;
  regime: string | null;
  deadlines: Deadline[];
  handoff_offered: boolean;
  handoff_reason: string | null;
  unsettled: boolean;
  asked_for: string[];
  abstained: boolean;
  suggested_actions: string[];
  steps: Record<string, unknown>[];
  corpus_version: string;
};

export type ChatResponse = {
  session_id: string;
  trace_id: string | null;
  trace_url: string | null;
  online_scores: Record<string, number>;
  result: AssistantReply;
};

export type ActionName = "open_dispute_case" | "block_card" | "handoff";

export type ActionResponse = {
  ok: boolean;
  status: "done" | "declined";
  reference?: string;
  message?: string;
};
