import "server-only";

import { getConfig } from "./config";
import { ApiError, ERROR_MESSAGES, kindForStatus } from "./errors";
import { isDemoPrincipal, requireSession, type WebPrincipal } from "./auth";
import type {
  AssessmentResult,
  AssessmentResultValidation,
  AssessmentResultVersion,
  AssessmentPlan,
  AssessmentPlanValidation,
  AssessmentPlanVersion,
  Catalog,
  ComponentDefinition,
  ControlDetail,
  InformationSystem,
  Implementation,
  MappingCollection,
  Paged,
  OutlineNode,
  Profile,
  RevisionDetail,
  RevisionSummary,
  SystemComponent,
  SystemSecurityPlan,
  SystemSecurityPlanValidation,
  SystemSecurityPlanVersion,
  Tenant,
} from "./types";

/** Server-side call to FastAPI using the mode-specific bearer credential. */
export async function backendFetch(
  session: WebPrincipal,
  path: string,
  search?: URLSearchParams,
  init?: { method: "POST" | "PUT" | "DELETE"; body: string | Uint8Array<ArrayBuffer>; timeoutMs?: number },
): Promise<Response> {
  const config = getConfig();
  const url = new URL(`${config.apiBaseUrl}${path}`);
  let accessToken: string;
  if (isDemoPrincipal(session)) {
    if (config.authMode !== "demo") throw new Error("Authentication mode mismatch.");
    accessToken = config.demoAuthSecret;
  } else {
    if (config.authMode !== "keycloak") throw new Error("Authentication mode mismatch.");
    accessToken = session.accessToken;
  }
  if (search) url.search = search.toString();
  let response: Response;
  try {
    response = await fetch(url, {
      method: init?.method,
      body: init?.body,
      headers: {
        Authorization: `Bearer ${accessToken}`,
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
    if (response.status === 422) {
      const body: unknown = await response.clone().json().catch(() => null);
      console.error("[backend] Validation response detail", {
        path: url.pathname,
        detail: validationLogDetail(body),
      });
    }
  }
  if (config.authMode === "demo" && response.status === 401) {
    throw new ApiError("unavailable", 503, ERROR_MESSAGES.unavailable);
  }
  return response;
}

function validationLogDetail(body: unknown): string | { location: string; type: string; message: string }[] {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return "No structured validation detail.";
  }
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return "Validation response has an unexpected detail format.";
  return detail.map((item) => {
    if (typeof item !== "object" || item === null) {
      return { location: "", type: "unknown", message: "Invalid request." };
    }
    const entry = item as Record<string, unknown>;
    return {
      location: Array.isArray(entry.loc) ? entry.loc.map(String).join(".") : "",
      type: typeof entry.type === "string" ? entry.type : "unknown",
      message: typeof entry.msg === "string" ? entry.msg : "Validation error.",
    };
  });
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

export function listComponentDefinitions(
  tenantId: string,
  returnTo: string,
): Promise<Paged<ComponentDefinition>> {
  return getJson(`/api/v1/tenants/${tenantId}/component-definitions`, returnTo, { limit: 200 });
}

export function getComponentDefinition(
  tenantId: string,
  documentId: string,
  returnTo: string,
): Promise<ComponentDefinition> {
  return getJson(`/api/v1/tenants/${tenantId}/component-definitions/${documentId}`, returnTo);
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

export function listSystems(tenantId: string, returnTo: string): Promise<InformationSystem[]> {
  return getJson(`/api/v1/tenants/${tenantId}/systems`, returnTo);
}

export function getSystem(
  tenantId: string,
  systemId: string,
  returnTo: string,
): Promise<InformationSystem> {
  return getJson(`/api/v1/tenants/${tenantId}/systems/${systemId}`, returnTo);
}

export function listSystemComponents(
  tenantId: string,
  systemId: string,
  returnTo: string,
): Promise<SystemComponent[]> {
  return getJson(`/api/v1/tenants/${tenantId}/systems/${systemId}/components`, returnTo);
}

export function exportComponentDefinitionSnapshotComponent(
  tenantId: string,
  snapshotId: string,
  componentId: string,
  returnTo: string,
): Promise<Record<string, unknown>> {
  return getJson(
    `/api/v1/tenants/${tenantId}/component-definition-snapshots/${snapshotId}/components/${componentId}/export`,
    returnTo,
  );
}

export function listSystemSecurityPlans(
  tenantId: string,
  systemId: string,
  returnTo: string,
): Promise<SystemSecurityPlan[]> {
  return getJson(
    `/api/v1/tenants/${tenantId}/systems/${systemId}/system-security-plans`,
    returnTo,
  );
}

export function getSystemSecurityPlan(
  tenantId: string,
  planId: string,
  returnTo: string,
): Promise<SystemSecurityPlan> {
  return getJson(`/api/v1/tenants/${tenantId}/system-security-plans/${planId}`, returnTo);
}

export function validateSystemSecurityPlan(
  tenantId: string,
  planId: string,
  returnTo: string,
): Promise<SystemSecurityPlanValidation> {
  return getJson(
    `/api/v1/tenants/${tenantId}/system-security-plans/${planId}/validation`,
    returnTo,
  );
}

export function listSystemSecurityPlanVersions(
  tenantId: string,
  planId: string,
  returnTo: string,
): Promise<SystemSecurityPlanVersion[]> {
  return getJson(`/api/v1/tenants/${tenantId}/system-security-plans/${planId}/versions`, returnTo);
}

export function exportSystemSecurityPlanVersion(
  tenantId: string,
  planId: string,
  versionId: string,
  returnTo: string,
): Promise<Record<string, unknown>> {
  return getJson(
    `/api/v1/tenants/${tenantId}/system-security-plans/${planId}/versions/${versionId}/export`,
    returnTo,
  );
}

export function listAssessmentPlans(
  tenantId: string,
  systemId: string,
  returnTo: string,
): Promise<AssessmentPlan[]> {
  return getJson(`/api/v1/tenants/${tenantId}/systems/${systemId}/assessment-plans`, returnTo);
}

export function getAssessmentPlan(
  tenantId: string,
  planId: string,
  returnTo: string,
): Promise<AssessmentPlan> {
  return getJson(`/api/v1/tenants/${tenantId}/assessment-plans/${planId}`, returnTo);
}

export function validateAssessmentPlan(
  tenantId: string,
  planId: string,
  returnTo: string,
): Promise<AssessmentPlanValidation> {
  return getJson(`/api/v1/tenants/${tenantId}/assessment-plans/${planId}/validation`, returnTo);
}

export function listAssessmentPlanVersions(
  tenantId: string,
  planId: string,
  returnTo: string,
): Promise<AssessmentPlanVersion[]> {
  return getJson(`/api/v1/tenants/${tenantId}/assessment-plans/${planId}/versions`, returnTo);
}

export function listAssessmentResults(
  tenantId: string,
  systemId: string,
  returnTo: string,
): Promise<AssessmentResult[]> {
  return getJson(`/api/v1/tenants/${tenantId}/systems/${systemId}/assessment-results`, returnTo);
}

export function getAssessmentResult(
  tenantId: string,
  resultId: string,
  returnTo: string,
): Promise<AssessmentResult> {
  return getJson(`/api/v1/tenants/${tenantId}/assessment-results/${resultId}`, returnTo);
}

export function validateAssessmentResult(
  tenantId: string,
  resultId: string,
  returnTo: string,
): Promise<AssessmentResultValidation> {
  return getJson(`/api/v1/tenants/${tenantId}/assessment-results/${resultId}/validation`, returnTo);
}

export function listAssessmentResultVersions(
  tenantId: string,
  resultId: string,
  returnTo: string,
): Promise<AssessmentResultVersion[]> {
  return getJson(`/api/v1/tenants/${tenantId}/assessment-results/${resultId}/versions`, returnTo);
}

export function listImplementations(
  tenantId: string,
  returnTo: string,
  offset = 0,
): Promise<Paged<Implementation>> {
  return getJson(`/api/v1/tenants/${tenantId}/implementations`, returnTo, {
    limit: 200,
    offset,
  });
}
