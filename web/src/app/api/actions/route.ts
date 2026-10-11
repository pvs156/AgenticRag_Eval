import { callBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";

const ALLOWED = new Set(["open_dispute_case", "block_card", "handoff"]);

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  if (typeof body.session_id !== "string" || !ALLOWED.has(body.action) || typeof body.confirm !== "boolean") {
    return Response.json({ detail: "invalid action request" }, { status: 422 });
  }
  return callBackend("/v1/actions", { session_id: body.session_id, action: body.action, confirm: body.confirm });
}
