import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

import { backendFetch } from "@/lib/api";
import { filterBffQuery, isAllowedBffPath } from "@/lib/bff-allowlist";
import { readSession } from "@/lib/session";

const NO_STORE = { "Cache-Control": "no-store" };

function json(body: unknown, status: number): NextResponse {
  return NextResponse.json(body, { status, headers: NO_STORE });
}

// Read-only proxy for the browser. Only GET is exported, so other methods return 405.
export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite && fetchSite !== "same-origin" && fetchSite !== "none") {
    return json({ error: "forbidden" }, 403);
  }
  const { path } = await context.params;
  if (!isAllowedBffPath(path)) {
    return json({ error: "not_found" }, 404);
  }
  const session = await readSession(await cookies());
  if (!session || session.accessTokenExpiresAt <= Math.floor(Date.now() / 1000)) {
    return json({ error: "session_expired" }, 401);
  }
  let upstream: Response;
  try {
    upstream = await backendFetch(
      session,
      `/api/v1/${path.join("/")}`,
      filterBffQuery(request.nextUrl.searchParams),
    );
  } catch {
    return json({ error: "unavailable" }, 503);
  }
  if (upstream.status === 401) return json({ error: "session_expired" }, 401);
  if (!upstream.headers.get("content-type")?.includes("application/json")) {
    return json({ error: "unavailable" }, 502);
  }
  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: { ...NO_STORE, "Content-Type": "application/json" },
  });
}
