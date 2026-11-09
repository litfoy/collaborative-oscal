from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4, uuid5

from collaborative_oscal_oscal.catalog_index import (
    canonical_json_sha256,
    document_metadata,
    project_catalog_indexes,
)

from app.domain.catalogs.models import (
    CatalogControlIndex,
    CatalogGroupIndex,
    CatalogRevision,
    CatalogRevisionStatus,
)


def prepare_catalog_revision(
    tenant_id: UUID,
    catalog_id: UUID,
    revision_number: int,
    document: Mapping[str, Any],
    *,
    source_version: str | None,
    source_format: str | None,
) -> tuple[CatalogRevision, list[CatalogGroupIndex], list[CatalogControlIndex]]:
    document_uuid, oscal_version = document_metadata(document)
    content_sha256 = canonical_json_sha256(document)
    revision_id = uuid4()
    group_projections, control_projections = project_catalog_indexes(document)
    group_ids = {
        group.structural_path: uuid5(revision_id, f"group:{group.structural_path}")
        for group in group_projections
    }
    control_ids = {
        control.structural_path: uuid5(revision_id, f"control:{control.structural_path}")
        for control in control_projections
    }
    groups = [
        CatalogGroupIndex(
            id=group_ids[group.structural_path],
            tenant_id=tenant_id,
            catalog_revision_id=revision_id,
            oscal_group_id=group.oscal_group_id,
            parent_group_id=group_ids.get(group.parent_path),
            structural_path=group.structural_path,
            title=group.title,
            display_order=group.display_order,
        )
        for group in group_projections
    ]
    controls = [
        CatalogControlIndex(
            id=control_ids[control.structural_path],
            tenant_id=tenant_id,
            catalog_revision_id=revision_id,
            oscal_control_id=control.oscal_control_id,
            parent_control_id=control_ids.get(control.parent_path),
            group_id=group_ids.get(control.group_path),
            title=control.title,
            structural_path=control.structural_path,
            display_order=control.display_order,
        )
        for control in control_projections
    ]
    now = datetime.now(UTC)
    revision = CatalogRevision(
        id=revision_id,
        tenant_id=tenant_id,
        catalog_id=catalog_id,
        revision_number=revision_number,
        lifecycle_status=CatalogRevisionStatus.DRAFT,
        oscal_document_uuid=document_uuid,
        oscal_version=oscal_version,
        source_version=source_version,
        source_format=source_format,
        content_sha256=content_sha256,
        content=dict(document),
        created_at=now,
        updated_at=now,
        published_at=None,
    )
    return revision, groups, controls
