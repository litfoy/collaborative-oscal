import { ApiProblem } from "@/components/ApiProblem";
import { SystemsList } from "@/components/SystemsList";
import { listSystems, listTenants } from "@/lib/api";

export default async function SystemsPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const here = `/t/${tenantId}/systems`;
  const result = await loadSystems(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return (
    <>
      <h1>Systems and System Security Plans</h1>
      <p className="muted">
        Systems are stable identities for the actual systems being secured. SSPs pin
        Catalog revisions and document selected implementation contributions; they
        are not assessment reports or compliance conclusions.
      </p>
      <SystemsList
        tenantId={tenantId}
        initialSystems={result.systems}
        canWrite={result.canWrite}
      />
    </>
  );
}

async function loadSystems(tenantId: string, returnTo: string) {
  try {
    const [systems, tenants] = await Promise.all([
      listSystems(tenantId, returnTo),
      listTenants(returnTo),
    ]);
    const tenant = tenants.items.find((item) => item.id === tenantId);
    return {
      ok: true as const,
      systems,
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}
