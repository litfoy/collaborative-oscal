import "server-only";

import { getConfig } from "./config";
import {
  chunk,
  isSessionData,
  seal,
  unseal,
  type SessionData,
} from "./session-crypto";

export interface CookieReader {
  get(name: string): { value: string } | undefined;
}

export interface CookieWriter {
  set(name: string, value: string, options: CookieOptions): unknown;
}

export interface CookieOptions {
  httpOnly: true;
  secure: boolean;
  sameSite: "lax";
  path: "/";
  maxAge: number;
}

const MAX_CHUNKS = 12;

export function sessionCookieName(secure: boolean): string {
  return secure ? "__Host-co_session" : "co_session";
}

export function flowCookieName(secure: boolean): string {
  return secure ? "__Host-co_flow" : "co_flow";
}

function options(secure: boolean, maxAge: number): CookieOptions {
  return { httpOnly: true, secure, sameSite: "lax", path: "/", maxAge };
}

function readChunks(reader: CookieReader, name: string): string | null {
  const parts: string[] = [];
  for (let index = 0; index < MAX_CHUNKS; index += 1) {
    const part = reader.get(`${name}.${index}`);
    if (!part) break;
    parts.push(part.value);
  }
  return parts.length > 0 ? parts.join("") : null;
}

export function hasSessionCookie(reader: CookieReader): boolean {
  return reader.get(`${sessionCookieName(getConfig().secureCookies)}.0`) !== undefined;
}

export async function readSession(reader: CookieReader): Promise<SessionData | null> {
  const config = getConfig();
  const raw = readChunks(reader, sessionCookieName(config.secureCookies));
  if (!raw) return null;
  const data = await unseal<SessionData>(raw, config.sessionSecret, "session");
  if (!data || !isSessionData(data)) return null;
  if (data.expiresAt <= Math.floor(Date.now() / 1000)) return null;
  return {
    sub: data.sub,
    name: data.name,
    email: data.email,
    accessToken: data.accessToken,
    accessTokenExpiresAt: data.accessTokenExpiresAt,
    refreshToken: data.refreshToken,
    idToken: data.idToken,
    expiresAt: data.expiresAt,
  };
}

export interface CookieMutation {
  name: string;
  value: string;
  options: CookieOptions;
}

/** Computes the cookie writes required to store (or, with null, clear) a session. */
export async function sessionCookieMutations(
  existing: CookieReader,
  data: SessionData | null,
): Promise<CookieMutation[]> {
  const config = getConfig();
  const name = sessionCookieName(config.secureCookies);
  const mutations: CookieMutation[] = [];
  let used = 0;
  if (data) {
    const lifetime = Math.max(1, data.expiresAt - Math.floor(Date.now() / 1000));
    const sealed = await seal(data, config.sessionSecret, "session", lifetime);
    const chunks = chunk(sealed);
    if (chunks.length > MAX_CHUNKS) {
      throw new Error("Session payload too large.");
    }
    chunks.forEach((value, index) => {
      mutations.push({
        name: `${name}.${index}`,
        value,
        options: options(config.secureCookies, lifetime),
      });
    });
    used = chunks.length;
  }
  for (let index = used; index < MAX_CHUNKS; index += 1) {
    if (existing.get(`${name}.${index}`) !== undefined || !data) {
      mutations.push({
        name: `${name}.${index}`,
        value: "",
        options: options(config.secureCookies, 0),
      });
    }
  }
  return mutations;
}

export function applyMutations(writer: CookieWriter, mutations: CookieMutation[]): void {
  for (const mutation of mutations) {
    writer.set(mutation.name, mutation.value, mutation.options);
  }
}

export interface LoginFlowState {
  state: string;
  nonce: string;
  codeVerifier: string;
  returnTo: string;
}

export async function flowCookie(flow: LoginFlowState): Promise<CookieMutation> {
  const config = getConfig();
  return {
    name: flowCookieName(config.secureCookies),
    value: await seal(flow, config.sessionSecret, "flow", 600),
    options: options(config.secureCookies, 600),
  };
}

export async function readFlow(reader: CookieReader): Promise<LoginFlowState | null> {
  const config = getConfig();
  const raw = reader.get(flowCookieName(config.secureCookies))?.value;
  if (!raw) return null;
  const flow = await unseal<LoginFlowState>(raw, config.sessionSecret, "flow");
  if (
    !flow ||
    typeof flow.state !== "string" ||
    typeof flow.nonce !== "string" ||
    typeof flow.codeVerifier !== "string" ||
    typeof flow.returnTo !== "string"
  ) {
    return null;
  }
  return flow;
}

export function clearFlowCookie(): CookieMutation {
  const config = getConfig();
  return {
    name: flowCookieName(config.secureCookies),
    value: "",
    options: options(config.secureCookies, 0),
  };
}
