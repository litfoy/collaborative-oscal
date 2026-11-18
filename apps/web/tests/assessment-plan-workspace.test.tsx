import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssessmentPlanWorkspace } from "@/components/AssessmentPlanWorkspace";
import { LocaleProvider } from "@/lib/i18n/provider";
import type {
  AssessmentPlan,
  AssessmentPlanValidation,
  AssessmentPlanVersion,
  InformationSystem,
  RevisionSummary,
  SystemSecurityPlan,
} from "@/lib/types";

import { CATALOG, REVISION, TENANT, jsonResponse, revision } from "./fixtures";

vi.mock("@/components/MappingControlPicker", () => ({
  MappingControlPicker: ({ selected, onChange }: { selected: string[]; onChange: (ids: string[]) => void }) => (
    <div>
      <button type="button" onClick={() => onChange([...selected, "ac-1"])}>add ac-1</button>
      <button type="button" onClick={() => onChange(selected.filter((id) => id !== "ac-1"))}>remove ac-1</button>
    </div>
  ),
}));

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

const ssp: SystemSecurityPlan = {
  id: "ssp",
  tenant_id: TENANT,
  system_id: system.id,
  catalog_id: CATALOG,
  revision_id: REVISION,
  catalog_name: "Sample Catalog",
  title: "Identity SSP",
  control_implementation_description: null,
  included_implementations: [],
  baseline_control_count: 5,
  documented_control_count: 0,
  created_at: "",
  updated_at: "",
};

const basePlan: AssessmentPlan = {
  id: "plan",
  tenant_id: TENANT,
  system_id: system.id,
  system_security_plan_id: ssp.id,
  system_security_plan_version_id: "ssp-version",
  title: "Assessment Alpha",
  description: null,
  control_ids: [],
  source_objectives: [],
  local_objectives: [],
  subject_uuids: [],
  activities: [],
  tasks: [],
  roles: [],
  parties: [],
  terms: null,
  baseline_catalog_id: CATALOG,
  baseline_revision_id: REVISION,
  ssp_oscal_version: "1.2.1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  concurrency_version: 1,
};

const validation: AssessmentPlanValidation = {
  valid: true,
  diagnostics: [],
  source_objectives: [
    {
      objective_id: "ac-1_obj",
      control_id: "ac-1",
      title: "Review account policy",
      description: "Check policy statement.",
    },
  ],
  oscal_candidate: {
    "assessment-plan": {
      metadata: { title: "Assessment Alpha", version: "draft", "oscal-version": "1.2.1" },
    },
  },
};

const versions: AssessmentPlanVersion[] = [];

const baseVersion: AssessmentPlanVersion = {
  id: "ap-version-1",
  assessment_plan_id: "plan",
  system_security_plan_version_id: "ssp-version",
  oscal_document_uuid: "11111111-1111-4111-8111-111111111111",
  oscal_version: "1.2.1",
  document_version: "1.0",
  last_modified: "2026-01-01T00:00:00Z",
  content_sha256: "hash",
  diagnostics: [],
  created_at: "2026-01-01T00:00:00Z",
  created: true,
};

