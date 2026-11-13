import "server-only";

import { getConfig } from "./config";
import { ApiError, ERROR_MESSAGES, kindForStatus } from "./errors";
import { requireSession } from "./auth";
import type { SessionData } from "./session-crypto";
import type { Catalog, ControlDetail, MappingCollection, Paged, OutlineNode, Profile, RevisionDetail, RevisionSummary, Tenant } from "./types";

/** Server-side call to FastAPI using the session's API access token (never the ID token). */
export async function backendFetch(
  session: SessionData,
  path: string,
  search?: URLSearchParams,
  init?: { method: "POST" | "PUT" | "DELETE"; body: string | Uint8Array<ArrayBuffer>; timeoutMs?: number },
): Promise<Response> {
  const url = new URL(`${getConfig().apiBaseUrl}${path}`);
  if (search) url.search = search.toString();
  let response: Response;
  try {
    response = await fetch(url, {
      method: init?.method,
      body: init?.body,
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
        Accept: "application/json",
        ...(init ? { "Content-Type": "application/json" } : {}),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(init?.timeoutMs ?? 15_000),
    });
  } catch (error) {
    const cause = error instanceof Error ? error.cause : undefined;
    const code = cause && typeof cause === "object" && "code" in cause ? cause.code : undefined;
    const knownCodes = ["ECONNREFUSED", "ECONNRESET", "ENOTFOUND", "EAI_AGAIN", "ETIMEDOUT", "UND_ERR_CONNECT_TIMEOUT"];
    console.error("[backend] Request failed", {
      origin: url.origin,
      path: url.pathname,
      reason: error instanceof Error && error.name === "TimeoutError" ? "timeout" : "connection_error",
      code: typeof code === "string" && knownCodes.includes(code) ? code : "unknown",
    });
    throw new ApiError("unavailable", 503, ERROR_MESSAGES.unavailable);
  }
  if (!response.ok) {
    console.error("[backend] Unsuccessful response", {
      origin: url.origin,
      path: url.pathname,
      status: response.status,
    });
  }
  return response;
}

async function getJson<T>(path: string, returnTo: string, query?: Record<string, string | number | undefined>): Promise<T> {
  const session = await requireSession(returnTo);
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const response = await backendFetch(session, path, search);
  if (!response.ok) {
    const kind = kindForStatus(response.status);
    throw new ApiError(kind, response.status, ERROR_MESSAGES[kind]);
  }
  return (await response.json()) as T;
}

export function listTenants(returnTo: string): Promise<{ items: Tenant[] }> {
  return getJson("/api/v1/tenants", returnTo);
}

export function listCatalogs(
  tenantId: string,
  query: { q?: string; limit?: number; offset?: number },
  returnTo: string,
): Promise<Paged<Catalog>> {
  return getJson(`/api/v1/tenants/${tenantId}/catalogs`, returnTo, query);
}

export function getCatalog(tenantId: string, catalogId: string, returnTo: string): Promise<Catalog> {
  return getJson(`/api/v1/tenants/${tenantId}/catalogs/${catalogId}`, returnTo);
}

export function listRevisions(tenantId: string, catalogId: string, returnTo: string): Promise<Paged<RevisionSummary>> {
  return getJson(`/api/v1/tenants/${tenantId}/catalogs/${catalogId}/revisions`, returnTo, { limit: 100 });
}

export function getRevision(tenantId: string, catalogId: string, revisionId: string, returnTo: string): Promise<RevisionDetail> {
  return getJson(`/api/v1/tenants/${tenantId}/catalogs/${catalogId}/revisions/${revisionId}`, returnTo);
}

export function getOutline(tenantId: string, catalogId: string, revisionId: string, returnTo: string): Promise<Paged<OutlineNode>> {
  return getJson(`/api/v1/tenants/${tenantId}/catalogs/${catalogId}/revisions/${revisionId}/outline`, returnTo, { limit: 200 });
}

export function getControl(tenantId: string, catalogId: string, revisionId: string, controlId: string, returnTo: string): Promise<ControlDetail> {
  return getJson(
    `/api/v1/tenants/${tenantId}/catalogs/${catalogId}/revisions/${revisionId}/controls/${encodeURIComponent(controlId)}`,
    returnTo,
  );
}

export function listProfiles(
  tenantId: string,
  returnTo: string,
): Promise<Paged<Profile>> {
  return getJson(`/api/v1/tenants/${tenantId}/profiles`, returnTo, { limit: 200 });
}

export function listMappingCollections(
  tenantId: string,
  returnTo: string,
): Promise<Paged<MappingCollection>> {
  return getJson(`/api/v1/tenants/${tenantId}/mapping-collections`, returnTo, { limit: 200 });
}

export function getMappingCollection(
  tenantId: string,
  collectionId: string,
  returnTo: string,
): Promise<MappingCollection> {
  return getJson(`/api/v1/tenants/${tenantId}/mapping-collections/${collectionId}`, returnTo);
}
