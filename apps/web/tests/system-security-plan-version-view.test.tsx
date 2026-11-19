// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SystemSecurityPlanVersionView } from "@/components/SystemSecurityPlanVersionView";
import { LocaleProvider } from "@/lib/i18n/provider";
import type { SystemSecurityPlanVersion } from "@/lib/types";

import { CATALOG, REVISION, TENANT } from "./fixtures";

const version: SystemSecurityPlanVersion = {
  id: "version-1",
  system_security_plan_id: "plan",
  catalog_id: CATALOG,
  revision_id: REVISION,
  oscal_document_uuid: "oscal-doc",
  oscal_version: "1.2.3",
  document_version: "1.0",
  last_modified: "2025-01-01T00:00:00Z",
  content_sha256: "hash",
  diagnostics: [],
  created_at: "2025-01-01T00:00:00Z",
  created: true,
};

describe("SystemSecurityPlanVersionView", () => {
  it("renders read-only historical requirements from stored immutable snapshot", () => {
    render(
      <LocaleProvider locale="en">
        <SystemSecurityPlanVersionView
          tenantId={TENANT}
          systemId="system"
          systemName="Identity"
          planId="plan"
          planTitle="Current plan title"
          version={version}
          snapshot={{
            "system-security-plan": {
              metadata: { title: "Historical SSP", version: "1.0" },
              "system-implementation": {
                components: [{ uuid: "component-uuid", title: "Identity app" }],
              },
              "control-implementation": {
                "implemented-requirements": [
                  {
                    "control-id": "ac-1",
                    description: "Policy is documented",
                    "by-components": [
                      {
                        "component-uuid": "component-uuid",
                        description: "Owned by IAM team",
                        status: { state: "implemented" },
                      },
                    ],
                  },
                ],
              },
            },
          }}
        />
      </LocaleProvider>,
    );

    expect(screen.getByRole("heading", { name: "Historical SSP" })).toBeVisible();
    expect(screen.getByText("ac-1")).toBeVisible();
    expect(screen.getByText(/Identity app/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Export stored OSCAL JSON" })).toHaveAttribute(
      "href",
      `/bff/tenants/${TENANT}/system-security-plans/plan/versions/version-1/export`,
    );
  });
});

