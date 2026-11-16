import { ApiProblem } from "@/components/ApiProblem";
import { AssessmentPlanWorkspace } from "@/components/AssessmentPlanWorkspace";
import {
  getAssessmentPlan,
  getSystem,
  listAssessmentPlanVersions,
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
    const tenant = tenants.items.find((item) => item.id === tenantId);
    return {
      ok: true as const,
      system,
      plan,
      validation,
      versions,
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}

