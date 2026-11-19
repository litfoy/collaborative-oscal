// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

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

export interface Profile {
  id: string;
  tenant_id: string;
  catalog_id: string;
  revision_id: string;
  title: string;
  description?: string;
  oscal_version?: string;
  control_ids: string[];
  imports?: ProfileImport[];
  created_at: string;
  updated_at: string;
  concurrency_version: number;
}

export interface ComponentRequirement {
  catalog_id: string;
  revision_id: string;
  control_id: string;
  description: string;
}

export interface ReusableComponent {
  id: string;
  oscal_uuid: string;
  type: string;
  title: string;
  description: string;
  requirements: ComponentRequirement[];
}

export interface ComponentDefinition {
  id: string;
  tenant_id: string;
  title: string;
  oscal_document_uuid: string;
  oscal_version: string;
  version: string;
  components: ReusableComponent[];
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

export interface ComponentRequirementInput {
  catalog_id: string;
  revision_id: string;
  control_id: string;
  description: string;
}

export interface ReusableComponentInput {
  id?: string;
  type: string;
  title: string;
  description: string;
  requirements: ComponentRequirementInput[];
}

export interface ComponentDefinitionInput {
  title: string;
  components: ReusableComponentInput[];
}

export interface MappingEntry {
  id: string;
  relationship: string;
  matching_rationale: string;
  justification: string;
  sources: (string | MappingControlReference)[];
  targets: (string | MappingControlReference)[];
}

export type MappingControlReference = { type?: string } & (
  | { "id-ref": string }
  | { id_ref: string }
  | { control_id: string }
);

export interface MappingPair {
  id: string;
  source_catalog_id: string;
  source_revision_id: string;
  target_catalog_id: string;
  target_revision_id: string;
  entries: MappingEntry[];
}

export interface MappingCollection {
  id: string;
  tenant_id: string;
  title: string;
  description: string;
  oscal_version: string;
  oscal_document_uuid: string;
  version: string;
  mappings: MappingPair[];
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  concurrency_version: number;
}

export interface MappingEntryInput {
  id?: string;
  sources: string[];
  targets: string[];
  relationship: "equal-to" | "equivalent-to" | "subset-of" | "superset-of" | "intersects-with" | "no-relationship";
  matching_rationale: "syntactic" | "semantic" | "functional";
  justification: string;
}

export interface MappingPairInput {
  id?: string;
  source_catalog_id: string;
  source_revision_id: string;
  target_catalog_id: string;
  target_revision_id: string;
  entries: MappingEntryInput[];
}

export interface MappingCollectionInput {
  title: string;
  description: string;
  mappings: MappingPairInput[];
}

export interface RelatedControl {
  catalog_id: string;
  catalog_name: string;
  revision_id: string;
  revision_number: number;
  control_id: string;
  title: string;
}

export interface RelatedMapping {
  collection_id: string;
  collection_title: string;
  mapping_uuid: string;
  entry_uuid: string;
  relationship: string;
  matching_rationale: string;
  matched_side: "source" | "target";
  sources: RelatedControl[];
  targets: RelatedControl[];
}

export interface ProfileImport {
  id: string;
  catalog_id: string;
  revision_id: string;
  control_ids: string[];
}

export type ImplementationStatus = "not_started" | "in_progress" | "implemented" | "not_applicable";
export interface Responsibility {
  kind: "accountable" | "responsible" | "participant";
  user_id: string | null;
  role: string;
}
export interface Implementation {
  id: string;
  tenant_id: string;
  organization_id: string | null;
  profile_id: string | null;
  profile_import_id?: string | null;
  catalog_id: string;
  revision_id: string;
  oscal_control_id: string;
  description: string;
  status: ImplementationStatus;
  oscal_implementation_status?: OscalImplementationStatus | null;
  oscal_status_explanation?: string | null;
  system_id?: string | null;
  system_component_id?: string | null;
  responsibilities: Responsibility[];
  evidence_references: string[];
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

export type OscalImplementationStatus =
  | "implemented"
  | "partial"
  | "planned"
  | "alternative"
  | "not-applicable";

export interface SystemIdentifier {
  id: string;
  "identifier-type"?: string;
}

export interface SystemInformationType {
  uuid: string;
  title: string;
  description: string;
}

export interface InformationSystem {
  id: string;
  tenant_id: string;
  organization_id: string | null;
  name: string;
  description: string | null;
  system_boundary: string | null;
  system_ids: SystemIdentifier[];
  information_types: SystemInformationType[];
  operational_status: string | null;
  status_remarks: string | null;
  security_sensitivity_level: string | null;
  created_at: string;
  updated_at: string;
}

export interface SystemComponent {
  id: string;
  system_id: string;
  oscal_component_uuid: string;
  component: {
    uuid: string;
    type: string;
    title: string;
    description: string;
    purpose?: string;
    status: { state: string; remarks?: string };
  };
  is_system_component: boolean;
  source_snapshot_id: string | null;
  source_component_uuid: string | null;
}

export interface IncludedImplementation {
  implementation_id: string;
  oscal_control_id: string;
  system_component_id: string;
}

export interface SystemSecurityPlan {
  id: string;
  tenant_id: string;
  system_id: string;
  catalog_id: string;
  revision_id: string;
  catalog_name: string;
  title: string;
  control_implementation_description: string | null;
  included_implementations: IncludedImplementation[];
  baseline_control_count: number;
  documented_control_count: number;
  created_at: string;
  updated_at: string;
  concurrency_version: number;
}

export interface SystemSecurityPlanDiagnostic {
  severity: "error" | "warning";
  code: string;
  message: string;
  category?: string;
  path?: string;
}

export interface SystemSecurityPlanValidation {
  valid: boolean;
  diagnostics: SystemSecurityPlanDiagnostic[];
  baseline_control_count: number;
  documented_control_count: number;
}

export interface SystemSecurityPlanVersion {
  id: string;
  system_security_plan_id: string;
  catalog_id: string;
  revision_id: string;
  oscal_document_uuid: string;
  oscal_version: string;
  document_version: string;
  last_modified: string;
  content_sha256: string;
  diagnostics: SystemSecurityPlanDiagnostic[];
  created_at: string;
  created?: boolean;
  concurrency_version?: number | null;
}

export type AssessmentMethod = "EXAMINE" | "INTERVIEW" | "TEST";

export interface AssessmentSourceObjective {
  objective_id: string;
  control_id: string;
}

export interface AssessmentLocalObjective {
  objective_id: string;
  control_id: string;
  description: string;
  methods: AssessmentMethod[];
}

export interface AssessmentActivityStep {
  id: string;
  title: string;
  description: string;
}

export interface AssessmentActivity {
  id: string;
  title: string;
  description: string;
  methods: AssessmentMethod[];
  steps: AssessmentActivityStep[];
  control_ids: string[];
  objective_ids: string[];
  planned_evidence: string | null;
}

export interface AssessmentTask {
  id: string;
  title: string;
  description: string | null;
  activity_ids: string[];
  subject_uuids: string[];
  role_ids: string[];
  on_date: string | null;
  start: string | null;
  end: string | null;
}

export interface AssessmentRole {
  role_id: string;
  title: string;
  description: string | null;
  party_uuids: string[];
}

export interface AssessmentParty {
  uuid: string;
  party_type: "person" | "organization";
  name: string;
}

export interface AssessmentPlan {
  id: string;
  tenant_id: string;
  system_id: string;
  system_security_plan_id: string;
  system_security_plan_version_id: string;
  title: string;
  description: string | null;
  control_ids: string[];
  source_objectives: AssessmentSourceObjective[];
  local_objectives: AssessmentLocalObjective[];
  subject_uuids: string[];
  activities: AssessmentActivity[];
  tasks: AssessmentTask[];
  roles: AssessmentRole[];
  parties: AssessmentParty[];
  terms: string | null;
  baseline_catalog_id: string;
  baseline_revision_id: string;
  ssp_oscal_version: string;
  created_at: string;
  updated_at: string;
  concurrency_version: number;
}

export interface AssessmentSourceObjectiveCatalogItem {
  objective_id: string;
  control_id: string;
  title: string;
  description: string | null;
}

export interface AssessmentPlanValidation {
  valid: boolean;
  diagnostics: SystemSecurityPlanDiagnostic[];
  source_objectives: AssessmentSourceObjectiveCatalogItem[];
  oscal_candidate?: Record<string, unknown> | null;
}

export interface AssessmentPlanVersion {
  id: string;
  assessment_plan_id: string;
  system_security_plan_version_id: string;
  oscal_document_uuid: string;
  oscal_version: string;
  document_version: string;
  last_modified: string;
  content_sha256: string;
  diagnostics: SystemSecurityPlanDiagnostic[];
  created_at: string;
  created?: boolean;
  concurrency_version?: number | null;
}

export type AssessmentResultTargetType = "statement-id" | "objective-id";

export interface AssessmentResultEvidence {
  id: string;
  title: string;
  description: string;
  href: string | null;
}

export interface AssessmentResultObservation {
  id: string;
  title: string;
  description: string;
  methods: AssessmentMethod[];
  collected_at: string;
  subject_uuids: string[];
  evidence: AssessmentResultEvidence[];
}

export interface AssessmentResultFinding {
  id: string;
  title: string;
  description: string;
  target_type: AssessmentResultTargetType;
  target_id: string;
  status: "satisfied" | "other" | "not-satisfied";
  related_observation_ids: string[];
}

export interface AssessmentResultSubjectOption {
  uuid: string;
  title: string;
  type: string;
}

export interface AssessmentResultStatementOption {
  statement_id: string;
  control_id: string;
  title: string;
}

export interface AssessmentResultObjectiveOption {
  objective_id: string;
  control_id: string;
  title: string;
}

export interface AssessmentResult {
  id: string;
  tenant_id: string;
  system_id: string;
  assessment_plan_id: string;
  assessment_plan_version_id: string;
  title: string;
  description: string | null;
  planned_control_ids: string[];
  reviewed_control_ids: string[];
  observations: AssessmentResultObservation[];
  findings: AssessmentResultFinding[];
  subject_options: AssessmentResultSubjectOption[];
  statement_options: AssessmentResultStatementOption[];
  objective_options: AssessmentResultObjectiveOption[];
  start: string | null;
  end: string | null;
  created_at: string;
  updated_at: string;
  concurrency_version: number;
}

export interface AssessmentResultValidation {
  valid: boolean;
  diagnostics: SystemSecurityPlanDiagnostic[];
  planned_control_ids: string[];
  subject_options: AssessmentResultSubjectOption[];
  statement_options: AssessmentResultStatementOption[];
  objective_options: AssessmentResultObjectiveOption[];
  oscal_candidate?: Record<string, unknown> | null;
}

export interface AssessmentResultVersion {
  id: string;
  assessment_result_id: string;
  assessment_plan_version_id: string;
  oscal_document_uuid: string;
  oscal_version: string;
  document_version: string;
  last_modified: string;
  content_sha256: string;
  diagnostics: SystemSecurityPlanDiagnostic[];
  created_at: string;
  created?: boolean;
  concurrency_version?: number | null;
}

export interface ProfileBrowserNode {
  key: string;
  parent_key: string | null;
  kind: "group" | "control";
  id: string | null;
  title: string;
  text: string;
  properties: Property[];
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
  raw_control?: Record<string, unknown>;
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