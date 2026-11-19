// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiProblem } from "@/components/ApiProblem";
import { SystemComponentSnapshotView } from "@/components/SystemComponentSnapshotView";
import {
  exportComponentDefinitionSnapshotComponent,
  getSystem,
  listSystemComponents,
} from "@/lib/api";

export default async function SystemComponentSourceSnapshotPage({
  params,
}: {
  params: Promise<{ tenantId: string; systemId: string; componentId: string }>;
}) {
  const { tenantId, systemId, componentId } = await params;
  const here = `/t/${tenantId}/systems/${systemId}/components/${componentId}/source-snapshot`;
  const result = await loadSnapshotView(tenantId, systemId, componentId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  return (
    <SystemComponentSnapshotView
      tenantId={tenantId}
      systemId={systemId}
      systemName={result.system.name}
      component={result.component}
      snapshot={result.snapshot}
    />
  );
}

async function loadSnapshotView(
  tenantId: string,
  systemId: string,
  componentId: string,
  here: string,
) {
  try {
    const [system, components] = await Promise.all([
      getSystem(tenantId, systemId, here),
      listSystemComponents(tenantId, systemId, here),
    ]);
    const component = components.find((item) => item.id === componentId);
    if (!component || !component.source_snapshot_id || !component.source_component_uuid) {
      throw new Error("Component source snapshot not found.");
    }
    const snapshot = await exportComponentDefinitionSnapshotComponent(
      tenantId,
      component.source_snapshot_id,
      component.source_component_uuid,
      here,
    );
    return { ok: true as const, system, component, snapshot };
  } catch (error) {
    return { ok: false as const, error };
  }
}

