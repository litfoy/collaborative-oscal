// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

const UUID = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const OSCAL_ID = "[A-Za-z0-9._:-]{1,128}";

const READ_PATHS = [
  new RegExp(`^tenants/${UUID}/catalogs$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions/${UUID}$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions/${UUID}/outline$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions/${UUID}/profile-browser$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions/${UUID}/controls$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions/${UUID}/controls/${OSCAL_ID}$`),
  new RegExp(`^tenants/${UUID}/profiles$`),
  new RegExp(`^tenants/${UUID}/profiles/${UUID}$`),
  new RegExp(`^tenants/${UUID}/profiles/${UUID}/export$`),
  new RegExp(`^tenants/${UUID}/component-definitions$`),
  new RegExp(`^tenants/${UUID}/component-definitions/${UUID}$`),
  new RegExp(`^tenants/${UUID}/component-definitions/${UUID}/export$`),
  new RegExp(`^tenants/${UUID}/component-definitions/${UUID}/components/${UUID}$`),
  new RegExp(`^tenants/${UUID}/mapping-collections$`),
  new RegExp(`^tenants/${UUID}/mapping-collections/${UUID}$`),
  new RegExp(`^tenants/${UUID}/mapping-collections/${UUID}/export$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions/${UUID}/controls/${OSCAL_ID}/related-mappings$`),
  new RegExp(`^tenants/${UUID}/implementation-options$`),
  new RegExp(`^tenants/${UUID}/implementations$`),
  new RegExp(`^tenants/${UUID}/implementations/${UUID}(/control)?$`),
  new RegExp(`^tenants/${UUID}/systems$`),
  new RegExp(`^tenants/${UUID}/systems/${UUID}$`),
  new RegExp(`^tenants/${UUID}/systems/${UUID}/components$`),
  new RegExp(`^tenants/${UUID}/systems/${UUID}/components/${UUID}$`),
  new RegExp(`^tenants/${UUID}/systems/${UUID}/system-security-plans$`),
  new RegExp(`^tenants/${UUID}/systems/${UUID}/assessment-plans$`),
  new RegExp(`^tenants/${UUID}/systems/${UUID}/assessment-results$`),
  new RegExp(`^tenants/${UUID}/system-security-plans/${UUID}$`),
  new RegExp(`^tenants/${UUID}/assessment-plans/${UUID}$`),
  new RegExp(`^tenants/${UUID}/assessment-results/${UUID}$`),
  new RegExp(`^tenants/${UUID}/system-security-plans/${UUID}/validation$`),
  new RegExp(`^tenants/${UUID}/assessment-plans/${UUID}/validation$`),
  new RegExp(`^tenants/${UUID}/assessment-results/${UUID}/validation$`),
  new RegExp(`^tenants/${UUID}/system-security-plans/${UUID}/implementations/${UUID}$`),
  new RegExp(`^tenants/${UUID}/system-security-plans/${UUID}/versions$`),
  new RegExp(`^tenants/${UUID}/assessment-plans/${UUID}/versions$`),
  new RegExp(`^tenants/${UUID}/assessment-results/${UUID}/versions$`),
  new RegExp(`^tenants/${UUID}/system-security-plans/${UUID}/versions/${UUID}(/export)?$`),
  new RegExp(`^tenants/${UUID}/assessment-plans/${UUID}/versions/${UUID}(/export)?$`),
  new RegExp(`^tenants/${UUID}/assessment-results/${UUID}/versions/${UUID}(/export)?$`),
  new RegExp(`^tenants/${UUID}/component-definition-snapshots/${UUID}/components/${UUID}/export$`),
];
const CREATE_PROFILE = new RegExp(`^tenants/${UUID}/profiles$`);
const UPDATE_PROFILE = new RegExp(`^tenants/${UUID}/profiles/${UUID}$`);
const CREATE_COMPONENT_DEFINITION = new RegExp(`^tenants/${UUID}/component-definitions$`);
const UPDATE_COMPONENT_DEFINITION = new RegExp(`^tenants/${UUID}/component-definitions/${UUID}$`);
const DELETE_COMPONENT_DEFINITION = new RegExp(`^tenants/${UUID}/component-definitions/${UUID}$`);
const DELETE_COMPONENT = new RegExp(`^tenants/${UUID}/component-definitions/${UUID}/components/${UUID}$`);
const CREATE_MAPPING_COLLECTION = new RegExp(`^tenants/${UUID}/mapping-collections$`);
const UPDATE_MAPPING_COLLECTION = new RegExp(`^tenants/${UUID}/mapping-collections/${UUID}$`);
const DELETE_MAPPING_COLLECTION = new RegExp(`^tenants/${UUID}/mapping-collections/${UUID}$`);
const CREATE_IMPLEMENTATION = new RegExp(`^tenants/${UUID}/implementations$`);
const UPDATE_IMPLEMENTATION = new RegExp(`^tenants/${UUID}/implementations/${UUID}$`);
const CREATE_SYSTEM = new RegExp(`^tenants/${UUID}/systems$`);
const UPDATE_SYSTEM = new RegExp(`^tenants/${UUID}/systems/${UUID}$`);
const CREATE_SYSTEM_COMPONENT = new RegExp(`^tenants/${UUID}/systems/${UUID}/components$`);
const UPDATE_SYSTEM_COMPONENT = new RegExp(`^tenants/${UUID}/systems/${UUID}/components/${UUID}$`);
const ADOPT_SYSTEM_COMPONENT = new RegExp(`^tenants/${UUID}/systems/${UUID}/components/adopt$`);
const CREATE_SYSTEM_PLAN = new RegExp(`^tenants/${UUID}/systems/${UUID}/system-security-plans$`);
const CREATE_ASSESSMENT_PLAN = new RegExp(`^tenants/${UUID}/systems/${UUID}/assessment-plans$`);
const CREATE_ASSESSMENT_RESULT = new RegExp(`^tenants/${UUID}/systems/${UUID}/assessment-results$`);
const UPDATE_SYSTEM_PLAN = new RegExp(`^tenants/${UUID}/system-security-plans/${UUID}$`);
const UPDATE_ASSESSMENT_PLAN = new RegExp(`^tenants/${UUID}/assessment-plans/${UUID}$`);
const UPDATE_ASSESSMENT_RESULT = new RegExp(`^tenants/${UUID}/assessment-results/${UUID}$`);
const INCLUDE_SYSTEM_IMPLEMENTATION = new RegExp(`^tenants/${UUID}/system-security-plans/${UUID}/implementations/${UUID}$`);
const CREATE_SYSTEM_PLAN_VERSION = new RegExp(`^tenants/${UUID}/system-security-plans/${UUID}/versions$`);
const CREATE_ASSESSMENT_PLAN_VERSION = new RegExp(`^tenants/${UUID}/assessment-plans/${UUID}/versions$`);
const CREATE_ASSESSMENT_RESULT_VERSION = new RegExp(`^tenants/${UUID}/assessment-results/${UUID}/versions$`);
const IMPORT_CATALOG = new RegExp(`^tenants/${UUID}/catalogs(?:/${UUID})?/import$`);

