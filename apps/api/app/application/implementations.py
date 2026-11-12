from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domain.catalogs.read_models import Page
from app.domain.errors import EntityNotFoundError
from app.domain.implementations import (
    ControlImplementation,
    ImplementationInformation,
    ImplementationStatus,
    Responsibility,
    ResponsibilityKind,
)
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogRevisionRecord,
    ControlImplementationRecord,
    ImplementationResponsibilityRecord,
    OrganizationRecord,
    ProfileRecord,
    TenantMembershipRecord,
    UserIdentityRecord,
)
from app.persistence.profile_repository import SQLProfileRepository

SessionScope = Callable[[], AbstractContextManager[Session]]


class InvalidImplementation(ValueError):
    pass


class ImplementationService:
    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    def create(
        self,
        tenant_id: UUID,
        actor: UUID,
        catalog_id: UUID,
        revision_id: UUID,
        control_id: str,
        organization_id: UUID | None,
        profile_id: UUID | None,
        information: ImplementationInformation,
        profile_import_id: UUID | None = None,
    ) -> ControlImplementation:
        with self._session_scope() as session:
            if profile_id is None and profile_import_id is not None:
                raise InvalidImplementation("An import requires a profile.")
            source_exists = session.scalar(
                select(CatalogControlIndexRecord.id)
                .join(
                    CatalogRevisionRecord,
                    (CatalogRevisionRecord.tenant_id == CatalogControlIndexRecord.tenant_id)
                    & (CatalogRevisionRecord.id == CatalogControlIndexRecord.catalog_revision_id),
                )
                .where(
                    CatalogRevisionRecord.tenant_id == tenant_id,
                    CatalogRevisionRecord.catalog_id == catalog_id,
                    CatalogRevisionRecord.id == revision_id,
                    CatalogControlIndexRecord.oscal_control_id == control_id,
                )
            )
            if source_exists is None:
                raise EntityNotFoundError("Control definition not found.")
            if profile_id is not None:
                locked = session.scalar(
                    select(ProfileRecord)
                    .where(ProfileRecord.tenant_id == tenant_id, ProfileRecord.id == profile_id)
                    .with_for_update()
                )
                if locked is None:
                    raise EntityNotFoundError("Profile not found.")
                profile = SQLProfileRepository(session).get(tenant_id, profile_id)
                assert profile is not None
                matches = [
                    item
                    for item in profile.imports
                    if item.catalog_id == catalog_id
                    and item.revision_id == revision_id
                    and control_id in item.control_ids
                    and (profile_import_id is None or item.id == profile_import_id)
                ]
                if len(matches) != 1:
                    raise InvalidImplementation(
                        "Select an unambiguous profile import containing this control."
                    )
                profile_import_id = matches[0].id
            revision = session.scalar(
                select(CatalogRevisionRecord)
                .where(
                    CatalogRevisionRecord.tenant_id == tenant_id,
                    CatalogRevisionRecord.catalog_id == catalog_id,
                    CatalogRevisionRecord.id == revision_id,
                )
                .with_for_update()
            )
            control = session.scalar(
                select(CatalogControlIndexRecord.id).where(
                    CatalogControlIndexRecord.tenant_id == tenant_id,
                    CatalogControlIndexRecord.catalog_revision_id == revision_id,
                    CatalogControlIndexRecord.oscal_control_id == control_id,
                )
            )
            if revision is None or control is None:
                raise EntityNotFoundError("Control definition not found.")
            if (
                organization_id is not None
                and session.scalar(
                    select(OrganizationRecord.id).where(
                        OrganizationRecord.tenant_id == tenant_id,
                        OrganizationRecord.id == organization_id,
                    )
                )
                is None
            ):
                raise EntityNotFoundError("Organization not found.")
            self._validate_responsibilities(session, tenant_id, information.responsibilities, set())
            now = datetime.now(UTC)
            record = ControlImplementationRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                organization_id=organization_id,
                profile_id=profile_id,
                profile_import_id=profile_import_id,
                catalog_id=catalog_id,
                revision_id=revision_id,
                oscal_control_id=control_id,
                description=information.description,
                status=information.status.value,
                evidence_references=information.evidence_references,
                created_by=actor,
                updated_by=actor,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            self._save_responsibilities(session, record, information.responsibilities)
            return self._to_domain(record, information.responsibilities)

    def get(self, tenant_id: UUID, implementation_id: UUID) -> ControlImplementation:
        with self._session_scope() as session:
            record = self._get_record(session, tenant_id, implementation_id)
            return self._to_domain(record, self._responsibilities(session, record))

    def list(
        self,
        tenant_id: UUID,
        *,
        profile_id: UUID | None,
        organization_id: UUID | None,
        tenant_scope: bool,
        limit: int,
        offset: int,
    ) -> Page[ControlImplementation]:
        with self._session_scope() as session:
            filters = [ControlImplementationRecord.tenant_id == tenant_id]
            if profile_id is not None:
                filters.append(ControlImplementationRecord.profile_id == profile_id)
            if organization_id is not None:
                filters.append(ControlImplementationRecord.organization_id == organization_id)
            elif tenant_scope:
                filters.append(ControlImplementationRecord.organization_id.is_(None))
            total = (
                session.scalar(
                    select(func.count()).select_from(ControlImplementationRecord).where(*filters)
                )
                or 0
            )
            records = session.scalars(
                select(ControlImplementationRecord)
                .where(*filters)
                .order_by(
                    ControlImplementationRecord.created_at.desc(), ControlImplementationRecord.id
                )
                .limit(limit)
                .offset(offset)
            ).all()
            return Page(
                [self._to_domain(r, self._responsibilities(session, r)) for r in records],
                total,
                limit,
                offset,
            )

    def update(
        self,
        tenant_id: UUID,
        actor: UUID,
        implementation_id: UUID,
        information: ImplementationInformation,
    ) -> ControlImplementation:
        with self._session_scope() as session:
            record = self._get_record(session, tenant_id, implementation_id, lock=True)
            old = self._responsibilities(session, record)
            self._validate_responsibilities(
                session, tenant_id, information.responsibilities, set(old)
            )
            record.description = information.description
            record.status = information.status.value
            record.evidence_references = information.evidence_references
            record.updated_by = actor
            record.updated_at = datetime.now(UTC)
            session.execute(
                delete(ImplementationResponsibilityRecord).where(
                    ImplementationResponsibilityRecord.tenant_id == tenant_id,
                    ImplementationResponsibilityRecord.implementation_id == record.id,
                )
            )
            self._save_responsibilities(session, record, information.responsibilities)
            return self._to_domain(record, information.responsibilities)

    def options(
        self, tenant_id: UUID
    ) -> tuple[list[tuple[UUID, str]], list[tuple[UUID, str | None]]]:
        with self._session_scope() as session:
            organizations = session.execute(
                select(OrganizationRecord.id, OrganizationRecord.name)
                .where(OrganizationRecord.tenant_id == tenant_id)
                .order_by(OrganizationRecord.name, OrganizationRecord.id)
            ).all()
            people = session.execute(
                select(UserIdentityRecord.id, UserIdentityRecord.display_name)
                .join(
                    TenantMembershipRecord, TenantMembershipRecord.user_id == UserIdentityRecord.id
                )
                .where(
                    TenantMembershipRecord.tenant_id == tenant_id,
                    TenantMembershipRecord.status == "active",
                )
                .order_by(UserIdentityRecord.display_name, UserIdentityRecord.id)
            ).all()
            return [(row.id, row.name) for row in organizations], [
                (row.id, row.display_name) for row in people
            ]

    @staticmethod
    def _get_record(
        session: Session, tenant_id: UUID, implementation_id: UUID, *, lock: bool = False
    ) -> ControlImplementationRecord:
        query = select(ControlImplementationRecord).where(
            ControlImplementationRecord.tenant_id == tenant_id,
            ControlImplementationRecord.id == implementation_id,
        )
        record = session.scalar(query.with_for_update() if lock else query)
        if record is None:
            raise EntityNotFoundError("Implementation not found.")
        return record

    @staticmethod
    def _validate_responsibilities(
        session: Session,
        tenant_id: UUID,
        responsibilities: list[Responsibility],
        existing: set[Responsibility],
    ) -> None:
        users = {r.user_id for r in responsibilities if r.user_id is not None and r not in existing}
        if users:
            active = set(
                session.scalars(
                    select(TenantMembershipRecord.user_id).where(
                        TenantMembershipRecord.tenant_id == tenant_id,
                        TenantMembershipRecord.user_id.in_(users),
                        TenantMembershipRecord.status == "active",
                    )
                )
            )
            if users != active:
                raise InvalidImplementation("Responsible persons must be active tenant members.")

    @staticmethod
    def _responsibilities(
        session: Session, record: ControlImplementationRecord
    ) -> list[Responsibility]:
        rows = session.scalars(
            select(ImplementationResponsibilityRecord)
            .where(
                ImplementationResponsibilityRecord.tenant_id == record.tenant_id,
                ImplementationResponsibilityRecord.implementation_id == record.id,
            )
            .order_by(
                ImplementationResponsibilityRecord.kind, ImplementationResponsibilityRecord.id
            )
        )
        return [Responsibility(ResponsibilityKind(r.kind), r.user_id, r.role) for r in rows]

    @staticmethod
    def _save_responsibilities(
        session: Session,
        record: ControlImplementationRecord,
        responsibilities: list[Responsibility],
    ) -> None:
        for r in responsibilities:
            session.add(
                ImplementationResponsibilityRecord(
                    id=uuid4(),
                    tenant_id=record.tenant_id,
                    implementation_id=record.id,
                    kind=r.kind.value,
                    user_id=r.user_id,
                    role=r.role,
                )
            )

    @staticmethod
    def _to_domain(
        record: ControlImplementationRecord, responsibilities: list[Responsibility]
    ) -> ControlImplementation:
        return ControlImplementation(
            record.id,
            record.tenant_id,
            record.organization_id,
            record.profile_id,
            record.profile_import_id,
            record.catalog_id,
            record.revision_id,
            record.oscal_control_id,
            record.description,
            ImplementationStatus(record.status),
            record.evidence_references,
            responsibilities,
            record.created_by,
            record.updated_by,
            record.created_at,
            record.updated_at,
        )
