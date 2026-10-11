import { callBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const rating = Number(body.rating);
  if (![-1, 0, 1].includes(rating)) return Response.json({ detail: "rating must be -1, 0 or 1" }, { status: 422 });
  return callBackend("/v1/feedback", {
    session_id: typeof body.session_id === "string" ? body.session_id : null,
    trace_id: typeof body.trace_id === "string" ? body.trace_id : null,
    rating,
    comment: typeof body.comment === "string" ? body.comment.slice(0, 1000) : null,
  });
}