function renderWorkspace({
  plan = basePlan,
  locale = "en",
  initialValidation = validation,
  initialVersions = versions,
}: {
  plan?: AssessmentPlan;
  locale?: "en" | "de";
  initialValidation?: AssessmentPlanValidation;
  initialVersions?: AssessmentPlanVersion[];
} = {}) {
  return render(
    <LocaleProvider locale={locale}>
      <AssessmentPlanWorkspace
        tenantId={TENANT}
        system={system}
        initialPlan={plan}
        initialValidation={initialValidation}
        initialVersions={initialVersions}
        ssp={ssp}
        sspVersion={null}
        revision={revision() as RevisionSummary}
        subjectOptions={[
          {
            uuid: "component-1",
            title: "Auth Service",
            type: "service",
            description: "Handles authentication",
            status: "operational",
            remarks: null,
          },
        ]}
        canWrite
      />
    </LocaleProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("AssessmentPlanWorkspace", () => {
  it("uses structured fields and saves a structured working payload", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse({ ...basePlan, control_ids: ["ac-1"], subject_uuids: ["component-1"] }));
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();
    await user.click(screen.getByRole("button", { name: "Scope" }));
    await user.click(screen.getByRole("button", { name: "add ac-1" }));
    await user.click(screen.getByRole("checkbox", { name: /Auth Service/i }));
    await user.click(screen.getAllByRole("button", { name: "Save working state" }).at(-1)!);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const firstCall = (fetchMock.mock.calls as unknown[][])[0];
    expect(firstCall).toBeDefined();
    const init = (firstCall?.[1] ?? undefined) as RequestInit | undefined;
    const body = JSON.parse(String(init?.body ?? "{}"));
    expect(body.control_ids).toEqual(["ac-1"]);
    expect(body.subject_uuids).toEqual(["component-1"]);
    expect(screen.queryByText("Subject UUIDs (one UUID per line)")).not.toBeInTheDocument();
  });

  it("creates local objectives and links activities without manual UUID entry", async () => {
    const user = userEvent.setup();
    renderWorkspace({ plan: { ...basePlan, control_ids: ["ac-1"] } });

    await user.click(screen.getByRole("button", { name: "Scope" }));
    await user.click(screen.getByRole("button", { name: "Add local objective" }));
    await user.type(screen.getByRole("textbox", { name: "Description" }), "Assess control objective");
    const localObjectiveEditor = screen.getByRole("textbox", { name: "Description" }).closest(".panel");
    expect(localObjectiveEditor).toBeTruthy();
    await user.click(within(localObjectiveEditor as HTMLElement).getByRole("button", { name: "Save working state" }));

    await user.click(screen.getByRole("button", { name: "Activities" }));
    await user.click(screen.getByRole("button", { name: "Add activity" }));
    await user.type(screen.getByRole("textbox", { name: "Activity title" }), "Interview owners");
    await user.type(screen.getByRole("textbox", { name: "Activity description" }), "Interview security owners");
    await user.click(screen.getByRole("checkbox", { name: "Interview" }));
    const activityEditor = screen.getByRole("textbox", { name: "Activity title" }).closest(".panel");
    expect(activityEditor).toBeTruthy();
    await user.click(within(activityEditor as HTMLElement).getByRole("button", { name: "Save working state" }));

    expect(screen.getByText("Interview owners")).toBeVisible();
    expect(screen.queryByText("Subject UUIDs (one UUID per line)")).not.toBeInTheDocument();
  });

  it("localizes key labels in German while preserving stored method values", async () => {
    const user = userEvent.setup();
    renderWorkspace({
      plan: {
        ...basePlan,
        activities: [
          {
            id: "activity-1",
            title: "Dokumentpruefung",
            description: "Beschreibung",
            methods: ["EXAMINE"],
            steps: [],
            control_ids: [],
            objective_ids: [],
            planned_evidence: null,
          },
        ],
      },
      locale: "de",
    });

    expect(screen.getByRole("button", { name: "Pruefumfang" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Pruefaktivitaeten" }));
    expect(screen.getByText("Sichten")).toBeVisible();
  });

  it("preserves stable activity, step, task, and party identifiers on save", async () => {
    const user = userEvent.setup();
    const planWithIds: AssessmentPlan = {
      ...basePlan,
      title: "Assessment with IDs",
      control_ids: ["ac-1"],
      subject_uuids: ["component-1"],
      local_objectives: [
        {
          objective_id: "local-ac-1-1",
          control_id: "ac-1",
          description: "Local objective",
          methods: ["EXAMINE"],
        },
      ],
      activities: [
        {
          id: "activity-fixed-id",
          title: "Activity",
          description: "Activity description",
          methods: ["TEST"],
          steps: [
            {
              id: "step-fixed-id",
              title: "Step",
              description: "Step description",
            },
          ],
          control_ids: ["ac-1"],
          objective_ids: ["local-ac-1-1"],
          planned_evidence: null,
        },
      ],
      parties: [{ uuid: "party-fixed-id", party_type: "person", name: "Assessor" }],
      roles: [
        {
          role_id: "lead-assessor",
          title: "Lead assessor",
          description: null,
          party_uuids: ["party-fixed-id"],
        },
      ],
      tasks: [
        {
          id: "task-fixed-id",
          title: "Task",
          description: null,
          activity_ids: ["activity-fixed-id"],
          subject_uuids: ["component-1"],
          role_ids: ["lead-assessor"],
          on_date: null,
          start: null,
          end: null,
        },
      ],
    };
    const fetchMock = vi.fn(async () => jsonResponse(planWithIds));
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace({ plan: planWithIds });
    await user.clear(screen.getByRole("textbox", { name: "Assessment Plan title" }));
    await user.type(screen.getByRole("textbox", { name: "Assessment Plan title" }), "Assessment with IDs updated");
    await user.click(screen.getAllByRole("button", { name: "Save working state" }).at(-1)!);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const firstCall = (fetchMock.mock.calls as unknown[][])[0];
    const init = (firstCall?.[1] ?? undefined) as RequestInit | undefined;
    const body = JSON.parse(String(init?.body ?? "{}"));
    expect(body.activities[0].id).toBe("activity-fixed-id");
    expect(body.activities[0].steps[0].id).toBe("step-fixed-id");
    expect(body.tasks[0].id).toBe("task-fixed-id");
    expect(body.parties[0].uuid).toBe("party-fixed-id");
  });

  it("marks validation results as stale after edits and blocks version creation", async () => {
    const user = userEvent.setup();
    renderWorkspace({
      initialValidation: { ...validation, valid: true, diagnostics: [] },
      initialVersions: [baseVersion],
    });

    await user.click(screen.getByRole("button", { name: "Overview" }));
    await user.type(screen.getByRole("textbox", { name: "Assessment Plan title" }), " updated");
    await user.click(screen.getByRole("button", { name: "Validation & Versions" }));

    expect(screen.getByText("Validation results are outdated because the working state changed.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Create immutable version" })).toBeDisabled();
  });

  it("creates a new immutable version and keeps export links bound to version ids", async () => {
    const user = userEvent.setup();
    const createdVersion: AssessmentPlanVersion = {
      ...baseVersion,
      id: "ap-version-2",
      document_version: "2.0",
      created: true,
      created_at: "2026-01-02T00:00:00Z",
    };
    const fetchMock = vi.fn(async () => jsonResponse(createdVersion));
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace({ initialVersions: [baseVersion] });
    await user.click(screen.getByRole("button", { name: "Validation & Versions" }));
    await user.click(screen.getByRole("button", { name: "Create immutable version" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const urls = (fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]));
    expect(urls.some((url) => url.endsWith(`/bff/tenants/${TENANT}/assessment-plans/plan/versions`))).toBe(true);

    const exportLinks = screen.getAllByRole("link", { name: "Export stored OSCAL JSON" });
    const hrefs = exportLinks.map((link) => link.getAttribute("href"));
    expect(hrefs).toContain(`/bff/tenants/${TENANT}/assessment-plans/plan/versions/ap-version-2/export`);
    expect(hrefs).toContain(`/bff/tenants/${TENANT}/assessment-plans/plan/versions/ap-version-1/export`);
  });

  it("synchronizes the publication token so a subsequent save does not conflict", async () => {
    const user = userEvent.setup();
    const publishedVersion: AssessmentPlanVersion = {
      ...baseVersion,
      id: "ap-version-2",
      document_version: "2.0",
      created: true,
      created_at: "2026-01-02T00:00:00Z",
      concurrency_version: 2,
    };
    const savedPlan: AssessmentPlan = {
      ...basePlan,
      title: "Assessment Alpha updated",
      concurrency_version: 3,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(publishedVersion))
      .mockResolvedValueOnce(jsonResponse(savedPlan));
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace({ initialVersions: [baseVersion] });
    await user.click(screen.getByRole("button", { name: "Validation & Versions" }));
    await user.click(screen.getByRole("button", { name: "Create immutable version" }));
    await user.click(screen.getByRole("button", { name: "Overview" }));
    await user.clear(screen.getByRole("textbox", { name: "Assessment Plan title" }));
    await user.type(screen.getByRole("textbox", { name: "Assessment Plan title" }), "Assessment Alpha updated");
    await user.click(screen.getAllByRole("button", { name: "Save working state" }).at(-1)!);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const secondCall = (fetchMock.mock.calls as unknown[][])[1];
    const secondInit = (secondCall?.[1] ?? undefined) as RequestInit | undefined;
    const secondBody = JSON.parse(String(secondInit?.body ?? "{}"));
    expect(secondBody.expected_version).toBe(2);
  });

  it("shows stale publication conflicts without generic error fallback", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonResponse(
        {
          detail: {
            code: "stale_update",
            plan_id: basePlan.id,
            expected_version: 1,
            current_version: 4,
          },
        },
        409,
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace({ initialVersions: [baseVersion] });
    await user.click(screen.getByRole("button", { name: "Validation & Versions" }));
    await user.click(screen.getByRole("button", { name: "Create immutable version" }));

    expect(await screen.findByText(/Current server version: 4\./)).toBeVisible();
    expect(screen.queryByText("The request was not valid.")).not.toBeInTheDocument();
  });

  it("shows generated OSCAL draft candidate and path-aware diagnostics", async () => {
    const user = userEvent.setup();
    renderWorkspace({
      initialValidation: {
        ...validation,
        valid: false,
        diagnostics: [
          {
            severity: "error",
            code: "oscal_model",
            category: "oscal_model",
            path: "assessment-plan.metadata.version",
            message:
              "OSCAL Assessment Plan model validation failed at assessment-plan.metadata.version: Value does not match required pattern.",
          },
        ],
      },
    });

    await user.click(screen.getByRole("button", { name: "Validation & Versions" }));

    expect(screen.getByText(/Validation path:/i)).toBeVisible();
    expect(screen.getByText("assessment-plan.metadata.version")).toBeVisible();
    await user.click(screen.getByText("OSCAL details (read-only)"));
    expect(screen.getByText(/Generated OSCAL draft candidate/i)).toBeVisible();
    expect(screen.getByText(/"version": "draft"/)).toBeVisible();
  });

  it("propagates role-party assignments into saved task payloads", async () => {
    const user = userEvent.setup();
    const updatedPlan: AssessmentPlan = {
      ...basePlan,
      parties: [{ uuid: "party-1", party_type: "person", name: "Alice Assessor" }],
      roles: [{ role_id: "lead-assessor", title: "Lead Assessor", description: null, party_uuids: ["party-1"] }],
      tasks: [{ id: "task-1", title: "Review interview schedule", description: null, activity_ids: [], subject_uuids: [], role_ids: ["lead-assessor"], on_date: null, start: null, end: null }],
    };
    const fetchMock = vi.fn(async () => jsonResponse(updatedPlan));
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();
    await user.click(screen.getByRole("button", { name: "Tasks" }));

    await user.click(screen.getByRole("button", { name: "Add party" }));
    await user.type(screen.getByRole("textbox", { name: "Party name" }), "Alice Assessor");
    const partyEditor = screen.getByRole("textbox", { name: "Party name" }).closest(".panel");
    expect(partyEditor).toBeTruthy();
    await user.click(within(partyEditor as HTMLElement).getByRole("button", { name: "Save working state" }));

    await user.click(screen.getByRole("button", { name: "Add role" }));
    await user.clear(screen.getByRole("textbox", { name: "Role identifier" }));
    await user.type(screen.getByRole("textbox", { name: "Role identifier" }), "lead-assessor");
    await user.type(screen.getByRole("textbox", { name: "Role title" }), "Lead Assessor");
    await user.click(screen.getByRole("checkbox", { name: "Alice Assessor" }));
    const roleEditor = screen.getByRole("textbox", { name: "Role title" }).closest(".panel");
    expect(roleEditor).toBeTruthy();
    await user.click(within(roleEditor as HTMLElement).getByRole("button", { name: "Save working state" }));

    await user.click(screen.getByRole("button", { name: "Add task" }));
    await user.type(screen.getByRole("textbox", { name: "Task title" }), "Review interview schedule");
    await user.click(screen.getByRole("checkbox", { name: "Lead Assessor" }));
    const taskEditor = screen.getByRole("textbox", { name: "Task title" }).closest(".panel");
    expect(taskEditor).toBeTruthy();
    await user.click(within(taskEditor as HTMLElement).getByRole("button", { name: "Save working state" }));

    await user.click(screen.getAllByRole("button", { name: "Save working state" }).at(-1)!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const firstCall = (fetchMock.mock.calls as unknown[][])[0];
    const init = (firstCall?.[1] ?? undefined) as RequestInit | undefined;
    const body = JSON.parse(String(init?.body ?? "{}"));
    expect(body.parties).toHaveLength(1);
    expect(body.roles).toHaveLength(1);
    expect(body.tasks).toHaveLength(1);
    expect(body.roles[0].party_uuids).toEqual([body.parties[0].uuid]);
    expect(body.tasks[0].role_ids).toEqual([body.roles[0].role_id]);
  });

  it("requires explicit confirmation before removing an activity referenced by tasks", async () => {
    const user = userEvent.setup();
    const planWithDependencies: AssessmentPlan = {
      ...basePlan,
      activities: [{ id: "activity-1", title: "Inspect policy", description: "Inspect policy docs", methods: ["EXAMINE"], steps: [], control_ids: [], objective_ids: [], planned_evidence: null }],
      tasks: [{ id: "task-1", title: "Policy review", description: null, activity_ids: ["activity-1"], subject_uuids: [], role_ids: [], on_date: null, start: null, end: null }],
    };
    const planAfterRemoval: AssessmentPlan = {
      ...planWithDependencies,
      activities: [],
      tasks: [{ ...planWithDependencies.tasks[0], activity_ids: [] }],
    };
    const fetchMock = vi.fn(async () => jsonResponse(planAfterRemoval));
    vi.stubGlobal("fetch", fetchMock);
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);

    renderWorkspace({ plan: planWithDependencies });
    await user.click(screen.getByRole("button", { name: "Activities" }));

    const firstActivityRow = screen.getByText("Inspect policy").closest("li");
    expect(firstActivityRow).toBeTruthy();
    await user.click(within(firstActivityRow as HTMLElement).getByRole("button", { name: "Remove" }));

    expect(confirmMock).toHaveBeenCalled();
    expect(screen.getByText("Inspect policy")).toBeVisible();

    const secondActivityRow = screen.getByText("Inspect policy").closest("li");
    expect(secondActivityRow).toBeTruthy();
    await user.click(within(secondActivityRow as HTMLElement).getByRole("button", { name: "Remove" }));

    expect(screen.queryByText("Inspect policy")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tasks" }));
    expect(screen.getByText(/0 Activities/i)).toBeVisible();

    await user.click(screen.getAllByRole("button", { name: "Save working state" }).at(-1)!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const firstCall = (fetchMock.mock.calls as unknown[][])[0];
    const init = (firstCall?.[1] ?? undefined) as RequestInit | undefined;
    const body = JSON.parse(String(init?.body ?? "{}"));
    expect(body.activities).toEqual([]);
    expect(body.tasks[0].activity_ids).toEqual([]);
  });

  it("preserves unsaved edits when conflict reload fails", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            detail: {
              code: "stale_update",
              plan_id: basePlan.id,
              expected_version: 1,
              current_version: 2,
            },
          },
          409,
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ error: "unavailable" }, 503))
      .mockResolvedValueOnce(jsonResponse({ error: "unavailable" }, 503))
      .mockResolvedValueOnce(jsonResponse({ error: "unavailable" }, 503));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderWorkspace({ plan: { ...basePlan, control_ids: ["ac-1"] } });
    const title = screen.getByRole("textbox", { name: "Assessment Plan title" });
    await user.clear(title);
    await user.type(title, "Assessment Alpha edited");
    await user.click(screen.getByRole("button", { name: "Scope" }));
    await user.click(screen.getByRole("button", { name: "Add local objective" }));
    await user.type(screen.getByRole("textbox", { name: "Identifier" }), "local-draft");
    await user.click(screen.getAllByRole("button", { name: "Save working state" }).at(-1)!);

    expect(await screen.findByText(/Current server version: 2\./)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Discard edits and reload" }));

    expect(await screen.findByText("The service is temporarily unavailable. Please try again.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Assessment Alpha edited" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Identifier" })).toHaveValue(
      "local-ac-1-1local-draft",
    );
  });

  it("keeps unsaved edits unchanged when conflict reload is cancelled", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonResponse(
        {
          detail: {
            code: "stale_update",
            plan_id: basePlan.id,
            expected_version: 1,
            current_version: 2,
          },
        },
        409,
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    renderWorkspace({ plan: { ...basePlan, control_ids: ["ac-1"] } });
    await user.clear(screen.getByRole("textbox", { name: "Assessment Plan title" }));
    await user.type(screen.getByRole("textbox", { name: "Assessment Plan title" }), "Assessment Alpha edited");
    await user.click(screen.getByRole("button", { name: "Scope" }));
    await user.click(screen.getByRole("button", { name: "Add local objective" }));
    await user.type(screen.getByRole("textbox", { name: "Identifier" }), "local-draft");
    await user.click(screen.getAllByRole("button", { name: "Save working state" }).at(-1)!);

    expect(await screen.findByText(/Current server version: 2\./)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Discard edits and reload" }));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("heading", { name: "Assessment Alpha edited" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Identifier" })).toHaveValue(
      "local-ac-1-1local-draft",
    );
  });

  it("replaces stale nested draft editors with refreshed server state after conflict reload", async () => {
    const user = userEvent.setup();
    const refreshedPlan: AssessmentPlan = {
      ...basePlan,
      title: "Server copy",
      concurrency_version: 5,
      control_ids: ["ac-1"],
    };
    const refreshedValidation: AssessmentPlanValidation = {
      ...validation,
      valid: true,
      diagnostics: [],
    };
    const refreshedVersions: AssessmentPlanVersion[] = [
      {
        ...baseVersion,
        id: "ap-version-server",
        document_version: "2.0",
      },
    ];
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            detail: {
              code: "stale_update",
              plan_id: basePlan.id,
              expected_version: 1,
              current_version: 5,
            },
          },
          409,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(refreshedPlan))
      .mockResolvedValueOnce(jsonResponse(refreshedVersions))
      .mockResolvedValueOnce(jsonResponse(refreshedValidation));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderWorkspace({ plan: { ...basePlan, control_ids: ["ac-1"] }, initialVersions: [baseVersion] });
    await user.clear(screen.getByRole("textbox", { name: "Assessment Plan title" }));
    await user.type(screen.getByRole("textbox", { name: "Assessment Plan title" }), "Unsaved title");

    await user.click(screen.getByRole("button", { name: "Scope" }));
    await user.click(screen.getByRole("button", { name: "Add local objective" }));
    await user.type(screen.getByRole("textbox", { name: "Identifier" }), "local-draft");

    await user.click(screen.getByRole("button", { name: "Activities" }));
    await user.click(screen.getByRole("button", { name: "Add activity" }));
    await user.type(screen.getByRole("textbox", { name: "Activity title" }), "Activity draft");

    await user.click(screen.getByRole("button", { name: "Tasks" }));
    await user.click(screen.getByRole("button", { name: "Add task" }));
    await user.type(screen.getByRole("textbox", { name: "Task title" }), "Task draft");
    await user.click(screen.getByRole("button", { name: "Add role" }));
    await user.type(screen.getByRole("textbox", { name: "Role identifier" }), "role-draft");
    await user.click(screen.getByRole("button", { name: "Add party" }));
    await user.type(screen.getByRole("textbox", { name: "Party name" }), "Party draft");

    await user.click(screen.getAllByRole("button", { name: "Save working state" }).at(-1)!);
    expect(await screen.findByText(/Current server version: 5\./)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Discard edits and reload" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(screen.getByRole("heading", { name: "Server copy" })).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Identifier" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Activity title" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Task title" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Role identifier" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Party name" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Validation & Versions" }));
    expect(screen.getByText(/Version 2\.0/)).toBeVisible();
  });
});












