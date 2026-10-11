import { notFound } from "next/navigation";

import { Chat } from "@/components/Chat";

export const dynamic = "force-dynamic";

// /interviewer?token=... shows trace links, online scores and the agent's step log.
export default async function Interviewer({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  const expected = process.env.INTERVIEWER_TOKEN;
  if (!expected || token !== expected) notFound();
  return <Chat interviewer />;
}
