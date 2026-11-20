// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiProblem } from "@/components/ApiProblem";
import { ComplianceExplorerRequirementsView } from "@/components/ComplianceExplorerRequirementsView";
import { listProfiles, listSystems } from "@/lib/api";

const PROFILE_PAGE_SIZE = 200;

export default async function ComplianceExplorerPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const here = `/t/${tenantId}/compliance-explorer`;
  const result = await loadComplianceExplorerData(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;

  return (
    <ComplianceExplorerRequirementsView
      tenantId={tenantId}
      systems={result.systems}
      profiles={result.profiles}
    />
  );
}

async function loadComplianceExplorerData(tenantId: string, returnTo: string) {
  try {
    const [systems, firstProfilesPage] = await Promise.all([
      listSystems(tenantId, returnTo),
      listProfiles(tenantId, returnTo, { limit: PROFILE_PAGE_SIZE, offset: 0 }),
    ]);
    const profiles = [...firstProfilesPage.items];
    let offset = firstProfilesPage.items.length;
    while (offset < firstProfilesPage.total) {
      const nextPage = await listProfiles(tenantId, returnTo, {
        limit: PROFILE_PAGE_SIZE,
        offset,
      });
      if (nextPage.items.length === 0) break;
      profiles.push(...nextPage.items);
      offset += nextPage.items.length;
    }
    return {
      ok: true as const,
      systems,
      profiles,
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}

