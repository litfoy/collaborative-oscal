import { ApiProblem } from "@/components/ApiProblem";
import { MappingWorkspace } from "@/components/MappingWorkspace";
import { getMappingCollection, listCatalogs, listTenants } from "@/lib/api";

export default async function MappingCollectionPage({
  params,
}: {
  params: Promise<{ tenantId: string; collectionId: string }>;
}) {
  const { tenantId, collectionId } = await params;
  const here = `/t/${tenantId}/mappings/${collectionId}`;
  const result = await loadMappingPage(tenantId, collectionId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return <>
    <h1>{result.collection.title}</h1>
    <MappingWorkspace tenantId={tenantId} catalogs={result.catalogs} catalogTotal={result.catalogTotal}
      canWrite={result.canWrite} initialCollection={result.collection} />
  </>;
}

async function loadMappingPage(tenantId: string, collectionId: string, returnTo: string) {
  try {
    const [collection, catalogs, tenants] = await Promise.all([
      getMappingCollection(tenantId, collectionId, returnTo),
      listCatalogs(tenantId, { limit: 200, offset: 0 }, returnTo),
      listTenants(returnTo),
    ]);
    return {
      ok: true as const,
      collection,
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
