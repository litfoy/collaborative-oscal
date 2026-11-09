import { NextResponse, type NextRequest } from "next/server";

import { getConfig } from "@/lib/config";
import { beginAuthorization } from "@/lib/oidc";
import { applyMutations, flowCookie } from "@/lib/session";
import { safeReturnTo } from "@/lib/safe";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const config = getConfig();
  const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));
  try {
    const { url, flow } = await beginAuthorization(returnTo);
    const response = NextResponse.redirect(url, 303);
    applyMutations(response.cookies, [await flowCookie(flow)]);
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch {
    const failure = new URL("/?error=provider_unavailable", config.appUrl);
    return NextResponse.redirect(failure, 303);
  }
}
