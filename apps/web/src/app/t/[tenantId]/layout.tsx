import type { ReactNode } from "react";

import { ApiProblem } from "@/components/ApiProblem";
import { AppShell } from "@/components/AppShell";
import { listTenants } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { requireSession } from "@/lib/auth";
import { isUuid } from "@/lib/safe";
import { getI18n } from "@/lib/i18n/server";

export default async function TenantLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ tenantId: string }>;
}) {
  const { t } = await getI18n();
  const { tenantId } = await params;
  const session = await requireSession(`/t/${tenantId}/catalogs`);
  const userName = session.name ?? session.email ?? t("auth.signedIn");
  const demoMode = "kind" in session && session.kind === "demo";

  let tenants;
  try {
    tenants = (await listTenants(`/t/${tenantId}/catalogs`)).items;
  } catch (error) {
    return (
      <AppShell userName={userName} tenants={[]} demoMode={demoMode}>
        <ApiProblem error={error} />
      </AppShell>
    );
  }

  // The tenant list only contains workspaces the backend says the user belongs to.
  if (!isUuid(tenantId) || !tenants.some((tenant) => tenant.id === tenantId)) {
    return (
      <AppShell userName={userName} tenants={tenants} demoMode={demoMode}>
        <ApiProblem error={new ApiError("forbidden", 403, "forbidden")} />
      </AppShell>
    );
  }

  return (
    <AppShell userName={userName} tenants={tenants} currentTenantId={tenantId} demoMode={demoMode}>
      {children}
    </AppShell>
  );
}
