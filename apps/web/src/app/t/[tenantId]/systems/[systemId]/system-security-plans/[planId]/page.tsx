import { ApiProblem } from "@/components/ApiProblem";
import { SystemSecurityPlanWorkspace } from "@/components/SystemSecurityPlanWorkspace";
import {
  getSystem,
  getSystemSecurityPlan,
  getOutline,
  getRevision,
  listImplementations,
  listSystemComponents,
  listSystemSecurityPlanVersions,
  listTenants,
} from "@/lib/api";

export default async function SystemSecurityPlanPage({
  params,
}: {
  params: Promise<{ tenantId: string; systemId: string; planId: string }>;
}) {
  const { tenantId, systemId, planId } = await params;
  const here = `/t/${tenantId}/systems/${systemId}/system-security-plans/${planId}`;
  const result = await loadPlan(tenantId, systemId, planId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return (
    <SystemSecurityPlanWorkspace
      tenantId={tenantId}
      system={result.system}
      initialPlan={result.plan}
      components={result.components}
      initialImplementations={result.implementations}
      initialVersions={result.versions}
      revision={result.revision}
      initialRoot={result.root}
      canWrite={result.canWrite}
    />
  );
}

async function loadPlan(tenantId: string, systemId: string, planId: string, here: string) {
  try {
    const [system, plan, components, implementationPage, versions, tenants] = await Promise.all([
      getSystem(tenantId, systemId, here),
      getSystemSecurityPlan(tenantId, planId, here),
      listSystemComponents(tenantId, systemId, here),
      listImplementations(tenantId, here),
      listSystemSecurityPlanVersions(tenantId, planId, here),
      listTenants(here),
    ]);
    if (plan.system_id !== system.id) {
      throw new Error("SSP does not belong to this System.");
    }
    const [revision, root] = await Promise.all([
      getRevision(tenantId, plan.catalog_id, plan.revision_id, here),
      getOutline(tenantId, plan.catalog_id, plan.revision_id, here),
    ]);
    const implementations = [...implementationPage.items];
    while (implementations.length < implementationPage.total) {
      const next = await listImplementations(tenantId, here, implementations.length);
      if (!next.items.length) throw new Error("Could not load all implementation records.");
      implementations.push(...next.items);
    }
    const tenant = tenants.items.find((item) => item.id === tenantId);
    return {
      ok: true as const,
      system,
      plan,
      components,
      implementations,
      versions,
      revision,
      root,
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}
