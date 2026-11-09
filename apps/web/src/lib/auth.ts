import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { readSession } from "./session";
import type { SessionData } from "./session-crypto";

/** The session is usable only while its access token is still valid (proxy.ts refreshes it). */
export async function getSession(): Promise<SessionData | null> {
  const session = await readSession(await cookies());
  if (!session) return null;
  if (session.accessTokenExpiresAt <= Math.floor(Date.now() / 1000)) return null;
  return session;
}

export async function requireSession(returnTo: string): Promise<SessionData> {
  const session = await getSession();
  if (!session) {
    redirect(`/?returnTo=${encodeURIComponent(returnTo)}`);
  }
  return session;
}
