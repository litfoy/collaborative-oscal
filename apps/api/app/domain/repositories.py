from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import Protocol
from uuid import UUID

from app.domain.catalogs.models import (
    Catalog,
    CatalogControlIndex,
    CatalogGroupIndex,
    CatalogRevision,
)
from app.domain.organizations.models import Organization
from app.domain.tenancy.models import Tenant


class TenantRepository(Protocol):
    def add(self, tenant: Tenant) -> None: ...

    def get(self, tenant_id: UUID) -> Tenant | None: ...


class OrganizationRepository(Protocol):
    def add(self, organization: Organization) -> None: ...

    def get(self, tenant_id: UUID, organization_id: UUID) -> Organization | None: ...

    def slug_exists(self, tenant_id: UUID, slug: str) -> bool: ...

    def get_parent_id(self, tenant_id: UUID, organization_id: UUID) -> UUID | None: ...


class CatalogRepository(Protocol):
    def add(self, catalog: Catalog) -> None: ...

    def get(self, tenant_id: UUID, catalog_id: UUID) -> Catalog | None: ...

    def list_for_tenant(self, tenant_id: UUID) -> Sequence[Catalog]: ...


class CatalogRevisionRepository(Protocol):
    def next_revision_number(self, tenant_id: UUID, catalog_id: UUID) -> int: ...

    def add(
        self,
        revision: CatalogRevision,
        groups: Sequence[CatalogGroupIndex],
        controls: Sequence[CatalogControlIndex],
    ) -> None: ...

    def get(self, tenant_id: UUID, revision_id: UUID) -> CatalogRevision | None: ...

    def list_controls(
        self, tenant_id: UUID, revision_id: UUID
    ) -> Sequence[CatalogControlIndex]: ...


class UnitOfWork(Protocol):
    tenants: TenantRepository
    organizations: OrganizationRepository
    catalogs: CatalogRepository
    revisions: CatalogRevisionRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...
