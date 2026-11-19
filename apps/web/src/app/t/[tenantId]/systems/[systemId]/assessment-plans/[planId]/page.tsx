// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiProblem } from "@/components/ApiProblem";
import { AssessmentPlanWorkspace } from "@/components/AssessmentPlanWorkspace";
import {
  exportSystemSecurityPlanVersion,
  getAssessmentPlan,
  getRevision,
  getSystem,
  getSystemSecurityPlan,
  listAssessmentPlanVersions,
  listSystemSecurityPlanVersions,
  listTenants,
  validateAssessmentPlan,
} from "@/lib/api";

export default async function AssessmentPlanPage({
  params,
}: {
  params: Promise<{ tenantId: string; systemId: string; planId: string }>;
}) {
  const { tenantId, systemId, planId } = await params;
  const here = `/t/${tenantId}/systems/${systemId}/assessment-plans/${planId}`;
  const result = await loadAssessmentPlan(tenantId, systemId, planId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return (
    <AssessmentPlanWorkspace
      tenantId={tenantId}
      system={result.system}
      initialPlan={result.plan}
      initialValidation={result.validation}
      initialVersions={result.versions}
      ssp={result.ssp}
      sspVersion={result.sspVersion}
      revision={result.revision}
      subjectOptions={result.subjectOptions}
      canWrite={result.canWrite}
    />
  );
}

async function loadAssessmentPlan(
  tenantId: string,
  systemId: string,
  planId: string,
  here: string,
) {
  try {
    const [system, plan, validation, versions, tenants] = await Promise.all([
      getSystem(tenantId, systemId, here),
      getAssessmentPlan(tenantId, planId, here),
      validateAssessmentPlan(tenantId, planId, here),
      listAssessmentPlanVersions(tenantId, planId, here),
      listTenants(here),
    ]);
    if (plan.system_id !== system.id) {
      throw new Error("Assessment Plan does not belong to this System.");
    }
    const [ssp, sspVersions] = await Promise.all([
      getSystemSecurityPlan(tenantId, plan.system_security_plan_id, here),
      listSystemSecurityPlanVersions(tenantId, plan.system_security_plan_id, here),
    ]);
    const sspVersion =
      sspVersions.find((item) => item.id === plan.system_security_plan_version_id) ?? null;
    const revision = await getRevision(tenantId, ssp.catalog_id, ssp.revision_id, here);
    const snapshot = await exportSystemSecurityPlanVersion(
      tenantId,
      plan.system_security_plan_id,
      plan.system_security_plan_version_id,
      here,
    );
    const tenant = tenants.items.find((item) => item.id === tenantId);
    return {
      ok: true as const,
      system,
      plan,
      validation,
      versions,
      ssp,
      sspVersion,
      revision,
      subjectOptions: readSubjectOptions(snapshot),
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}

function readSubjectOptions(snapshot: Record<string, unknown>) {
  const body = valueObject(snapshot["system-security-plan"]);
  const implementation = valueObject(body?.["system-implementation"]);
  const components = Array.isArray(implementation?.components)
    ? implementation.components
    : [];
  return components
    .map((item) => {
      const component = valueObject(item);
      const status = valueObject(component?.status);
      const uuid = valueString(component?.uuid);
      if (!uuid) return null;
      return {
        uuid,
        title: valueString(component?.title) ?? uuid,
        type: valueString(component?.type) ?? "component",
        description: valueString(component?.description) ?? "",
        status: valueString(status?.state),
        remarks: valueString(status?.remarks),
      };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null);
}

function valueObject(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function valueString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}


