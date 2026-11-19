// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiProblem } from "@/components/ApiProblem";
import { MeasureDetailWorkspace } from "@/components/MeasureDetailWorkspace";
import { getComponentDefinition, listCatalogs, listTenants } from "@/lib/api";

export default async function MeasurePage({
  params,
}: {
  params: Promise<{ tenantId: string; documentId: string; componentId: string }>;
}) {
  const { tenantId, documentId, componentId } = await params;
  const here = `/t/${tenantId}/measures/${documentId}/${componentId}`;
  const result = await loadMeasure(tenantId, documentId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return <MeasureDetailWorkspace tenantId={tenantId} initialDocument={result.document} componentId={componentId}
    catalogs={result.catalogs.items} catalogTotal={result.catalogs.total} canWrite={result.canWrite} />;
}

async function loadMeasure(tenantId: string, documentId: string, here: string) {
  try {
    const [document, catalogs, tenants] = await Promise.all([
      getComponentDefinition(tenantId, documentId, here),
      listCatalogs(tenantId, { limit: 200, offset: 0 }, here),
      listTenants(here),
    ]);
    return { ok: true as const, document, catalogs,
      canWrite: tenants.items.some((tenant) => tenant.id === tenantId && tenant.permissions.includes("catalog:write")) };
  } catch (error) {
    return { ok: false as const, error };
  }
}
