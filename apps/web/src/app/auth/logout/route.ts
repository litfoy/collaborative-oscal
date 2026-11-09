import { NextResponse, type NextRequest } from "next/server";

import { getConfig } from "@/lib/config";
import { endSession } from "@/lib/oidc";
import { applyMutations, readSession, sessionCookieMutations } from "@/lib/session";

export const dynamic = "force-dynamic";

// POST-only and Origin-checked so that a cross-site page cannot sign the user out (CSRF).
export async function POST(request: NextRequest): Promise<NextResponse> {
  const config = getConfig();
  const origin = request.headers.get("origin");
  if (origin !== config.appUrl.origin) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const session = await readSession(request.cookies);
  const destination = session ? await endSession(session) : new URL("/signed-out", config.appUrl);
  const response = NextResponse.redirect(destination, 303);
  applyMutations(response.cookies, await sessionCookieMutations(request.cookies, null));
  response.headers.set("Cache-Control", "no-store");
  return response;
}
