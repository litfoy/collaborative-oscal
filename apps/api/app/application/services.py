from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.application.catalog_revisions import prepare_catalog_revision
from app.domain.catalogs.models import (
    Catalog,
    CatalogControlIndex,
    CatalogOriginType,
    CatalogRevision,
)
from app.domain.errors import DomainInvariantError, EntityNotFoundError
from app.domain.organizations.invariants import validate_parent_chain
from app.domain.organizations.models import Organization
from app.domain.repositories import UnitOfWork
from app.domain.tenancy.models import Tenant

UnitOfWorkFactory = Callable[[], UnitOfWork]


def _now() -> datetime:
    return datetime.now(UTC)


class GrcService:
    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def create_tenant(self, name: str, slug: str) -> Tenant:
        now = _now()
        tenant = Tenant(id=uuid4(), name=name, slug=slug, created_at=now, updated_at=now)
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.tenants.add(tenant)
        return tenant

    def create_organization(
        self,
        tenant_id: UUID,
        name: str,
        slug: str,
        parent_organization_id: UUID | None = None,
    ) -> Organization:
        now = _now()
        organization = Organization(
            id=uuid4(),
            tenant_id=tenant_id,
            parent_organization_id=parent_organization_id,
            name=name,
            slug=slug,
            created_at=now,
            updated_at=now,
        )
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.tenants.get(tenant_id) is None:
                raise EntityNotFoundError("Tenant not found.")
            if unit_of_work.organizations.slug_exists(tenant_id, slug):
                raise DomainInvariantError("Organization slug must be unique within its tenant.")
            if parent_organization_id is not None:
                parent = unit_of_work.organizations.get(tenant_id, parent_organization_id)
                if parent is None:
                    raise EntityNotFoundError("Organization parent not found in this tenant.")
                validate_parent_chain(
                    organization.id,
                    parent_organization_id,
                    lambda organization_id: unit_of_work.organizations.get_parent_id(
                        tenant_id, organization_id
                    ),
                )
            unit_of_work.organizations.add(organization)
        return organization

    def create_catalog(
        self,
        tenant_id: UUID,
        name: str,
        origin_type: CatalogOriginType,
        description: str | None = None,
        source_uri: str | None = None,
        source_organization: str | None = None,
        license_identifier: str | None = None,
    ) -> Catalog:
        now = _now()
        catalog = Catalog(
            id=uuid4(),
            tenant_id=tenant_id,
            name=name,
            description=description,
            origin_type=origin_type,
            source_uri=source_uri,
            source_organization=source_organization,
            license_identifier=license_identifier,
            created_at=now,
            updated_at=now,
        )
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.tenants.get(tenant_id) is None:
                raise EntityNotFoundError("Tenant not found.")
            unit_of_work.catalogs.add(catalog)
        return catalog

    def create_draft_catalog_revision(
        self,
        tenant_id: UUID,
        catalog_id: UUID,
        document: Mapping[str, Any],
        source_version: str | None = None,
    ) -> CatalogRevision:
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.catalogs.get(tenant_id, catalog_id) is None:
                raise EntityNotFoundError("Catalog not found in this tenant.")
            revision, groups, controls = prepare_catalog_revision(
                tenant_id,
                catalog_id,
                unit_of_work.revisions.next_revision_number(tenant_id, catalog_id),
                document,
                source_version=source_version,
                source_format=None,
            )
            unit_of_work.revisions.add(revision, groups, controls)
        return revision

    def get_catalog_revision(self, tenant_id: UUID, revision_id: UUID) -> CatalogRevision:
        with self._unit_of_work_factory() as unit_of_work:
            revision = unit_of_work.revisions.get(tenant_id, revision_id)
        if revision is None:
            raise EntityNotFoundError("Catalog revision not found in this tenant.")
        return revision

    def list_catalogs(self, tenant_id: UUID) -> Sequence[Catalog]:
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.tenants.get(tenant_id) is None:
                raise EntityNotFoundError("Tenant not found.")
            return unit_of_work.catalogs.list_for_tenant(tenant_id)

    def get_indexed_controls(
        self, tenant_id: UUID, revision_id: UUID
    ) -> Sequence[CatalogControlIndex]:
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.revisions.get(tenant_id, revision_id) is None:
                raise EntityNotFoundError("Catalog revision not found in this tenant.")
            return unit_of_work.revisions.list_controls(tenant_id, revision_id)
