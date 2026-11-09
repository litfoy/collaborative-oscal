from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class TenantRole(StrEnum):
    TENANT_ADMIN = "tenant_admin"
    CATALOG_EDITOR = "catalog_editor"
    VIEWER = "viewer"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Permission(StrEnum):
    TENANT_READ = "tenant:read"
    TENANT_MANAGE = "tenant:manage"
    CATALOG_READ = "catalog:read"
    CATALOG_WRITE = "catalog:write"
    CATALOG_IMPORT = "catalog:import"


@dataclass(frozen=True, slots=True)
class UserIdentity:
    id: UUID
    issuer: str
    subject: str
    display_name: str | None
    email: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TenantMembership:
    id: UUID
    tenant_id: UUID
    user_id: UUID
    role: str
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AuthorizedTenantContext:
    tenant_id: UUID
    membership: TenantMembership
    permissions: frozenset[Permission]

    def permits(self, permission: Permission) -> bool:
        return permission in self.permissions


@dataclass(frozen=True, slots=True)
class TenantAccess:
    """A tenant the user may access, derived only from persisted active memberships."""

    tenant_id: UUID
    name: str
    slug: str
    role: TenantRole
    permissions: frozenset[Permission]
