import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MappingWorkspace } from "@/components/MappingWorkspace";
import type { MappingCollection } from "@/lib/types";

const collection: MappingCollection = {
  id: "collection-1",
  tenant_id: "tenant-1",
  title: "Policy relationships",
  description: "",
  oscal_version: "1.2.3",
  oscal_document_uuid: "document-1",
  version: "1.0.0",
  mappings: [{
    id: "mapping-1",
    source_catalog_id: "catalog-1",
    source_revision_id: "revision-1",
    target_catalog_id: "catalog-2",
    target_revision_id: "revision-2",
    entries: [{
      id: "entry-1",
      relationship: "equivalent-to",
      matching_rationale: "semantic",
      justification: "",
      sources: [
        { type: "control", "id-ref": "AC-1" },
        { type: "control", control_id: "AC-2" },
      ],
      targets: [{ type: "control", id_ref: "POL-1" }],
    }],
  }],
  created_by: "user-1",
  updated_by: "user-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("MappingWorkspace", () => {
  it("displays OSCAL control references by their id-ref", () => {
    render(
      <MappingWorkspace
        tenantId="tenant-1"
        catalogs={[]}
        catalogTotal={0}
        canWrite={false}
        initialCollection={collection}
      />,
    );

    expect(screen.getByText("AC-1")).toBeInTheDocument();
    expect(screen.getByText("AC-2")).toBeInTheDocument();
    expect(screen.getByText("POL-1")).toBeInTheDocument();
    expect(screen.queryByText("[object Object]")).not.toBeInTheDocument();
  });
});
