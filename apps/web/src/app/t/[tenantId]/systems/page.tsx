// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiProblem } from "@/components/ApiProblem";
import { SystemsList } from "@/components/SystemsList";
import { listSystemComponents, listSystemSecurityPlans, listSystems, listTenants } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";

export default async function SystemsPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { t } = await getI18n();
  const { tenantId } = await params;
  const here = `/t/${tenantId}/systems`;
  const result = await loadSystems(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return (
    <>
      <h1>{t("systemPage.title")}</h1>
      <p className="muted">
        {t("systemPage.intro")}
      </p>
      <SystemsList
        tenantId={tenantId}
        initialSystems={result.systems}
        initialCounts={result.counts}
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
    const counts = Object.fromEntries(await Promise.all(systems.map(async (system) => {
      const [components, plans] = await Promise.all([
        listSystemComponents(tenantId, system.id, returnTo),
        listSystemSecurityPlans(tenantId, system.id, returnTo),
      ]);
      return [system.id, { components: components.length, plans: plans.length }];
    })));
    return {
      ok: true as const,
      systems,
      counts,
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}
