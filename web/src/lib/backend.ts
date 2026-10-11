// Server-only helper for the BFF routes. The API URL and demo token never reach the browser.
import "server-only";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function callBackend(path: string, body: unknown): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.DEMO_TOKEN) headers["X-Demo-Token"] = process.env.DEMO_TOKEN;
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(180_000),
    });
    const text = await res.text();
    return new Response(text, { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch {
    return Response.json({ detail: "The assistant is unavailable right now. Please try again." }, { status: 503 });
  }
}

export async function backendHealthy(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/readyz`, { cache: "no-store", signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch {
    return false;
  }
}
