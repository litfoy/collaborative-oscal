import { NextResponse, type NextRequest } from "next/server";

import { getConfig } from "@/lib/config";
import { completeAuthorization, callbackUrl } from "@/lib/oidc";
import {
  applyMutations,
  clearFlowCookie,
  readFlow,
  sessionCookieMutations,
} from "@/lib/session";
import { safeReturnTo } from "@/lib/safe";

export const dynamic = "force-dynamic";

function redirectTo(path: string): NextResponse {
  const response = NextResponse.redirect(new URL(path, getConfig().appUrl), 303);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const flow = await readFlow(request.cookies);
  if (!flow) {
    return redirectTo("/?error=login_failed");
  }
  // The public URL is used (not request.url) so the redirect_uri matches what was registered.
  const current = callbackUrl();
  current.search = request.nextUrl.search;
  try {
    const session = await completeAuthorization(current, flow);
    const response = redirectTo(safeReturnTo(flow.returnTo));
    applyMutations(response.cookies, [
      ...(await sessionCookieMutations(request.cookies, session)),
      clearFlowCookie(),
    ]);
    return response;
  } catch {
    const response = redirectTo("/?error=login_failed");
    applyMutations(response.cookies, [clearFlowCookie()]);
    return response;
  }
}
