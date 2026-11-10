from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.catalogs.read_models import Page
from app.domain.profiles.models import Profile
from app.persistence.models import ProfileRecord


def _profile(record: ProfileRecord) -> Profile:
    return Profile(
        record.id,
        record.tenant_id,
        record.catalog_id,
        record.revision_id,
        record.title,
        record.document,
        record.created_at,
        record.updated_at,
    )


class SQLProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, profile: Profile) -> None:
        self._session.add(
            ProfileRecord(
                id=profile.id,
                tenant_id=profile.tenant_id,
                catalog_id=profile.catalog_id,
                revision_id=profile.revision_id,
                title=profile.title,
                document=profile.document,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
            )
        )

    def get(self, tenant_id: UUID, profile_id: UUID) -> Profile | None:
        record = self._session.scalar(
            select(ProfileRecord).where(
                ProfileRecord.tenant_id == tenant_id,
                ProfileRecord.id == profile_id,
            )
        )
        return _profile(record) if record is not None else None

    def list_for_tenant(self, tenant_id: UUID, *, limit: int, offset: int) -> Page[Profile]:
        total = self._session.scalar(
            select(func.count())
            .select_from(ProfileRecord)
            .where(ProfileRecord.tenant_id == tenant_id)
        )
        records = self._session.scalars(
            select(ProfileRecord)
            .where(ProfileRecord.tenant_id == tenant_id)
            .order_by(ProfileRecord.created_at.desc(), ProfileRecord.id)
            .limit(limit)
            .offset(offset)
        )
        return Page([_profile(record) for record in records], total or 0, limit, offset)

    def update(self, profile: Profile) -> None:
        record = self._session.scalar(
            select(ProfileRecord).where(
                ProfileRecord.tenant_id == profile.tenant_id,
                ProfileRecord.id == profile.id,
            )
        )
        if record is None:
            raise RuntimeError("Profile disappeared during update.")
        record.title = profile.title
        record.document = profile.document
        record.updated_at = profile.updated_at
