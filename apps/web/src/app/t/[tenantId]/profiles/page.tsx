import { ApiProblem } from "@/components/ApiProblem";
import { ProfileManager } from "@/components/ProfileManager";
import { listCatalogs, listProfiles, listTenants } from "@/lib/api";

export default async function ProfilesPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const here = `/t/${tenantId}/profiles`;
  const result = await loadProfilesPage(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  const { profiles, catalogs, canWrite } = result;
  return (
    <>
      <h1>Profiles</h1>
      <p className="muted">
        Select controls from an immutable catalog revision. Profile changes never modify the
        source catalog.
      </p>
      <ProfileManager
        tenantId={tenantId}
        profiles={profiles.items}
        catalogs={catalogs.items}
        canWrite={canWrite}
      />
      {profiles.total > profiles.items.length ? (
        <p role="status" className="muted">
          Showing {profiles.items.length} of {profiles.total} profiles.
        </p>
      ) : null}
    </>
  );
}

async function loadProfilesPage(tenantId: string, returnTo: string) {
  try {
    const [profiles, catalogs, tenants] = await Promise.all([
      listProfiles(tenantId, returnTo),
      listCatalogs(tenantId, { limit: 200, offset: 0 }, returnTo),
      listTenants(returnTo),
    ]);
    const tenant = tenants.items.find((item) => item.id === tenantId);
    return {
      ok: true as const,
      profiles,
      catalogs,
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}
