import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssessmentResultWorkspace } from "@/components/AssessmentResultWorkspace";
import { LocaleProvider } from "@/lib/i18n/provider";
import type {
  AssessmentPlan,
  AssessmentResult,
  AssessmentResultValidation,
  AssessmentResultVersion,
  InformationSystem,
} from "@/lib/types";

import { TENANT, jsonResponse } from "./fixtures";

const system: InformationSystem = {
  id: "system",
  tenant_id: TENANT,
  organization_id: null,
  name: "Identity System",
  description: null,
  system_boundary: null,
  system_ids: [],
  information_types: [],
  operational_status: null,
  status_remarks: null,
  security_sensitivity_level: null,
  created_at: "",
  updated_at: "",
};

const plan: AssessmentPlan = {
  id: "plan",
  tenant_id: TENANT,
  system_id: system.id,
  system_security_plan_id: "ssp",
  system_security_plan_version_id: "ssp-v1",
  title: "Assessment Plan",
  description: null,
  control_ids: ["ac-1"],
  source_objectives: [],
  local_objectives: [],
  subject_uuids: [],
  activities: [],
  tasks: [],
  roles: [],
  parties: [],
  terms: null,
  baseline_catalog_id: "catalog",
  baseline_revision_id: "revision",
  ssp_oscal_version: "1.2.1",
  created_at: "",
  updated_at: "",
};

const result: AssessmentResult = {
  id: "result",
  tenant_id: TENANT,
  system_id: system.id,
  assessment_plan_id: plan.id,
  assessment_plan_version_id: "ap-v1",
  title: "Results Alpha",
  description: null,
  reviewed_control_ids: ["ac-1"],
  observations: [],
  findings: [],
  subject_options: [{ uuid: "component-1", title: "Auth Service", type: "service" }],
  statement_options: [{ statement_id: "ac-1_smt", control_id: "ac-1", title: "Statement" }],
  objective_options: [{ objective_id: "local-1", control_id: "ac-1", title: "Objective" }],
  start: null,
  end: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const validation: AssessmentResultValidation = {
  valid: true,
  diagnostics: [],
  subject_options: result.subject_options,
  statement_options: result.statement_options,
  objective_options: result.objective_options,
  oscal_candidate: null,
};

const versions: AssessmentResultVersion[] = [];

function renderWorkspace() {
  return render(
    <LocaleProvider locale="en">
      <AssessmentResultWorkspace
        tenantId={TENANT}
        system={system}
        plan={plan}
        initialResult={result}
        initialValidation={validation}
        initialVersions={versions}
        canWrite
      />
    </LocaleProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("AssessmentResultWorkspace", () => {
  it("saves structured observation and finding payloads without raw JSON authoring", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse(result));
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();

    await user.click(screen.getByRole("button", { name: "Observations" }));
    await user.click(screen.getByRole("button", { name: "Add observation" }));
    await user.type(screen.getByRole("textbox", { name: "Observation title" }), "MFA log review");
    await user.type(
      screen.getByRole("textbox", { name: "Observation description" }),
      "MFA logs show challenge response.",
    );
    await user.click(screen.getByRole("checkbox", { name: "EXAMINE" }));

    await user.click(screen.getByRole("button", { name: "Findings" }));
    await user.click(screen.getByRole("button", { name: "Add finding" }));
    await user.type(screen.getByRole("textbox", { name: "Finding title" }), "AC-1 verified");
    await user.type(
      screen.getByRole("textbox", { name: "Finding description" }),
      "Evidence supports statement satisfaction.",
    );

    await user.click(screen.getByRole("button", { name: "Save working state" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const firstCall = (fetchMock.mock.calls as unknown[][])[0];
    const init = (firstCall?.[1] ?? undefined) as RequestInit | undefined;
    const body = JSON.parse(String(init?.body ?? "{}"));
    expect(body).toHaveProperty("observations");
    expect(body).toHaveProperty("findings");
    expect(body).toHaveProperty("reviewed_control_ids");
    expect(body).not.toHaveProperty("oscal_candidate");
    expect(body.observations[0].id).toBeTruthy();
    expect(body.findings[0].id).toBeTruthy();
  });
});



