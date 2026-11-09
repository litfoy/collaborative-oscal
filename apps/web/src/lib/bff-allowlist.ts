const UUID = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const OSCAL_ID = "[A-Za-z0-9._:-]{1,128}";

// Read-only catalog endpoints the browser may reach through the BFF.
const ALLOWED = [
  new RegExp(`^tenants/${UUID}/catalogs$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions/${UUID}$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions/${UUID}/outline$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions/${UUID}/controls$`),
  new RegExp(`^tenants/${UUID}/catalogs/${UUID}/revisions/${UUID}/controls/${OSCAL_ID}$`),
];

const ALLOWED_QUERY = new Set(["q", "limit", "offset", "parent_kind", "parent_id", "lifecycle_status"]);

export function isAllowedBffPath(segments: string[]): boolean {
  if (segments.some((segment) => segment === "" || segment === "." || segment === "..")) return false;
  const path = segments.join("/");
  return ALLOWED.some((pattern) => pattern.test(path));
}

export function filterBffQuery(source: URLSearchParams): URLSearchParams {
  const filtered = new URLSearchParams();
  for (const [key, value] of source) {
    if (ALLOWED_QUERY.has(key) && value.length <= 200) filtered.append(key, value);
  }
  return filtered;
}
