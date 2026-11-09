from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.identity.models import MembershipStatus, TenantMembership, UserIdentity
from app.persistence.models import TenantMembershipRecord, UserIdentityRecord


def _identity(record: UserIdentityRecord) -> UserIdentity:
    return UserIdentity(
        id=record.id,
        issuer=record.issuer,
        subject=record.subject,
        display_name=record.display_name,
        email=record.email,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _membership(record: TenantMembershipRecord) -> TenantMembership:
    return TenantMembership(
        id=record.id,
        tenant_id=record.tenant_id,
        user_id=record.user_id,
        role=record.role,
        status=MembershipStatus(record.status),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class SQLIdentityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create(
        self,
        *,
        issuer: str,
        subject: str,
        display_name: str | None,
        email: str | None,
    ) -> UserIdentity:
        now = datetime.now(UTC)
        statement = insert(UserIdentityRecord).values(
            id=uuid4(),
            issuer=issuer,
            subject=subject,
            display_name=display_name,
            email=email,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_user_identities_issuer_subject",
            set_={
                "display_name": statement.excluded.display_name,
                "email": statement.excluded.email,
                "updated_at": now,
            },
        )
        self._session.execute(statement)
        record = self._session.scalar(
            select(UserIdentityRecord).where(
                UserIdentityRecord.issuer == issuer,
                UserIdentityRecord.subject == subject,
            )
        )
        if record is None:
            raise RuntimeError("Identity upsert did not return a persisted identity.")
        return _identity(record)


class SQLMembershipRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_tenant_and_user(self, tenant_id: UUID, user_id: UUID) -> TenantMembership | None:
        statement = select(TenantMembershipRecord).where(
            TenantMembershipRecord.tenant_id == tenant_id,
            TenantMembershipRecord.user_id == user_id,
        )
        record = self._session.scalar(statement)
        return _membership(record) if record is not None else None

    def assign(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role: str,
        status: str,
    ) -> TenantMembership:
        now = datetime.now(UTC)
        statement = insert(TenantMembershipRecord).values(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            status=status,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_tenant_memberships_tenant_user",
            set_={"role": role, "status": status, "updated_at": now},
        )
        self._session.execute(statement)
        record = self._session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.tenant_id == tenant_id,
                TenantMembershipRecord.user_id == user_id,
            )
        )
        if record is None:
            raise RuntimeError("Membership upsert did not return a persisted membership.")
        return _membership(record)
