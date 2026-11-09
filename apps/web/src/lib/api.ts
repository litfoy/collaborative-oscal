import "server-only";

import { getConfig } from "./config";
import { ApiError, ERROR_MESSAGES, kindForStatus } from "./errors";
import { requireSession } from "./auth";
import type { SessionData } from "./session-crypto";
import type { Catalog, ControlDetail, Paged, OutlineNode, RevisionDetail, RevisionSummary, Tenant } from "./types";

/** Server-side call to FastAPI using the session's API access token (never the ID token). */
export async function backendFetch(
  session: SessionData,
  path: string,
  search?: URLSearchParams,
): Promise<Response> {
  const url = new URL(`${getConfig().apiBaseUrl}${path}`);
  if (search) url.search = search.toString();
  try {
    return await fetch(url, {
      headers: { Authorization: `Bearer ${session.accessToken}`, Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    throw new ApiError("unavailable", 503, ERROR_MESSAGES.unavailable);
  }
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
