import { backendHealthy } from "@/lib/backend";

export const dynamic = "force-dynamic";

// Liveness of the web container itself; `backend` reports whether the assistant is ready.
export async function GET() {
  return Response.json({ status: "ok", backend: (await backendHealthy()) ? "ready" : "starting" });
}
