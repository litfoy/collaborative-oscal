import { ApiProblem } from "@/components/ApiProblem";
import { AssessmentResultWorkspace } from "@/components/AssessmentResultWorkspace";
import {
  getAssessmentPlan,
  getAssessmentResult,
  getSystem,
  listAssessmentResultVersions,
  listTenants,
  validateAssessmentResult,
} from "@/lib/api";

export default async function AssessmentResultPage({
  params,
}: {
  params: Promise<{ tenantId: string; systemId: string; resultId: string }>;
}) {
  const { tenantId, systemId, resultId } = await params;
  const here = `/t/${tenantId}/systems/${systemId}/assessment-results/${resultId}`;
  const result = await loadAssessmentResult(tenantId, systemId, resultId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return (
    <AssessmentResultWorkspace
      tenantId={tenantId}
      system={result.system}
      plan={result.plan}
      initialResult={result.assessmentResult}
      initialValidation={result.validation}
      initialVersions={result.versions}
      canWrite={result.canWrite}
    />
  );
}

async function loadAssessmentResult(
  tenantId: string,
  systemId: string,
  resultId: string,
  here: string,
) {
  try {
    const [system, assessmentResult, validation, versions, tenants] = await Promise.all([
      getSystem(tenantId, systemId, here),
      getAssessmentResult(tenantId, resultId, here),
      validateAssessmentResult(tenantId, resultId, here),
      listAssessmentResultVersions(tenantId, resultId, here),
      listTenants(here),
    ]);

    if (assessmentResult.system_id !== system.id) {
      throw new Error("Assessment Results do not belong to this System.");
    }

    const plan = await getAssessmentPlan(tenantId, assessmentResult.assessment_plan_id, here);
    const tenant = tenants.items.find((item) => item.id === tenantId);
    return {
      ok: true as const,
      system,
      assessmentResult,
      plan,
      validation,
      versions,
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}

