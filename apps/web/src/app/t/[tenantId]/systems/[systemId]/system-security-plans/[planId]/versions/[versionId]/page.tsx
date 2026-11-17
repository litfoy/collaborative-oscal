import { ApiProblem } from "@/components/ApiProblem";
import { SystemSecurityPlanVersionView } from "@/components/SystemSecurityPlanVersionView";
import {
  exportSystemSecurityPlanVersion,
  getSystem,
  getSystemSecurityPlan,
  getSystemSecurityPlanVersion,
} from "@/lib/api";

export default async function SystemSecurityPlanVersionPage({
  params,
}: {
  params: Promise<{ tenantId: string; systemId: string; planId: string; versionId: string }>;
}) {
  const { tenantId, systemId, planId, versionId } = await params;
  const here = `/t/${tenantId}/systems/${systemId}/system-security-plans/${planId}/versions/${versionId}`;
  const result = await loadVersionView(tenantId, systemId, planId, versionId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return (
    <SystemSecurityPlanVersionView
      tenantId={tenantId}
      systemId={systemId}
      systemName={result.system.name}
      planId={planId}
      planTitle={result.plan.title}
      version={result.version}
      snapshot={result.snapshot}
    />
  );
}

async function loadVersionView(
  tenantId: string,
  systemId: string,
  planId: string,
  versionId: string,
  here: string,
) {
  try {
    const [system, plan, version, snapshot] = await Promise.all([
      getSystem(tenantId, systemId, here),
      getSystemSecurityPlan(tenantId, planId, here),
      getSystemSecurityPlanVersion(tenantId, planId, versionId, here),
      exportSystemSecurityPlanVersion(tenantId, planId, versionId, here),
    ]);
    if (plan.system_id !== system.id) {
      throw new Error("SSP does not belong to this System.");
    }
    return { ok: true as const, system, plan, version, snapshot };
  } catch (error) {
    return { ok: false as const, error };
  }
}

