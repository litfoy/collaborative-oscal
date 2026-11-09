export interface Page {
  total: number;
  limit: number;
  offset: number;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  role: string;
  permissions: string[];
}

export interface RevisionSummary {
  id: string;
  catalog_id: string;
  revision_number: number;
  lifecycle_status: "draft" | "published" | "superseded" | "withdrawn" | string;
  oscal_document_uuid: string;
  oscal_version: string;
  source_version: string | null;
  source_format: string | null;
  created_at: string;
  published_at: string | null;
  control_count: number;
}

export interface RevisionDetail extends RevisionSummary {
  group_count: number;
  source_document: {
    title: string | null;
    version: string | null;
    last_modified: string | null;
    published: string | null;
  };
}

export interface Catalog {
  id: string;
  name: string;
  description: string | null;
  origin_type: "imported" | "custom";
  source_uri: string | null;
  source_organization: string | null;
  license_identifier: string | null;
  revision_count: number;
  latest_revision: RevisionSummary | null;
}

export interface OutlineNode {
  kind: "group" | "control";
  id: string;
  oscal_id: string | null;
  title: string;
  child_count: number;
}

export interface ControlReference {
  catalog_id: string;
  revision_id: string;
  oscal_control_id: string;
}

export interface GroupRef {
  id: string;
  oscal_group_id: string | null;
  title: string;
}

export interface ControlListItem {
  id: string;
  oscal_control_id: string;
  title: string;
  parent_control_id: string | null;
  group: GroupRef | null;
  reference: ControlReference;
}

export interface Property {
  name: string;
  value: string;
  ns?: string | null;
  class?: string | null;
  uuid?: string | null;
  remarks?: string | null;
}

export interface Link {
  href: string;
  rel?: string | null;
  text?: string | null;
  media_type?: string | null;
}

export interface Part {
  id?: string | null;
  name: string;
  ns?: string | null;
  class?: string | null;
  title?: string | null;
  prose?: string | null;
  props: Property[];
  links: Link[];
  parts: Part[];
}

export interface Parameter {
  id: string;
  class?: string | null;
  label?: string | null;
  usage?: string | null;
  values: string[];
  select?: { how_many?: string | null; choices: string[] } | null;
  constraints: { description?: string | null; tests: { expression: string; remarks?: string | null }[] }[];
  guidelines: string[];
  depends_on?: string | null;
  props: Property[];
  links: Link[];
}

export interface Reference {
  uuid: string;
  title: string | null;
  description: string | null;
  citation: string | null;
  rlinks: { href: string; media_type?: string | null }[];
}

export interface Ancestor {
  kind: "group" | "control";
  id: string;
  oscal_id: string | null;
  title: string;
}

export interface ControlDetail {
  id: string;
  reference: ControlReference;
  oscal_document_uuid: string;
  oscal_version: string;
  oscal_control_id: string;
  title: string;
  class: string | null;
  structural_path: string;
  group: GroupRef | null;
  parent_control_id: string | null;
  ancestors: Ancestor[];
  child_control_count: number;
  parts: Part[];
  parameters: Parameter[];
  properties: Property[];
  links: Link[];
  references: Reference[];
  source_catalog: {
    id: string;
    name: string;
    origin_type: "imported" | "custom";
    source_organization: string | null;
    source_uri: string | null;
    license_identifier: string | null;
  };
  source_revision: {
    id: string;
    revision_number: number;
    lifecycle_status: string;
    oscal_document_uuid: string;
    oscal_version: string;
    source_version: string | null;
  };
}

export interface Paged<T> extends Page {
  items: T[];
}
