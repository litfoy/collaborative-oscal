from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.authorization import AuthorizationService, permissions_for_role
from app.domain.identity.models import (
    MembershipStatus,
    Permission,
    TenantMembership,
    TenantRole,
)


class Memberships:
    def __init__(self) -> None:
        self.records: dict[tuple[object, object], TenantMembership] = {}

    def get_for_tenant_and_user(self, tenant_id, user_id):
        return self.records.get((tenant_id, user_id))

    def set(self, tenant_id, user_id, role, status=MembershipStatus.ACTIVE) -> None:
        now = datetime.now(UTC)
        self.records[(tenant_id, user_id)] = TenantMembership(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            status=status,
            created_at=now,
            updated_at=now,
        )


@pytest.fixture
def authorization():
    return AuthorizationService()


def test_active_membership_authorizes_only_its_tenant(authorization) -> None:
    user_id, tenant_a, tenant_b = uuid4(), uuid4(), uuid4()
    memberships = Memberships()
    memberships.set(tenant_a, user_id, TenantRole.VIEWER.value)

    allowed = authorization.resolve_tenant_context(
        memberships,
        tenant_id=tenant_a,
        user_id=user_id,
        required_permission=Permission.CATALOG_READ,
    )
    denied = authorization.resolve_tenant_context(
        memberships,
        tenant_id=tenant_b,
        user_id=user_id,
        required_permission=Permission.CATALOG_READ,
    )

    assert allowed is not None
    assert allowed.tenant_id == tenant_a
    assert denied is None


def test_membership_is_required_and_inactive_memberships_are_denied(authorization) -> None:
    user_id, tenant_id = uuid4(), uuid4()
    memberships = Memberships()

    assert (
        authorization.resolve_tenant_context(
            memberships,
            tenant_id=tenant_id,
            user_id=user_id,
            required_permission=Permission.TENANT_READ,
        )
        is None
    )

    memberships.set(
        tenant_id,
        user_id,
        TenantRole.TENANT_ADMIN.value,
        MembershipStatus.INACTIVE,
    )
    assert (
        authorization.resolve_tenant_context(
            memberships,
            tenant_id=tenant_id,
            user_id=user_id,
            required_permission=Permission.TENANT_READ,
        )
        is None
    )


def test_permissions_are_role_specific_and_default_to_deny() -> None:
    assert permissions_for_role(TenantRole.TENANT_ADMIN) == frozenset(Permission)
    assert Permission.CATALOG_WRITE in permissions_for_role(TenantRole.CATALOG_EDITOR)
    assert Permission.TENANT_MANAGE not in permissions_for_role(TenantRole.CATALOG_EDITOR)
    assert Permission.CATALOG_WRITE not in permissions_for_role(TenantRole.VIEWER)
    assert not permissions_for_role("future_unknown_role")


def test_permission_denial_and_role_changes_take_effect_immediately(authorization) -> None:
    user_id, tenant_id = uuid4(), uuid4()
    memberships = Memberships()
    memberships.set(tenant_id, user_id, TenantRole.VIEWER.value)

    assert (
        authorization.resolve_tenant_context(
            memberships,
            tenant_id=tenant_id,
            user_id=user_id,
            required_permission=Permission.CATALOG_WRITE,
        )
        is None
    )

    memberships.set(tenant_id, user_id, TenantRole.CATALOG_EDITOR.value)
    context = authorization.resolve_tenant_context(
        memberships,
        tenant_id=tenant_id,
        user_id=user_id,
        required_permission=Permission.CATALOG_WRITE,
    )

    assert context is not None
    assert context.permits(Permission.CATALOG_WRITE)


def test_tenant_role_changes_are_independent() -> None:
    user_id, tenant_a, tenant_b = uuid4(), uuid4(), uuid4()
    memberships = Memberships()
    memberships.set(tenant_a, user_id, TenantRole.TENANT_ADMIN.value)
    memberships.set(tenant_b, user_id, TenantRole.VIEWER.value)

    assert Permission.TENANT_MANAGE in permissions_for_role(
        memberships.get_for_tenant_and_user(tenant_a, user_id).role
    )
    assert Permission.TENANT_MANAGE not in permissions_for_role(
        memberships.get_for_tenant_and_user(tenant_b, user_id).role
    )
