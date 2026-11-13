from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.catalogs.read_models import Page
from app.domain.mappings import MappingCollection
from app.persistence.models import MappingCollectionRecord, MappingMemberRecord


def _collection(record: MappingCollectionRecord) -> MappingCollection:
    return MappingCollection(
        record.id,
        record.tenant_id,
        record.document,
        record.created_by,
        record.updated_by,
        record.created_at,
        record.updated_at,
    )


class SQLMappingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        collection: MappingCollection,
        members: list[MappingMemberRecord],
    ) -> None:
        self._session.add(
            MappingCollectionRecord(
                id=collection.id,
                tenant_id=collection.tenant_id,
                document=collection.document,
                created_by=collection.created_by,
                updated_by=collection.updated_by,
                created_at=collection.created_at,
                updated_at=collection.updated_at,
            )
        )
        self._session.flush()
        self._session.add_all(members)

    def get(
        self, tenant_id: UUID, collection_id: UUID, *, lock: bool = False
    ) -> MappingCollection | None:
        statement = select(MappingCollectionRecord).where(
            MappingCollectionRecord.tenant_id == tenant_id,
            MappingCollectionRecord.id == collection_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self._session.scalar(statement)
        return _collection(record) if record is not None else None

    def list_for_tenant(
        self, tenant_id: UUID, *, limit: int, offset: int
    ) -> Page[MappingCollection]:
        total = self._session.scalar(
            select(func.count())
            .select_from(MappingCollectionRecord)
            .where(MappingCollectionRecord.tenant_id == tenant_id)
        )
        records = self._session.scalars(
            select(MappingCollectionRecord)
            .where(MappingCollectionRecord.tenant_id == tenant_id)
            .order_by(MappingCollectionRecord.updated_at.desc(), MappingCollectionRecord.id)
            .limit(limit)
            .offset(offset)
        )
        return Page([_collection(record) for record in records], total or 0, limit, offset)

    def update(
        self,
        collection: MappingCollection,
        members: list[MappingMemberRecord],
    ) -> None:
        record = self._session.scalar(
            select(MappingCollectionRecord)
            .where(
                MappingCollectionRecord.tenant_id == collection.tenant_id,
                MappingCollectionRecord.id == collection.id,
            )
            .with_for_update()
        )
        if record is None:
            raise RuntimeError("Mapping collection disappeared during update.")
        record.document = collection.document
        record.updated_by = collection.updated_by
        record.updated_at = collection.updated_at
        self._session.query(MappingMemberRecord).filter_by(
            tenant_id=collection.tenant_id, collection_id=collection.id
        ).delete(synchronize_session=False)
        self._session.flush()
        self._session.add_all(members)

    def delete(self, tenant_id: UUID, collection_id: UUID) -> bool:
        record = self._session.scalar(
            select(MappingCollectionRecord)
            .where(
                MappingCollectionRecord.tenant_id == tenant_id,
                MappingCollectionRecord.id == collection_id,
            )
            .with_for_update()
        )
        if record is None:
            return False
        self._session.delete(record)
        return True

    def members_for_control(
        self,
        tenant_id: UUID,
        catalog_id: UUID,
        revision_id: UUID,
        control_id: str,
    ) -> list[MappingMemberRecord]:
        return list(
            self._session.scalars(
                select(MappingMemberRecord)
                .where(
                    MappingMemberRecord.tenant_id == tenant_id,
                    MappingMemberRecord.catalog_id == catalog_id,
                    MappingMemberRecord.revision_id == revision_id,
                    MappingMemberRecord.member_type == "control",
                    MappingMemberRecord.oscal_member_id == control_id,
                )
                .order_by(MappingMemberRecord.collection_id, MappingMemberRecord.entry_uuid)
            )
        )

    def members_for_entry(
        self,
        tenant_id: UUID,
        collection_id: UUID,
        mapping_uuid: UUID,
        entry_uuid: UUID,
    ) -> list[MappingMemberRecord]:
        return list(
            self._session.scalars(
                select(MappingMemberRecord)
                .where(
                    MappingMemberRecord.tenant_id == tenant_id,
                    MappingMemberRecord.collection_id == collection_id,
                    MappingMemberRecord.mapping_uuid == mapping_uuid,
                    MappingMemberRecord.entry_uuid == entry_uuid,
                )
                .order_by(MappingMemberRecord.side, MappingMemberRecord.oscal_member_id)
            )
        )


def new_member_record(
    *,
    tenant_id: UUID,
    collection_id: UUID,
    mapping_uuid: UUID,
    entry_uuid: UUID,
    side: str,
    catalog_id: UUID,
    revision_id: UUID,
    control_id: str,
) -> MappingMemberRecord:
    return MappingMemberRecord(
        id=uuid4(),
        tenant_id=tenant_id,
        collection_id=collection_id,
        mapping_uuid=mapping_uuid,
        entry_uuid=entry_uuid,
        side=side,
        member_type="control",
        catalog_id=catalog_id,
        revision_id=revision_id,
        oscal_member_id=control_id,
        control_id=control_id,
    )
