from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.catalogs.models import (
    Catalog,
    CatalogControlIndex,
    CatalogGroupIndex,
    CatalogOriginType,
    CatalogRevision,
    CatalogRevisionStatus,
)
from app.domain.errors import EntityNotFoundError
from app.domain.organizations.models import Organization
from app.domain.tenancy.models import Tenant
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogGroupIndexRecord,
    CatalogRecord,
    CatalogRevisionRecord,
    OrganizationRecord,
    TenantRecord,
)


def _tenant(record: TenantRecord) -> Tenant:
    return Tenant(record.id, record.name, record.slug, record.created_at, record.updated_at)


def _organization(record: OrganizationRecord) -> Organization:
    return Organization(
        record.id,
        record.tenant_id,
        record.parent_organization_id,
        record.name,
        record.slug,
        record.created_at,
        record.updated_at,
    )


def _catalog(record: CatalogRecord) -> Catalog:
    return Catalog(
        record.id,
        record.tenant_id,
        record.name,
        record.description,
        CatalogOriginType(record.origin_type),
        record.source_uri,
        record.source_organization,
        record.license_identifier,
        record.created_at,
        record.updated_at,
    )


def _revision(record: CatalogRevisionRecord) -> CatalogRevision:
    return CatalogRevision(
        record.id,
        record.tenant_id,
        record.catalog_id,
        record.revision_number,
        CatalogRevisionStatus(record.lifecycle_status),
        record.oscal_document_uuid,
        record.oscal_version,
        record.source_version,
        record.content_sha256,
        record.content,
        record.created_at,
        record.updated_at,
        record.published_at,
    )


def _group_index(record: CatalogGroupIndexRecord) -> CatalogGroupIndex:
    return CatalogGroupIndex(
        record.id,
        record.tenant_id,
        record.catalog_revision_id,
        record.oscal_group_id,
        record.parent_group_id,
        record.structural_path,
        record.title,
        record.display_order,
    )


def _control_index(record: CatalogControlIndexRecord) -> CatalogControlIndex:
    return CatalogControlIndex(
        record.id,
        record.tenant_id,
        record.catalog_revision_id,
        record.oscal_control_id,
        record.parent_control_id,
        record.group_id,
        record.title,
        record.structural_path,
        record.display_order,
    )


class SQLTenantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, tenant: Tenant) -> None:
        self._session.add(
            TenantRecord(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                created_at=tenant.created_at,
                updated_at=tenant.updated_at,
            )
        )

    def get(self, tenant_id: UUID) -> Tenant | None:
        record = self._session.get(TenantRecord, tenant_id)
        return _tenant(record) if record is not None else None


class SQLOrganizationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, organization: Organization) -> None:
        self._session.add(
            OrganizationRecord(
                id=organization.id,
                tenant_id=organization.tenant_id,
                parent_organization_id=organization.parent_organization_id,
                name=organization.name,
                slug=organization.slug,
                created_at=organization.created_at,
                updated_at=organization.updated_at,
            )
        )

    def get(self, tenant_id: UUID, organization_id: UUID) -> Organization | None:
        statement = select(OrganizationRecord).where(
            OrganizationRecord.tenant_id == tenant_id,
            OrganizationRecord.id == organization_id,
        )
        record = self._session.scalar(statement)
        return _organization(record) if record is not None else None

    def slug_exists(self, tenant_id: UUID, slug: str) -> bool:
        statement = select(OrganizationRecord.id).where(
            OrganizationRecord.tenant_id == tenant_id,
            OrganizationRecord.slug == slug,
        )
        return self._session.scalar(statement) is not None

    def get_parent_id(self, tenant_id: UUID, organization_id: UUID) -> UUID | None:
        organization = self.get(tenant_id, organization_id)
        if organization is None:
            raise EntityNotFoundError("Organization parent not found in this tenant.")
        return organization.parent_organization_id


class SQLCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, catalog: Catalog) -> None:
        self._session.add(
            CatalogRecord(
                id=catalog.id,
                tenant_id=catalog.tenant_id,
                name=catalog.name,
                description=catalog.description,
                origin_type=catalog.origin_type.value,
                source_uri=catalog.source_uri,
                source_organization=catalog.source_organization,
                license_identifier=catalog.license_identifier,
                created_at=catalog.created_at,
                updated_at=catalog.updated_at,
            )
        )

    def get(self, tenant_id: UUID, catalog_id: UUID) -> Catalog | None:
        statement = select(CatalogRecord).where(
            CatalogRecord.tenant_id == tenant_id,
            CatalogRecord.id == catalog_id,
        )
        record = self._session.scalar(statement)
        return _catalog(record) if record is not None else None

    def list_for_tenant(self, tenant_id: UUID) -> Sequence[Catalog]:
        statement = (
            select(CatalogRecord)
            .where(CatalogRecord.tenant_id == tenant_id)
            .order_by(CatalogRecord.created_at, CatalogRecord.id)
        )
        return [_catalog(record) for record in self._session.scalars(statement)]


class SQLCatalogRevisionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def next_revision_number(self, tenant_id: UUID, catalog_id: UUID) -> int:
        catalog_statement = (
            select(CatalogRecord)
            .where(CatalogRecord.tenant_id == tenant_id, CatalogRecord.id == catalog_id)
            .with_for_update()
        )
        if self._session.scalar(catalog_statement) is None:
            raise EntityNotFoundError("Catalog not found in this tenant.")
        statement = select(func.max(CatalogRevisionRecord.revision_number)).where(
            CatalogRevisionRecord.tenant_id == tenant_id,
            CatalogRevisionRecord.catalog_id == catalog_id,
        )
        return (self._session.scalar(statement) or 0) + 1

    def add(
        self,
        revision: CatalogRevision,
        groups: Sequence[CatalogGroupIndex],
        controls: Sequence[CatalogControlIndex],
    ) -> None:
        self._session.add(
            CatalogRevisionRecord(
                id=revision.id,
                tenant_id=revision.tenant_id,
                catalog_id=revision.catalog_id,
                revision_number=revision.revision_number,
                lifecycle_status=revision.lifecycle_status.value,
                oscal_document_uuid=revision.oscal_document_uuid,
                oscal_version=revision.oscal_version,
                source_version=revision.source_version,
                content_sha256=revision.content_sha256,
                content=revision.content,
                created_at=revision.created_at,
                updated_at=revision.updated_at,
                published_at=revision.published_at,
            )
        )
        self._session.flush()
        self._session.add_all(
            [
                CatalogGroupIndexRecord(
                    id=group.id,
                    tenant_id=group.tenant_id,
                    catalog_revision_id=group.catalog_revision_id,
                    oscal_group_id=group.oscal_group_id,
                    parent_group_id=group.parent_group_id,
                    structural_path=group.structural_path,
                    title=group.title,
                    display_order=group.display_order,
                )
                for group in groups
            ]
        )
        self._session.flush()
        self._session.add_all(
            [
                CatalogControlIndexRecord(
                    id=control.id,
                    tenant_id=control.tenant_id,
                    catalog_revision_id=control.catalog_revision_id,
                    oscal_control_id=control.oscal_control_id,
                    parent_control_id=control.parent_control_id,
                    group_id=control.group_id,
                    title=control.title,
                    structural_path=control.structural_path,
                    display_order=control.display_order,
                )
                for control in controls
            ]
        )

    def get(self, tenant_id: UUID, revision_id: UUID) -> CatalogRevision | None:
        statement = select(CatalogRevisionRecord).where(
            CatalogRevisionRecord.tenant_id == tenant_id,
            CatalogRevisionRecord.id == revision_id,
        )
        record = self._session.scalar(statement)
        return _revision(record) if record is not None else None

    def list_controls(self, tenant_id: UUID, revision_id: UUID) -> Sequence[CatalogControlIndex]:
        statement = (
            select(CatalogControlIndexRecord)
            .where(
                CatalogControlIndexRecord.tenant_id == tenant_id,
                CatalogControlIndexRecord.catalog_revision_id == revision_id,
            )
            .order_by(CatalogControlIndexRecord.structural_path)
        )
        return [_control_index(record) for record in self._session.scalars(statement)]


class SQLAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SQLAlchemyUnitOfWork:
        self._session = self._session_factory()
        self._session.begin()
        self.tenants = SQLTenantRepository(self._session)
        self.organizations = SQLOrganizationRepository(self._session)
        self.catalogs = SQLCatalogRepository(self._session)
        self.revisions = SQLCatalogRevisionRepository(self._session)
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self._session is None:
            raise RuntimeError("Unit of work was not entered.")
        try:
            if exception_type is None:
                try:
                    self._session.commit()
                except BaseException:
                    self._session.rollback()
                    raise
            else:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None
        return False