export function isCatalogImportPath(segments: string[]): boolean {
  return IMPORT_CATALOG.test(segments.join("/"));
}

const ALLOWED_QUERY = new Set(["q", "limit", "offset", "parent_kind", "parent_id", "lifecycle_status", "profile_id", "organization_id", "tenant_scope", "expected_version"]);

export function isAllowedBffPath(segments: string[]): boolean {
  if (segments.some((segment) => segment === "" || segment === "." || segment === "..")) return false;
  const path = segments.join("/");
  return READ_PATHS.some((pattern) => pattern.test(path));
}

export function isAllowedBffRequest(segments: string[], method: string): boolean {
  if (segments.some((segment) => segment === "" || segment === "." || segment === "..")) return false;
  const path = segments.join("/");
  if (method === "GET") return isAllowedBffPath(segments);
  if (method === "POST") return CREATE_MAPPING_COLLECTION.test(path) || CREATE_PROFILE.test(path) || CREATE_COMPONENT_DEFINITION.test(path) || CREATE_IMPLEMENTATION.test(path) || CREATE_SYSTEM.test(path) || CREATE_SYSTEM_COMPONENT.test(path) || ADOPT_SYSTEM_COMPONENT.test(path) || CREATE_SYSTEM_PLAN.test(path) || CREATE_ASSESSMENT_PLAN.test(path) || CREATE_ASSESSMENT_RESULT.test(path) || INCLUDE_SYSTEM_IMPLEMENTATION.test(path) || CREATE_SYSTEM_PLAN_VERSION.test(path) || CREATE_ASSESSMENT_PLAN_VERSION.test(path) || CREATE_ASSESSMENT_RESULT_VERSION.test(path) || IMPORT_CATALOG.test(path);
  if (method === "PUT") return UPDATE_PROFILE.test(path) || UPDATE_COMPONENT_DEFINITION.test(path) || UPDATE_IMPLEMENTATION.test(path) || UPDATE_SYSTEM.test(path) || UPDATE_SYSTEM_COMPONENT.test(path) || UPDATE_SYSTEM_PLAN.test(path) || UPDATE_ASSESSMENT_PLAN.test(path) || UPDATE_ASSESSMENT_RESULT.test(path) || UPDATE_MAPPING_COLLECTION.test(path);
  if (method === "DELETE") return DELETE_MAPPING_COLLECTION.test(path) || DELETE_COMPONENT_DEFINITION.test(path) || DELETE_COMPONENT.test(path) || INCLUDE_SYSTEM_IMPLEMENTATION.test(path);
  return false;
}

export function filterBffQuery(source: URLSearchParams): URLSearchParams {
  const filtered = new URLSearchParams();
  for (const [key, value] of source) {
    if (ALLOWED_QUERY.has(key) && value.length <= 200) filtered.append(key, value);
  }
  return filtered;
}
