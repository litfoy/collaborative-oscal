# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from uuid import UUID

from sqlalchemy import Select, select, tuple_
from sqlalchemy.orm import Session

from app.domain.errors import EntityNotFoundError
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogRevisionRecord,
    ControlImplementationRecord,
    InformationSystemRecord,
    ProfileImportRecord,
    ProfileRecord,
    SystemComponentRecord,
)

SessionScope = Callable[[], AbstractContextManager[Session]]


class ComplianceExplorerService:
    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    def project(
        self,
        tenant_id: UUID,
        system_id: UUID,
        profile_ids: Sequence[UUID],
        *,
        limit: int,
        offset: int,
    ) -> dict:
        with self._session_scope() as session:
            system = session.execute(
                select(InformationSystemRecord.id, InformationSystemRecord.name).where(
                    InformationSystemRecord.tenant_id == tenant_id,
                    InformationSystemRecord.id == system_id,
                )
            ).one_or_none()
            if system is None:
                raise EntityNotFoundError("System not found.")

            profile_records = session.scalars(
                select(ProfileRecord).where(
                    ProfileRecord.tenant_id == tenant_id,
                    ProfileRecord.id.in_(profile_ids),
                )
            ).all()
            if len(profile_records) != len(profile_ids):
                raise EntityNotFoundError("Profile not found.")

            profile_by_id = {record.id: record for record in profile_records}
            ordered_profiles = [
                {"id": profile_id, "title": profile_by_id[profile_id].title}
                for profile_id in profile_ids
            ]
            profile_order = {profile_id: index for index, profile_id in enumerate(profile_ids)}

            import_rows = session.execute(
                select(
                    ProfileImportRecord.profile_id,
                    ProfileImportRecord.id,
                    ProfileImportRecord.catalog_id,
                    ProfileImportRecord.revision_id,
                    ProfileImportRecord.position,
                ).where(
                    ProfileImportRecord.tenant_id == tenant_id,
                    ProfileImportRecord.profile_id.in_(profile_ids),
                    ProfileImportRecord.active.is_(True),
                )
            ).all()
            ordered_import_rows = sorted(
                import_rows,
                key=lambda row: (
                    profile_order[row.profile_id],
                    row.position,
                    row.id,
                ),
            )

            memberships_by_control: dict[tuple[UUID, UUID, str], list[dict]] = {}
            for row in ordered_import_rows:
                document_imports = profile_by_id[row.profile_id].document["profile"]["imports"]
                if row.position >= len(document_imports):
                    raise RuntimeError("Profile import registry does not match document.")
                control_ids = document_imports[row.position]["include-controls"][0]["with-ids"]
                for control_id in control_ids:
                    key = (row.catalog_id, row.revision_id, control_id)
                    memberships_by_control.setdefault(key, []).append(
                        {
                            "profile_id": row.profile_id,
                            "profile_title": profile_by_id[row.profile_id].title,
                            "profile_import_id": row.id,
                        }
                    )

            ordered_controls = sorted(
                memberships_by_control,
                key=lambda key: (str(key[0]), str(key[1]), key[2]),
            )
            total = len(ordered_controls)
            paged_controls = ordered_controls[offset : offset + limit]
            if not paged_controls:
                return {
                    "system": {"id": system.id, "name": system.name},
                    "profiles": ordered_profiles,
                    "items": [],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }

            title_rows = session.execute(
                self._control_title_query(tenant_id, paged_controls)
            ).all()
            titles = {
                (row.catalog_id, row.revision_id, row.oscal_control_id): row.title
                for row in title_rows
            }
            if any(control not in titles for control in paged_controls):
                raise EntityNotFoundError("Control definition not found.")

            implementation_rows = session.execute(
                self._implementation_query(tenant_id, system_id, paged_controls)
            ).all()
            implementations_by_control: dict[tuple[UUID, UUID, str], list[dict]] = {}
            for row in implementation_rows:
                component_title = None
                if row.component is not None:
                    component_title = row.component.get("title")
                control_key = (row.catalog_id, row.revision_id, row.oscal_control_id)
                implementations_by_control.setdefault(control_key, []).append(
                    {
                        "id": row.id,
                        "status": row.status,
                        "oscal_implementation_status": row.oscal_implementation_status,
                        "oscal_status_explanation": row.oscal_status_explanation,
                        "profile_id": row.profile_id,
                        "profile_import_id": row.profile_import_id,
                        "system_component_id": row.system_component_id,
                        "system_component": (
                            {"id": row.system_component_id, "title": component_title}
                            if row.system_component_id is not None
                            else None
                        ),
                    }
                )

            items = []
            for catalog_id, revision_id, control_id in paged_controls:
                items.append(
                    {
                        "reference": {
                            "catalog_id": catalog_id,
                            "revision_id": revision_id,
                            "oscal_control_id": control_id,
                        },
                        "title": titles[(catalog_id, revision_id, control_id)],
                        "memberships": memberships_by_control[
                            (catalog_id, revision_id, control_id)
                        ],
                        "implementations": implementations_by_control.get(
                            (catalog_id, revision_id, control_id), []
                        ),
                    }
                )

            return {
                "system": {"id": system.id, "name": system.name},
                "profiles": ordered_profiles,
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    @staticmethod
    def _control_title_query(
        tenant_id: UUID,
        controls: Sequence[tuple[UUID, UUID, str]],
    ) -> Select:
        return (
            select(
                CatalogRevisionRecord.catalog_id,
                CatalogRevisionRecord.id.label("revision_id"),
                CatalogControlIndexRecord.oscal_control_id,
                CatalogControlIndexRecord.title,
            )
            .join(
                CatalogControlIndexRecord,
                (CatalogControlIndexRecord.tenant_id == CatalogRevisionRecord.tenant_id)
                & (CatalogControlIndexRecord.catalog_revision_id == CatalogRevisionRecord.id),
            )
            .where(
                CatalogRevisionRecord.tenant_id == tenant_id,
                tuple_(
                    CatalogRevisionRecord.catalog_id,
                    CatalogRevisionRecord.id,
                    CatalogControlIndexRecord.oscal_control_id,
                ).in_(controls),
            )
        )

    @staticmethod
    def _implementation_query(
        tenant_id: UUID,
        system_id: UUID,
        controls: Sequence[tuple[UUID, UUID, str]],
    ) -> Select:
        return (
            select(
                ControlImplementationRecord.id,
                ControlImplementationRecord.catalog_id,
                ControlImplementationRecord.revision_id,
                ControlImplementationRecord.oscal_control_id,
                ControlImplementationRecord.status,
                ControlImplementationRecord.oscal_implementation_status,
                ControlImplementationRecord.oscal_status_explanation,
                ControlImplementationRecord.profile_id,
                ControlImplementationRecord.profile_import_id,
                ControlImplementationRecord.system_component_id,
                SystemComponentRecord.component,
            )
            .outerjoin(
                SystemComponentRecord,
                (SystemComponentRecord.tenant_id == ControlImplementationRecord.tenant_id)
                & (SystemComponentRecord.system_id == ControlImplementationRecord.system_id)
                & (SystemComponentRecord.id == ControlImplementationRecord.system_component_id),
            )
            .where(
                ControlImplementationRecord.tenant_id == tenant_id,
                ControlImplementationRecord.system_id == system_id,
                tuple_(
                    ControlImplementationRecord.catalog_id,
                    ControlImplementationRecord.revision_id,
                    ControlImplementationRecord.oscal_control_id,
                ).in_(controls),
            )
            .order_by(
                ControlImplementationRecord.catalog_id,
                ControlImplementationRecord.revision_id,
                ControlImplementationRecord.oscal_control_id,
                ControlImplementationRecord.created_at,
                ControlImplementationRecord.id,
            )
        )



