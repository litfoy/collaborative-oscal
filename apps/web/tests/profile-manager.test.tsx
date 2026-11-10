// @vitest-environment node
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { ProfileManager } from "@/components/ProfileManager";
import type { Profile } from "@/lib/types";

const mocks = vi.hoisted(() => ({ bffWrite: vi.fn() }));
vi.mock("@/lib/bff-client", () => ({ bffWrite: mocks.bffWrite }));

const TENANT = "11111111-2222-3333-4444-555555555555";
const CATALOG = "aaaaaaaa-2222-3333-4444-555555555555";
const REVISION = "bbbbbbbb-2222-3333-4444-555555555555";
const PROFILE_ID = "cccccccc-2222-3333-4444-555555555555";
const profile: Profile = {
  id: PROFILE_ID,
  tenant_id: TENANT,
  catalog_id: CATALOG,
  revision_id: REVISION,
  title: "Access baseline",
  control_ids: ["ac-1"],
  created_at: "2026-11-10T00:00:00Z",
  updated_at: "2026-11-10T00:00:00Z",
};
const catalogs = [{
  id: CATALOG,
  name: "Sample catalog",
  description: null,
  origin_type: "imported" as const,
  source_uri: null,
  source_organization: null,
  license_identifier: null,
  revision_count: 1,
  latest_revision: {
    id: REVISION,
    catalog_id: CATALOG,
    revision_number: 1,
    lifecycle_status: "draft",
    oscal_document_uuid: PROFILE_ID,
    oscal_version: "1.2.1",
    source_version: "1.0",
    source_format: "json",
    created_at: "2026-11-10T00:00:00Z",
    published_at: null,
    control_count: 1,
  },
}];

describe("ProfileManager", () => {
  it("renders a create form using the latest catalog revision", () => {
    const markup = renderToStaticMarkup(
      <ProfileManager tenantId={TENANT} profiles={[]} catalogs={catalogs} canWrite />,
    );
    expect(markup).toContain("Create profile");
    expect(markup).toContain("Sample catalog — revision 1");
    expect(markup).toContain("Selected OSCAL control IDs");
    expect(markup).toContain("No profiles have been created");
  });

  it("renders existing profiles with source revision and editing fields", () => {
    const markup = renderToStaticMarkup(
      <ProfileManager tenantId={TENANT} profiles={[profile]} catalogs={catalogs} canWrite />,
    );
    expect(markup).toContain("Access baseline");
    expect(markup).toContain("ac-1");
    expect(markup).toContain(`/t/${TENANT}/catalogs/${CATALOG}?revision=${REVISION}`);
    expect(markup).toContain("Save profile");
  });
});
