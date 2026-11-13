import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

import { backendFetch } from "@/lib/api";
import { getConfig } from "@/lib/config";
import { filterBffQuery, isAllowedBffPath, isAllowedBffRequest, isCatalogImportPath } from "@/lib/bff-allowlist";
import { readSession } from "@/lib/session";

const NO_STORE = { "Cache-Control": "no-store" };
const MAX_PROFILE_BODY_BYTES = 3 * 1024 * 1024;
const MAX_CATALOG_BODY_BYTES = 100 * 1024 * 1024;

function json(body: unknown, status: number): NextResponse {
  return NextResponse.json(body, { status, headers: NO_STORE });
}

function rejectCrossSite(request: NextRequest): boolean {
  const fetchSite = request.headers.get("sec-fetch-site");
  return (
    request.headers.get("origin") !== getConfig().appUrl.origin ||
    (fetchSite !== null && fetchSite !== "same-origin")
  );
}

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
  if (upstream.status === 204) return new NextResponse(null, { status: 204, headers: NO_STORE });
  if (!upstream.headers.get("content-type")?.includes("application/json")) {
    return json({ error: "unavailable" }, 502);
  }
  const contentDisposition = upstream.headers.get("content-disposition");
  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: {
      ...NO_STORE,
      "Content-Type": "application/json",
      ...(contentDisposition ? { "Content-Disposition": contentDisposition } : {}),
    },
  });
}

async function mutate(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
  method: "POST" | "PUT" | "DELETE",
): Promise<NextResponse> {
  if (rejectCrossSite(request)) return json({ error: "forbidden" }, 403);
  const { path } = await context.params;
  if (!isAllowedBffRequest(path, method)) return json({ error: "not_found" }, 404);
  const isImport = method === "POST" && isCatalogImportPath(path);
  const maxBytes = isImport ? MAX_CATALOG_BODY_BYTES : MAX_PROFILE_BODY_BYTES;
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return json({ error: "invalid_content_type" }, 415);
  }
  const declaredLength = Number(request.headers.get("content-length") ?? 0);
  if (declaredLength > maxBytes) return json({ error: "request_too_large" }, 413);

  const session = await readSession(await cookies());
  if (!session || session.accessTokenExpiresAt <= Math.floor(Date.now() / 1000)) {
    return json({ error: "session_expired" }, 401);
  }
  const reader = request.body?.getReader();
  if (!reader) return json({ error: "invalid_json" }, 400);
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  while (true) {
    let result: ReadableStreamReadResult<Uint8Array>;
    try {
      result = await reader.read();
    } catch {
      return json({ error: "invalid_json" }, 400);
    }
    if (result.done) break;
    totalBytes += result.value.byteLength;
    if (totalBytes > maxBytes) {
      await reader.cancel();
      return json({ error: "request_too_large" }, 413);
    }
    chunks.push(result.value);
  }
  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  let body: string | Uint8Array<ArrayBuffer> = bytes;
  if (!isImport) {
    body = new TextDecoder().decode(bytes);
    try {
      JSON.parse(body);
    } catch {
      return json({ error: "invalid_json" }, 400);
    }
  }

  let upstream: Response;
  try {
    upstream = await backendFetch(
      session,
      `/api/v1/${path.join("/")}`,
      undefined,
      isImport ? { method, body, timeoutMs: 120_000 } : { method, body },
    );
  } catch {
    return json({ error: "unavailable" }, 503);
  }
  if (upstream.status === 401) return json({ error: "session_expired" }, 401);
  if (upstream.status === 204) return new NextResponse(null, { status: 204, headers: NO_STORE });
  if (!upstream.headers.get("content-type")?.includes("application/json")) {
    return json({ error: "unavailable" }, 502);
  }
  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: { ...NO_STORE, "Content-Type": "application/json" },
  });
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  return mutate(request, context, "POST");
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  return mutate(request, context, "PUT");
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  return mutate(request, context, "DELETE");
}
