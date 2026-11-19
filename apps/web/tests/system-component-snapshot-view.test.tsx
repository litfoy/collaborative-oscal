// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SystemComponentSnapshotView } from "@/components/SystemComponentSnapshotView";
import { LocaleProvider } from "@/lib/i18n/provider";
import type { SystemComponent } from "@/lib/types";

const component: SystemComponent = {
  id: "component-id",
  system_id: "system-id",
  oscal_component_uuid: "component-oscal-uuid",
  is_system_component: false,
  source_snapshot_id: "11111111-1111-1111-1111-111111111111",
  source_component_uuid: "22222222-2222-2222-2222-222222222222",
  component: {
    uuid: "component-oscal-uuid",
    type: "service",
    title: "Identity service",
    description: "Runs in production",
    purpose: "Authentication",
    status: { state: "operational" },
  },
};

const snapshot = {
  "component-definition": {
    metadata: {
      title: "Reusable identity guidance",
      version: "2.3.0",
      "oscal-version": "1.1.2",
      "last-modified": "2026-10-01T00:00:00Z",
    },
    components: [
      {
        uuid: component.source_component_uuid,
        type: "service",
        title: "Reusable identity service",
        description: "Reusable source guidance.",
        status: { state: "operational" },
        links: [{ href: "https://example.test/guidance", rel: "reference", text: "Guidance" }],
        "control-implementations": [
          {
            "implemented-requirements": [
              {
                "control-id": "ac-1",
                description: "Document policy ownership.",
                statements: [{ description: "Tie policy ownership to accountable role." }],
              },
            ],
          },
        ],
      },
    ],
  },
};

describe("SystemComponentSnapshotView", () => {
  it("renders immutable snapshot metadata and keeps raw OSCAL JSON as a secondary action", () => {
    render(
      <LocaleProvider locale="en">
        <SystemComponentSnapshotView
          tenantId="tenant-id"
          systemId="system-id"
          systemName="Identity"
          component={component}
          snapshot={snapshot}
        />
      </LocaleProvider>,
    );

    expect(screen.getByText("This is an immutable historical snapshot captured at adoption time. It does not automatically follow newer Component Definition revisions.")).toBeVisible();
    expect(screen.getByText("Reusable identity guidance")).toBeVisible();
    expect(screen.getByText("ac-1")).toBeVisible();
    expect(screen.getByRole("link", { name: "Open raw snapshot JSON" })).toHaveAttribute(
      "href",
      "/bff/tenants/tenant-id/component-definition-snapshots/11111111-1111-1111-1111-111111111111/components/22222222-2222-2222-2222-222222222222/export",
    );
  });
});

