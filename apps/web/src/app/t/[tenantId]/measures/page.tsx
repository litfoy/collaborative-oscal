import { ApiProblem } from "@/components/ApiProblem";
import { ComponentDefinitionWorkspace } from "@/components/ComponentDefinitionWorkspace";
import { listCatalogs, listComponentDefinitions, listTenants } from "@/lib/api";

export default async function MeasuresPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const here = `/t/${tenantId}/measures`;
  const result = await loadMeasuresPage(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  const { definitions, catalogs, canWrite } = result;
  return (
      <ComponentDefinitionWorkspace
        tenantId={tenantId}
        initialDefinitions={definitions.items}
        definitionTotal={definitions.total}
        catalogs={catalogs.items}
        catalogTotal={catalogs.total}
        canWrite={canWrite}
      />
  );
}

async function loadMeasuresPage(tenantId: string, returnTo: string) {
  try {
    const [definitions, catalogs, tenants] = await Promise.all([
      listComponentDefinitions(tenantId, returnTo),
      listCatalogs(tenantId, { limit: 200, offset: 0 }, returnTo),
      listTenants(returnTo),
    ]);
    const tenant = tenants.items.find((item) => item.id === tenantId);
    return {
      ok: true as const,
      definitions,
      catalogs,
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}
