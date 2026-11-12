from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.catalogs.read_models import Page
from app.domain.profiles.models import Profile, ProfileImport
from app.persistence.models import ProfileImportRecord, ProfileRecord


def _profile(session: Session, record: ProfileRecord) -> Profile:
    imports = session.scalars(
        select(ProfileImportRecord)
        .where(
            ProfileImportRecord.tenant_id == record.tenant_id,
            ProfileImportRecord.profile_id == record.id,
            ProfileImportRecord.active.is_(True),
        )
        .order_by(ProfileImportRecord.position)
    ).all()
    documents = record.document["profile"]["imports"]
    if len(imports) != len(documents) or [item.position for item in imports] != list(
        range(len(imports))
    ):
        raise RuntimeError("Profile import registry does not match document.")
    sources = []
    for item, document in zip(imports, documents, strict=True):
        href = (
            f"/api/v1/tenants/{record.tenant_id}/catalogs/{item.catalog_id}"
            f"/revisions/{item.revision_id}/export"
        )
        if document["href"] != href:
            raise RuntimeError("Profile import source does not match document.")
        ids = document["include-controls"][0]["with-ids"]
        sources.append(ProfileImport(item.id, item.catalog_id, item.revision_id, list(ids)))
    return Profile(
        record.id,
        record.tenant_id,
        sources,
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
                title=profile.title,
                document=profile.document,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
            )
        )
        self._session.flush()
        self._update_imports(profile)

    def get(self, tenant_id: UUID, profile_id: UUID) -> Profile | None:
        record = self._session.scalar(
            select(ProfileRecord)
            .where(
                ProfileRecord.tenant_id == tenant_id,
                ProfileRecord.id == profile_id,
            )
            .with_for_update(read=True)
        )
        return _profile(self._session, record) if record is not None else None

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
            .with_for_update(read=True)
        )
        return Page(
            [_profile(self._session, record) for record in records], total or 0, limit, offset
        )

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
        self._update_imports(profile)

    def _update_imports(self, profile: Profile) -> None:
        existing = {
            item.id: item
            for item in self._session.scalars(
                select(ProfileImportRecord).where(
                    ProfileImportRecord.tenant_id == profile.tenant_id,
                    ProfileImportRecord.profile_id == profile.id,
                )
            )
        }
        active = {item.id for item in profile.imports}
        for item in existing.values():
            if item.id not in active:
                item.active = False
        for position, source in enumerate(profile.imports):
            item = existing.get(source.id)
            if item is None:
                self._session.add(
                    ProfileImportRecord(
                        id=source.id,
                        tenant_id=profile.tenant_id,
                        profile_id=profile.id,
                        catalog_id=source.catalog_id,
                        revision_id=source.revision_id,
                        position=position,
                        active=True,
                    )
                )
            else:
                if (item.catalog_id, item.revision_id) != (source.catalog_id, source.revision_id):
                    raise ValueError("An existing profile import cannot change its source.")
                item.position = position
                item.active = True
