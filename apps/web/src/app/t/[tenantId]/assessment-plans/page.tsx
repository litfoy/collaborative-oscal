// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiProblem } from "@/components/ApiProblem";
import {
  AssessmentPlansWorkspace,
  type AssessmentPlanOverviewItem,
} from "@/components/AssessmentPlansWorkspace";
import {
  getRevision,
  listAssessmentPlans,
  listAssessmentPlanVersions,
  listSystems,
  listSystemSecurityPlans,
  listSystemSecurityPlanVersions,
  listTenants,
} from "@/lib/api";
import type { RevisionSummary, SystemSecurityPlan, SystemSecurityPlanVersion } from "@/lib/types";

export default async function AssessmentPlansPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const here = `/t/${tenantId}/assessment-plans`;
  const result = await loadAssessmentPlansOverview(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return (
    <AssessmentPlansWorkspace
      tenantId={tenantId}
      items={result.items}
      systems={result.systems}
      sspBySystem={result.sspBySystem}
      versionsBySsp={result.versionsBySsp}
      revisionsBySsp={result.revisionsBySsp}
      canWrite={result.canWrite}
    />
  );
}

async function loadAssessmentPlansOverview(tenantId: string, here: string) {
  try {
    const [systems, tenants] = await Promise.all([
      listSystems(tenantId, here),
      listTenants(here),
    ]);
    const sspBySystem: Record<string, SystemSecurityPlan[]> = Object.fromEntries(
      await Promise.all(
        systems.map(async (system) => [
          system.id,
          await listSystemSecurityPlans(tenantId, system.id, here),
        ]),
      ),
    );
    const allSsp: SystemSecurityPlan[] = Object.values(sspBySystem).flat();
    const versionsBySsp: Record<string, SystemSecurityPlanVersion[]> = Object.fromEntries(
      await Promise.all(
        allSsp.map(async (ssp) => [
          ssp.id,
          await listSystemSecurityPlanVersions(tenantId, ssp.id, here),
        ]),
      ),
    );
    const revisionsBySsp: Record<string, RevisionSummary | null> = Object.fromEntries(
      await Promise.all(
        allSsp.map(async (ssp) => {
          const revision = await getRevision(tenantId, ssp.catalog_id, ssp.revision_id, here);
          return [ssp.id, revision];
        }),
      ),
    );

    const items: AssessmentPlanOverviewItem[] = [];
    for (const system of systems) {
      const plans = await listAssessmentPlans(tenantId, system.id, here);
      for (const plan of plans) {
        const immutableVersions = await listAssessmentPlanVersions(tenantId, plan.id, here);
        const ssp = (sspBySystem[system.id] ?? []).find(
          (candidate) => candidate.id === plan.system_security_plan_id,
        ) ?? null;
        const sspVersion = ssp
          ? (versionsBySsp[ssp.id] ?? []).find(
              (candidate) => candidate.id === plan.system_security_plan_version_id,
            ) ?? null
          : null;
        items.push({
          plan,
          system,
          ssp,
          sspVersion,
          revision: ssp ? revisionsBySsp[ssp.id] ?? null : null,
          immutableVersionCount: immutableVersions.length,
        });
      }
    }

    const tenant = tenants.items.find((item) => item.id === tenantId);
    return {
      ok: true as const,
      items,
      systems,
      sspBySystem,
      versionsBySsp,
      revisionsBySsp,
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}


