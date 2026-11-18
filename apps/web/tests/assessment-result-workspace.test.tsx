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
  concurrency_version: 1,
};

const result: AssessmentResult = {
  id: "result",
  tenant_id: TENANT,
  system_id: system.id,
  assessment_plan_id: plan.id,
  assessment_plan_version_id: "ap-v1",
  title: "Results Alpha",
  description: null,
  planned_control_ids: ["ac-1", "ac-2"],
  reviewed_control_ids: ["ac-1"],
  observations: [],
  findings: [],
  subject_options: [{ uuid: "component-1", title: "Auth Service", type: "service" }],
  statement_options: [
    { statement_id: "ac-1_smt", control_id: "ac-1", title: "Statement" },
    { statement_id: "ac-2_smt", control_id: "ac-2", title: "Statement 2" },
  ],
  objective_options: [
    { objective_id: "local-1", control_id: "ac-1", title: "Objective" },
    { objective_id: "local-2", control_id: "ac-2", title: "Objective 2" },
  ],
  start: null,
  end: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const validation: AssessmentResultValidation = {
  valid: true,
  diagnostics: [],
  planned_control_ids: result.planned_control_ids,
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

  it("filters statement target options to the current reviewed scope while preserving existing out-of-scope selections", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse(result));
    vi.stubGlobal("fetch", fetchMock);

    const scopedResult: AssessmentResult = {
      ...result,
      reviewed_control_ids: ["ac-1", "ac-2"],
      findings: [
        {
          id: "finding-1",
          title: "Existing finding",
          description: "desc",
          target_type: "statement-id",
          target_id: "ac-1_smt",
          status: "satisfied",
          related_observation_ids: [],
        },
      ],
    };

    render(
      <LocaleProvider locale="en">
        <AssessmentResultWorkspace
          tenantId={TENANT}
          system={system}
          plan={plan}
          initialResult={scopedResult}
          initialValidation={validation}
          initialVersions={versions}
          canWrite
        />
      </LocaleProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Findings" }));
    let targetSelect = screen.getByRole("combobox", { name: "Target" });
    expect(screen.getByRole("option", { name: /ac-1_smt/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /ac-2_smt/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Overview" }));
    const reviewedControls = screen.getByRole("listbox", { name: "Reviewed controls" });
    await user.deselectOptions(reviewedControls, ["ac-1"]);
    await user.selectOptions(reviewedControls, ["ac-2"]);

    await user.click(screen.getByRole("button", { name: "Findings" }));
    expect(screen.getByRole("option", { name: /ac-2_smt/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /ac-1_smt · ac-1 · Statement/ })).not.toBeInTheDocument();
    expect(
      screen.getByRole("option", {
        name: "ac-1_smt · outside current reviewed control scope",
      }),
    ).toBeInTheDocument();

    targetSelect = screen.getByRole("combobox", { name: "Target" });
    expect(targetSelect).toHaveValue("ac-1_smt");
    expect(targetSelect).toBeInTheDocument();
  });

  it("filters objective target options to the current reviewed scope while preserving existing out-of-scope selections", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse(result));
    vi.stubGlobal("fetch", fetchMock);

    const scopedResult: AssessmentResult = {
      ...result,
      reviewed_control_ids: ["ac-1", "ac-2"],
      findings: [
        {
          id: "finding-1",
          title: "Existing finding",
          description: "desc",
          target_type: "objective-id",
          target_id: "local-1",
          status: "satisfied",
          related_observation_ids: [],
        },
      ],
    };

    render(
      <LocaleProvider locale="en">
        <AssessmentResultWorkspace
          tenantId={TENANT}
          system={system}
          plan={plan}
          initialResult={scopedResult}
          initialValidation={validation}
          initialVersions={versions}
          canWrite
        />
      </LocaleProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Findings" }));
    let targetSelect = screen.getByRole("combobox", { name: "Target" });
    expect(screen.getByRole("option", { name: /local-1 · ac-1/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /local-2 · ac-2/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Overview" }));
    const reviewedControls = screen.getByRole("listbox", { name: "Reviewed controls" });
    await user.deselectOptions(reviewedControls, ["ac-1"]);
    await user.selectOptions(reviewedControls, ["ac-2"]);

    await user.click(screen.getByRole("button", { name: "Findings" }));
    expect(screen.getByRole("option", { name: /local-2 · ac-2/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /local-1 · ac-1/ })).not.toBeInTheDocument();
    expect(
      screen.getByRole("option", {
        name: /local-1 · outside current reviewed control scope/,
      }),
    ).toBeInTheDocument();
    targetSelect = screen.getByRole("combobox", { name: "Target" });
    expect(targetSelect).toHaveValue("local-1");
  });

  it("prevents deleting an observation that is still referenced by a finding", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse(result));
    vi.stubGlobal("fetch", fetchMock);

    const referencedResult: AssessmentResult = {
      ...result,
      observations: [
        {
          id: "obs-1",
          title: "Observed",
          description: "desc",
          methods: ["EXAMINE"],
          collected_at: "2026-01-01T00:00:00Z",
          subject_uuids: [],
          evidence: [],
        },
      ],
      findings: [
        {
          id: "finding-1",
          title: "Linked finding",
          description: "desc",
          target_type: "statement-id",
          target_id: "ac-1_smt",
          status: "satisfied",
          related_observation_ids: ["obs-1"],
        },
      ],
    };

    render(
      <LocaleProvider locale="en">
        <AssessmentResultWorkspace
          tenantId={TENANT}
          system={system}
          plan={plan}
          initialResult={referencedResult}
          initialValidation={validation}
          initialVersions={versions}
          canWrite
        />
      </LocaleProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Observations" }));
    await user.click(screen.getAllByRole("button", { name: "Remove" })[0]);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Remove observation references from findings",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("preserves explicit nested ids in save payload when editing existing entries", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse(result));
    vi.stubGlobal("fetch", fetchMock);

    const editableResult: AssessmentResult = {
      ...result,
      observations: [
        {
          id: "11111111-1111-4111-8111-111111111111",
          title: "Observed",
          description: "desc",
          methods: ["EXAMINE"],
          collected_at: "2026-01-01T00:00:00Z",
          subject_uuids: [],
          evidence: [
            {
              id: "22222222-2222-4222-8222-222222222222",
              title: "Evidence",
              description: "desc",
              href: "https://example.test/evidence",
            },
          ],
        },
      ],
      findings: [
        {
          id: "33333333-3333-4333-8333-333333333333",
          title: "Finding",
          description: "desc",
          target_type: "statement-id",
          target_id: "ac-1_smt",
          status: "satisfied",
          related_observation_ids: ["11111111-1111-4111-8111-111111111111"],
        },
      ],
    };

    render(
      <LocaleProvider locale="en">
        <AssessmentResultWorkspace
          tenantId={TENANT}
          system={system}
          plan={plan}
          initialResult={editableResult}
          initialValidation={validation}
          initialVersions={versions}
          canWrite
        />
      </LocaleProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Observations" }));
    await user.clear(screen.getByRole("textbox", { name: "Observation title" }));
    await user.type(screen.getByRole("textbox", { name: "Observation title" }), "Observed updated");

    await user.click(screen.getByRole("button", { name: "Save working state" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const firstCall = (fetchMock.mock.calls as unknown[][])[0];
    const init = (firstCall?.[1] ?? undefined) as RequestInit | undefined;
    const body = JSON.parse(String(init?.body ?? "{}"));

    expect(body.observations[0].id).toBe("11111111-1111-4111-8111-111111111111");
    expect(body.observations[0].evidence[0].id).toBe(
      "22222222-2222-4222-8222-222222222222",
    );
    expect(body.findings[0].id).toBe("33333333-3333-4333-8333-333333333333");
  });

  it("renders structured save diagnostics and keeps unsaved edits", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        {
          detail: {
            diagnostics: [
              {
                severity: "error",
                code: "invalid_evidence_href",
                message: "Evidence href cannot contain malformed percent-encoding.",
                path: "$.observations[0].evidence[0].href",
              },
            ],
          },
        },
        422,
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();

    const titleInput = screen.getByRole("textbox", { name: "Assessment Results title" });
    await user.clear(titleInput);
    await user.type(titleInput, "Results Draft");

    await user.click(screen.getByRole("button", { name: "Save working state" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Save rejected. Fix the listed diagnostics and try again.",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Evidence href cannot contain malformed percent-encoding.",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Validation path: $.observations[0].evidence[0].href",
    );
    expect(titleInput).toHaveValue("Results Draft");
  });

  it("renders structured publication diagnostics", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        {
          detail: {
            diagnostics: [
              {
                severity: "error",
                code: "ambiguous_statement_target",
                message: "Finding target statement-id 'shared-statement' is ambiguous.",
                path: "$.findings[0].target_id",
              },
            ],
          },
        },
        422,
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();

    await user.click(screen.getByRole("button", { name: "Validation & Versions" }));
    await user.click(screen.getByRole("button", { name: "Create immutable version" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Version creation rejected. Fix the listed diagnostics and try again.",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "This statement target is ambiguous in the pinned Assessment Plan context. Choose an unambiguous statement identifier.",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Validation path: $.findings[0].target_id",
    );
  });
});



