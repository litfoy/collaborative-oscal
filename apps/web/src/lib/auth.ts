// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { readSession } from "./session";
import { getConfig } from "./config";
import type { SessionData } from "./session-crypto";

export type WebPrincipal = SessionData | { kind: "demo"; name: string; email?: undefined };

export function isDemoPrincipal(principal: WebPrincipal): principal is Extract<WebPrincipal, { kind: "demo" }> {
  return "kind" in principal && principal.kind === "demo";
}

export async function getRequestPrincipal(): Promise<WebPrincipal | null> {
  if (getConfig().authMode === "demo") return { kind: "demo", name: "Demo User" };
  const session = await readSession(await cookies());
  if (!session || session.accessTokenExpiresAt <= Math.floor(Date.now() / 1000)) return null;
  return session;
}

/** The session is usable only while its access token is still valid (proxy.ts refreshes it). */
export async function getSession(): Promise<WebPrincipal | null> {
  return getRequestPrincipal();
}

export async function requireSession(returnTo: string): Promise<WebPrincipal> {
  const session = await getSession();
  if (!session) {
    redirect(`/?returnTo=${encodeURIComponent(returnTo)}`);
  }
  return session;
}
