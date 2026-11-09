import type { Catalog, ControlDetail, OutlineNode, Paged, RevisionSummary } from "@/lib/types";

export const TENANT = "11111111-1111-4111-8111-111111111111";
export const CATALOG = "22222222-2222-4222-8222-222222222222";
export const REVISION = "33333333-3333-4333-8333-333333333333";

export function page<T>(items: T[], total = items.length): Paged<T> {
  return { items, total, limit: 50, offset: 0 };
}

export const groupAc: OutlineNode = { kind: "group", id: "g-ac", oscal_id: "ac", title: "Access Control", child_count: 3 };
export const groupIr: OutlineNode = { kind: "group", id: "g-ir", oscal_id: "ir", title: "Incident Response", child_count: 1 };
export const ac1: OutlineNode = { kind: "control", id: "c-ac1", oscal_id: "ac-1", title: "Access Policy", child_count: 1 };
export const ac11: OutlineNode = { kind: "control", id: "c-ac11", oscal_id: "ac-1.1", title: "Policy Exceptions", child_count: 0 };
export const ac2: OutlineNode = { kind: "control", id: "c-ac2", oscal_id: "ac-2", title: "Account Management", child_count: 0 };

export function revision(overrides: Partial<RevisionSummary> = {}): RevisionSummary {
  return {
    id: REVISION,
    catalog_id: CATALOG,
    revision_number: 1,
    lifecycle_status: "published",
    oscal_document_uuid: "44444444-4444-4444-8444-444444444444",
    oscal_version: "1.2.1",
    source_version: "1.0.0",
    source_format: "json",
    created_at: "2025-01-01T00:00:00Z",
    published_at: null,
    control_count: 6,
    ...overrides,
  };
}

export function catalog(overrides: Partial<Catalog> = {}): Catalog {
  return {
    id: CATALOG,
    name: "Sample Security Practices",
    description: "A sample",
    origin_type: "imported",
    source_uri: "https://example.com/catalog",
    source_organization: "Example Org",
    license_identifier: "CC0-1.0",
    revision_count: 1,
    latest_revision: revision(),
    ...overrides,
  };
}

export function control(overrides: Partial<ControlDetail> = {}): ControlDetail {
  return {
    id: "c-ac1",
    reference: { catalog_id: CATALOG, revision_id: REVISION, oscal_control_id: "ac-1" },
    oscal_document_uuid: "44444444-4444-4444-8444-444444444444",
    oscal_version: "1.2.1",
    oscal_control_id: "ac-1",
    title: "Access Policy",
    class: null,
    structural_path: "/catalog/groups/0/controls/0",
    group: { id: "g-ac", oscal_group_id: "ac", title: "Access Control" },
    parent_control_id: null,
    ancestors: [{ kind: "group", id: "g-ac", oscal_id: "ac", title: "Access Control" }],
    child_control_count: 1,
    parts: [
      {
        id: "ac-1_smt",
        name: "statement",
        prose: "Review every {{ insert: param, ac-1_prm_1 }}.",
        props: [],
        links: [],
        parts: [{ id: "ac-1_smt.a", name: "item", prose: "Nested item", props: [{ name: "label", value: "a." }], links: [], parts: [] }],
      },
    ],
    parameters: [{ id: "ac-1_prm_1", label: "frequency", values: ["annually"], constraints: [], guidelines: [], props: [], links: [] }],
    properties: [{ name: "label", value: "AC-1" }],
    links: [{ href: "https://example.com/doc", text: "Doc", rel: "reference" }],
    references: [
      { uuid: "r1", title: "Policy template", description: null, citation: null, rlinks: [{ href: "https://example.com/t" }] },
    ],
    source_catalog: {
      id: CATALOG,
      name: "Sample Security Practices",
      origin_type: "imported",
      source_organization: "Example Org",
      source_uri: null,
      license_identifier: null,
    },
    source_revision: {
      id: REVISION,
      revision_number: 1,
      lifecycle_status: "published",
      oscal_document_uuid: "44444444-4444-4444-8444-444444444444",
      oscal_version: "1.2.1",
      source_version: "1.0.0",
    },
    ...overrides,
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
