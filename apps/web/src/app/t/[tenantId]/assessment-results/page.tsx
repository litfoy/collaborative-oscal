// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiProblem } from "@/components/ApiProblem";
import {
  AssessmentResultsWorkspace,
  type AssessmentResultOverviewItem,
} from "@/components/AssessmentResultsWorkspace";
import {
  listAssessmentPlanVersions,
  listAssessmentPlans,
  listAssessmentResultVersions,
  listAssessmentResults,
  listSystems,
  listTenants,
} from "@/lib/api";
import type { AssessmentPlan, AssessmentPlanVersion } from "@/lib/types";

export default async function AssessmentResultsPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const here = `/t/${tenantId}/assessment-results`;
  const result = await loadAssessmentResultsOverview(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return (
    <AssessmentResultsWorkspace
      tenantId={tenantId}
      items={result.items}
      systems={result.systems}
      plansBySystem={result.plansBySystem}
      versionsByPlan={result.versionsByPlan}
      canWrite={result.canWrite}
    />
  );
}

async function loadAssessmentResultsOverview(tenantId: string, here: string) {
  try {
    const [systems, tenants] = await Promise.all([
      listSystems(tenantId, here),
      listTenants(here),
    ]);

    const plansBySystem: Record<string, AssessmentPlan[]> = Object.fromEntries(
      await Promise.all(
        systems.map(async (system) => [
          system.id,
          await listAssessmentPlans(tenantId, system.id, here),
        ]),
      ),
    );

    const allPlans = Object.values(plansBySystem).flat();
    const versionsByPlan: Record<string, AssessmentPlanVersion[]> = Object.fromEntries(
      await Promise.all(
        allPlans.map(async (plan) => [
          plan.id,
          await listAssessmentPlanVersions(tenantId, plan.id, here),
        ]),
      ),
    );

    const items: AssessmentResultOverviewItem[] = [];
    for (const system of systems) {
      const results = await listAssessmentResults(tenantId, system.id, here);
      for (const result of results) {
        const plan = (plansBySystem[system.id] ?? []).find(
          (item) => item.id === result.assessment_plan_id,
        ) ?? null;
        const planVersion = plan
          ? (versionsByPlan[plan.id] ?? []).find(
              (item) => item.id === result.assessment_plan_version_id,
            ) ?? null
          : null;
        items.push({
          result,
          system,
          plan,
          planVersion,
          immutableVersionCount: (
            await listAssessmentResultVersions(tenantId, result.id, here)
          ).length,
        });
      }
    }

    const tenant = tenants.items.find((item) => item.id === tenantId);
    return {
      ok: true as const,
      items,
      systems,
      plansBySystem,
      versionsByPlan,
      canWrite: tenant?.permissions.includes("catalog:write") ?? false,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}


