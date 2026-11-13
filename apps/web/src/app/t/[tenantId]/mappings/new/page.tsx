import { ApiProblem } from "@/components/ApiProblem";
import { MappingWorkspace } from "@/components/MappingWorkspace";
import { listCatalogs, listTenants } from "@/lib/api";

export default async function NewMappingCollectionPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const here = `/t/${tenantId}/mappings/new`;
  const result = await loadNewMappingPage(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return <>
    <h1>New Control Mapping collection</h1>
    <MappingWorkspace tenantId={tenantId} catalogs={result.catalogs} catalogTotal={result.catalogTotal}
      canWrite={result.canWrite} initialCollection={null} />
  </>;
}

async function loadNewMappingPage(tenantId: string, returnTo: string) {
  try {
    const [catalogs, tenants] = await Promise.all([
      listCatalogs(tenantId, { limit: 200, offset: 0 }, returnTo),
      listTenants(returnTo),
    ]);
    return {
      ok: true as const,
      catalogs: catalogs.items,
      catalogTotal: catalogs.total,
      canWrite: tenants.items.some((tenant) =>
        tenant.id === tenantId && tenant.permissions.includes("catalog:write"),
      ),
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}
