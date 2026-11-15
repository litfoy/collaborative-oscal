import { ApiProblem } from "@/components/ApiProblem";
import { SystemWorkspace } from "@/components/SystemWorkspace";
import {
  getSystem,
  listCatalogs,
  listComponentDefinitions,
  listSystemComponents,
  listSystemSecurityPlans,
  listTenants,
  listRevisions,
} from "@/lib/api";

export default async function SystemDetailPage({
  params,
}: {
  params: Promise<{ tenantId: string; systemId: string }>;
}) {
  const { tenantId, systemId } = await params;
  const here = `/t/${tenantId}/systems/${systemId}`;
  const result = await loadSystem(tenantId, systemId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return (
    <SystemWorkspace
      tenantId={tenantId}
      initialSystem={result.system}
      initialComponents={result.components}
      initialPlans={result.plans}
      catalogs={result.catalogs}
      revisions={result.revisions}
      definitions={result.definitions}
      canWrite={result.canWrite}
    />
  );
}

async function loadSystem(tenantId: string, systemId: string, here: string) {
  try {
    const [system, components, plans, catalogPage, definitions, tenants] = await Promise.all([
      getSystem(tenantId, systemId, here),
      listSystemComponents(tenantId, systemId, here),
      listSystemSecurityPlans(tenantId, systemId, here),
      listCatalogs(tenantId, { limit: 200, offset: 0 }, here),
      listComponentDefinitions(tenantId, here),
      listTenants(here),
    ]);
    const catalogRevisions = await Promise.all(
      catalogPage.items.map(async (catalog) => ({
        catalog,
        revisions: await listRevisions(tenantId, catalog.id, here),
      })),
    );
    const revisions = catalogRevisions.flatMap(({ catalog, revisions: page }) =>
      page.items.map((revision) => ({ catalog, revision })),
    );
    const tenant = tenants.items.find((item) => item.id === tenantId);
    return {
      ok: true as const,
      system,
      components,
      plans,
      catalogs: catalogPage.items,
      revisions,
      definitions: definitions.items,
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}
