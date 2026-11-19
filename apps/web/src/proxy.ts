// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { NextResponse, type NextRequest } from "next/server";

import { refreshSession } from "@/lib/oidc";
import { getConfig } from "@/lib/config";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n/locale";
import {
  applyMutations,
  hasSessionCookie,
  readSession,
  sessionCookieMutations,
  type CookieMutation,
} from "@/lib/session";

const REFRESH_WINDOW_SECONDS = 60;

function sessionEnded(request: NextRequest, mutations: CookieMutation[]): NextResponse {
  const path = request.nextUrl.pathname;
  let response: NextResponse;
  if (path.startsWith("/bff/")) {
    response = NextResponse.json({ error: "session_expired" }, { status: 401 });
  } else if (path === "/") {
    const forwarded = new Headers(request.headers);
    forwarded.delete("cookie");
    const locale = request.cookies.get(LOCALE_COOKIE)?.value;
    if (locale) forwarded.set("cookie", `${LOCALE_COOKIE}=${resolveLocale(locale)}`);
    response = NextResponse.next({ request: { headers: forwarded } });
  } else {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "?reason=expired";
    response = NextResponse.redirect(url);
  }
  applyMutations(response.cookies, mutations);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

function withCookies(request: NextRequest, mutations: CookieMutation[]): Headers {
  const jar = new Map(request.cookies.getAll().map(({ name, value }) => [name, value]));
  for (const mutation of mutations) {
    if (mutation.value) jar.set(mutation.name, mutation.value);
    else jar.delete(mutation.name);
  }
  const headers = new Headers(request.headers);
  headers.set("cookie", [...jar].map(([name, value]) => `${name}=${value}`).join("; "));
  return headers;
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const config = getConfig();
  if (config.authMode === "demo") {
    if (request.headers.get("host") !== config.appUrl.host) {
      return NextResponse.json({ error: "invalid_host" }, { status: 400, headers: { "Cache-Control": "no-store" } });
    }
    return NextResponse.next();
  }
  if (request.nextUrl.pathname.startsWith("/auth/") || request.nextUrl.pathname === "/signed-out") {
    return NextResponse.next();
  }
  if (!hasSessionCookie(request.cookies)) {
    return NextResponse.next();
  }
  const session = await readSession(request.cookies);
  if (!session) {
    return sessionEnded(request, await sessionCookieMutations(request.cookies, null));
  }
  const now = Math.floor(Date.now() / 1000);
  if (session.accessTokenExpiresAt - now > REFRESH_WINDOW_SECONDS) {
    return NextResponse.next();
  }
  const refreshed = await refreshSession(session);
  if (!refreshed) {
    if (session.accessTokenExpiresAt > now) return NextResponse.next();
    return sessionEnded(request, await sessionCookieMutations(request.cookies, null));
  }
  const mutations = await sessionCookieMutations(request.cookies, refreshed);
  const response = NextResponse.next({ request: { headers: withCookies(request, mutations) } });
  applyMutations(response.cookies, mutations);
  return response;
}

export const config = {
  matcher: ["/((?!_next/|favicon.ico).*)"],
};
