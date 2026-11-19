// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiProblem } from "@/components/ApiProblem";
import { ProfileManager } from "@/components/ProfileManager";
import { listCatalogs, listProfiles, listTenants } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";

export default async function ProfilesPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { t, number } = await getI18n();
  const { tenantId } = await params;
  const here = `/t/${tenantId}/profiles`;
  const result = await loadProfilesPage(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  const { profiles, catalogs, canWrite } = result;
  return (
    <>
      <h1>{t("nav.profiles")}</h1>
      <p className="muted">
        {t("profilePage.intro")}
      </p>
      <ProfileManager
        tenantId={tenantId}
        profiles={profiles.items}
        catalogs={catalogs.items}
        catalogTotal={catalogs.total}
        canWrite={canWrite}
      />
      {profiles.total > profiles.items.length ? (
        <p role="status" className="muted">
          {t("profilePage.showing", { count: number(profiles.items.length), total: number(profiles.total) })}
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
