from typing import Protocol
from uuid import UUID

from app.domain.identity.models import (
    AuthorizedTenantContext,
    MembershipStatus,
    Permission,
    TenantMembership,
    TenantRole,
)

ROLE_PERMISSIONS: dict[TenantRole, frozenset[Permission]] = {
    TenantRole.TENANT_ADMIN: frozenset(Permission),
    TenantRole.CATALOG_EDITOR: frozenset(
        {
            Permission.TENANT_READ,
            Permission.CATALOG_READ,
            Permission.CATALOG_WRITE,
            Permission.CATALOG_IMPORT,
        }
    ),
    TenantRole.VIEWER: frozenset({Permission.TENANT_READ, Permission.CATALOG_READ}),
}


class MembershipLookup(Protocol):
    def get_for_tenant_and_user(
        self, tenant_id: UUID, user_id: UUID
    ) -> TenantMembership | None: ...


def permissions_for_role(role: TenantRole | str) -> frozenset[Permission]:
    try:
        return ROLE_PERMISSIONS.get(TenantRole(role), frozenset())
    except ValueError:
        return frozenset()


class AuthorizationService:
    def resolve_tenant_context(
        self,
        memberships: MembershipLookup,
        *,
        tenant_id: UUID,
        user_id: UUID,
        required_permission: Permission,
    ) -> AuthorizedTenantContext | None:
        membership = memberships.get_for_tenant_and_user(tenant_id, user_id)
        if membership is None or membership.status is not MembershipStatus.ACTIVE:
            return None

        permissions = permissions_for_role(membership.role)
        if required_permission not in permissions:
            return None

        return AuthorizedTenantContext(tenant_id, membership, permissions)
