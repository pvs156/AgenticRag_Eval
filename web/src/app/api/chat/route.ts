import { callBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  let body: { message?: unknown; session_id?: unknown };
  try {
    body = await req.json();
  } catch {
    return Response.json({ detail: "invalid JSON" }, { status: 400 });
  }
  const message = typeof body.message === "string" ? body.message.trim() : "";
  if (!message || message.length > 2000) {
    return Response.json({ detail: "message must be 1-2000 characters" }, { status: 422 });
  }
  const session_id = typeof body.session_id === "string" ? body.session_id : undefined;
  return callBackend("/v1/chat", { message, session_id });
}
