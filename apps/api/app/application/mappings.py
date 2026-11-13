from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from collaborative_oscal_oscal.mapping import (
    MATCHING_RATIONALES,
    RELATIONSHIP_TYPES,
    relationship_from_opposite_direction,
    validate_mapping_document,
)
from collaborative_oscal_oscal.versions import DEFAULT_MAPPING_OSCAL_VERSION
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.catalogs.read_models import Page
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import UserIdentity
from app.domain.mappings import MappingCollection, MappingPairSpec
from app.persistence.mapping_repository import SQLMappingRepository, new_member_record
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogRecord,
    CatalogRevisionRecord,
    MappingMemberRecord,
)

SessionScope = Callable[[], AbstractContextManager[Session]]


class InvalidMapping(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RelatedControl:
    catalog_id: UUID
    catalog_name: str
    revision_id: UUID
    revision_number: int
    control_id: str
    title: str


@dataclass(frozen=True, slots=True)
class RelatedMapping:
    collection_id: UUID
    collection_title: str
    mapping_uuid: UUID
    entry_uuid: UUID
    relationship: str
    matching_rationale: str
    matched_side: str
    sources: tuple[RelatedControl, ...]
    targets: tuple[RelatedControl, ...]


class MappingService:
    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    def create(
        self,
        tenant_id: UUID,
        actor: UserIdentity,
        title: str,
        description: str,
        pairs: Sequence[MappingPairSpec],
    ) -> MappingCollection:
        self._validate_specs(pairs)
        now = datetime.now(UTC)
        collection_id = uuid4()
        with self._session_scope() as session:
            self._validate_sources(session, tenant_id, pairs)
            document, members = self._build_document(
                tenant_id,
                collection_id,
                actor,
                title,
                description,
                pairs,
                now,
            )
            validate_mapping_document(document)
            collection = MappingCollection(
                collection_id,
                tenant_id,
                document,
                actor.id,
                actor.id,
                now,
                now,
            )
            SQLMappingRepository(session).add(collection, members)
        return collection

    def get(self, tenant_id: UUID, collection_id: UUID) -> MappingCollection:
        with self._session_scope() as session:
            collection = SQLMappingRepository(session).get(tenant_id, collection_id)
        if collection is None:
            raise EntityNotFoundError("Mapping collection not found.")
        return collection

    def list(self, tenant_id: UUID, *, limit: int, offset: int) -> Page[MappingCollection]:
        with self._session_scope() as session:
            return SQLMappingRepository(session).list_for_tenant(
                tenant_id, limit=limit, offset=offset
            )

    def update(
        self,
        tenant_id: UUID,
        collection_id: UUID,
        actor: UserIdentity,
        title: str,
        description: str,
        pairs: Sequence[MappingPairSpec],
    ) -> MappingCollection:
        self._validate_specs(pairs)
        with self._session_scope() as session:
            repository = SQLMappingRepository(session)
            existing = repository.get(tenant_id, collection_id, lock=True)
            if existing is None:
                raise EntityNotFoundError("Mapping collection not found.")
            old_pairs = _mapping_identities(existing.document, tenant_id)
            self._validate_stable_identities(pairs, old_pairs)
            self._validate_sources(session, tenant_id, pairs)
            now = datetime.now(UTC)
            document, members = self._build_document(
                tenant_id,
                collection_id,
                actor,
                title,
                description,
                pairs,
                now,
                previous=existing.document,
            )
            validate_mapping_document(document)
            updated = MappingCollection(
                existing.id,
                existing.tenant_id,
                document,
                existing.created_by,
                actor.id,
                existing.created_at,
                now,
            )
            repository.update(updated, members)
        return updated

    def delete(self, tenant_id: UUID, collection_id: UUID) -> None:
        with self._session_scope() as session:
            if not SQLMappingRepository(session).delete(tenant_id, collection_id):
                raise EntityNotFoundError("Mapping collection not found.")

    def related_controls(
        self,
        tenant_id: UUID,
        catalog_id: UUID,
        revision_id: UUID,
        control_id: str,
    ) -> list[RelatedMapping]:
        with self._session_scope() as session:
            repository = SQLMappingRepository(session)
            control_exists = session.scalar(
                select(CatalogControlIndexRecord.id).where(
                    CatalogControlIndexRecord.tenant_id == tenant_id,
                    CatalogControlIndexRecord.catalog_revision_id == revision_id,
                    CatalogControlIndexRecord.oscal_control_id == control_id,
                )
            )
            if (
                control_exists is None
                or session.scalar(
                    select(CatalogRevisionRecord.id).where(
                        CatalogRevisionRecord.tenant_id == tenant_id,
                        CatalogRevisionRecord.catalog_id == catalog_id,
                        CatalogRevisionRecord.id == revision_id,
                    )
                )
                is None
            ):
                raise EntityNotFoundError("Control not found in the catalog revision.")
            matches = repository.members_for_control(tenant_id, catalog_id, revision_id, control_id)
            results: list[RelatedMapping] = []
            seen: set[tuple[UUID, UUID, UUID]] = set()
            for matched in matches:
                key = (matched.collection_id, matched.mapping_uuid, matched.entry_uuid)
                if key in seen:
                    continue
                seen.add(key)
                collection = repository.get(tenant_id, matched.collection_id)
                if collection is None:
                    raise RuntimeError("Mapping member has no collection.")
                mapping = _find_mapping(collection.document, matched.mapping_uuid)
                entry = _find_entry(mapping, matched.entry_uuid)
                all_members = repository.members_for_entry(
                    tenant_id, matched.collection_id, matched.mapping_uuid, matched.entry_uuid
                )
                sources = self._control_details(
                    session, [m for m in all_members if m.side == "source"]
                )
                targets = self._control_details(
                    session, [m for m in all_members if m.side == "target"]
                )
                rationale = (
                    entry.get("matching-rationale")
                    or mapping.get("matching-rationale")
                    or collection.document["mapping-collection"]["provenance"]["matching-rationale"]
                )
                results.append(
                    RelatedMapping(
                        collection.id,
                        collection.document["mapping-collection"]["metadata"]["title"],
                        matched.mapping_uuid,
                        matched.entry_uuid,
                        relationship_from_opposite_direction(entry["relationship"])
                        if matched.side == "target"
                        else entry["relationship"],
                        rationale,
                        matched.side,
                        tuple(sources),
                        tuple(targets),
                    )
                )
            return results

    @staticmethod
    def _control_details(
        session: Session, members: Sequence[MappingMemberRecord]
    ) -> list[RelatedControl]:
        details: list[RelatedControl] = []
        for member in members:
            row = session.execute(
                select(
                    CatalogRecord.id,
                    CatalogRecord.name,
                    CatalogRevisionRecord.id,
                    CatalogRevisionRecord.revision_number,
                    CatalogControlIndexRecord.oscal_control_id,
                    CatalogControlIndexRecord.title,
                )
                .join(
                    CatalogRevisionRecord,
                    (CatalogRevisionRecord.tenant_id == CatalogRecord.tenant_id)
                    & (CatalogRevisionRecord.catalog_id == CatalogRecord.id),
                )
                .join(
                    CatalogControlIndexRecord,
                    (CatalogControlIndexRecord.tenant_id == CatalogRevisionRecord.tenant_id)
                    & (CatalogControlIndexRecord.catalog_revision_id == CatalogRevisionRecord.id),
                )
                .where(
                    CatalogRecord.tenant_id == member.tenant_id,
                    CatalogRecord.id == member.catalog_id,
                    CatalogRevisionRecord.id == member.revision_id,
                    CatalogControlIndexRecord.oscal_control_id == member.oscal_member_id,
                )
            ).one()
            details.append(RelatedControl(*row))
        return details

    @staticmethod
    def _validate_specs(pairs: Sequence[MappingPairSpec]) -> None:
        if not pairs or len(pairs) > 100:
            raise InvalidMapping("A collection must contain between 1 and 100 mappings.")
        mapping_ids: set[UUID] = set()
        entry_ids: set[UUID] = set()
        for pair in pairs:
            if pair.id is not None and pair.id in mapping_ids:
                raise InvalidMapping("Mapping identifiers must be unique.")
            if pair.id is not None:
                mapping_ids.add(pair.id)
            if not pair.entries or len(pair.entries) > 1000:
                raise InvalidMapping("Each mapping must contain between 1 and 1000 entries.")
            for entry in pair.entries:
                if entry.id is not None and entry.id in entry_ids:
                    raise InvalidMapping("Mapping entry identifiers must be unique.")
                if entry.id is not None:
                    entry_ids.add(entry.id)
                if entry.relationship not in RELATIONSHIP_TYPES:
                    raise InvalidMapping("Unsupported OSCAL mapping relationship.")
                if entry.matching_rationale not in MATCHING_RATIONALES:
                    raise InvalidMapping("Unsupported OSCAL matching rationale.")
                for values in (entry.sources, entry.targets):
                    if not values or len(values) > 1000:
                        raise InvalidMapping(
                            "Each source and target set must contain 1 to 1000 controls."
                        )
                    if len(values) != len(set(values)):
                        raise InvalidMapping("A mapping set cannot contain duplicate controls.")
                    if any(not value or len(value) > 255 for value in values):
                        raise InvalidMapping(
                            "Control identifiers must contain 1 to 255 characters."
                        )

    @staticmethod
    def _validate_sources(
        session: Session, tenant_id: UUID, pairs: Sequence[MappingPairSpec]
    ) -> None:
        revisions = {(pair.source_catalog_id, pair.source_revision_id) for pair in pairs} | {
            (pair.target_catalog_id, pair.target_revision_id) for pair in pairs
        }
        locked: dict[tuple[UUID, UUID], CatalogRevisionRecord] = {}
        for catalog_id, revision_id in sorted(
            revisions, key=lambda item: (str(item[1]), str(item[0]))
        ):
            revision = session.scalar(
                select(CatalogRevisionRecord)
                .where(
                    CatalogRevisionRecord.tenant_id == tenant_id,
                    CatalogRevisionRecord.catalog_id == catalog_id,
                    CatalogRevisionRecord.id == revision_id,
                )
                .with_for_update()
            )
            if revision is None:
                raise EntityNotFoundError("Catalog revision not found in this tenant.")
            locked[(catalog_id, revision_id)] = revision

        for pair in pairs:
            for revision_key, entries, side in (
                ((pair.source_catalog_id, pair.source_revision_id), pair.entries, "source"),
                ((pair.target_catalog_id, pair.target_revision_id), pair.entries, "target"),
            ):
                revision = locked[revision_key]
                control_ids = {
                    control_id
                    for entry in entries
                    for control_id in (entry.sources if side == "source" else entry.targets)
                }
                found = set(
                    session.scalars(
                        select(CatalogControlIndexRecord.oscal_control_id).where(
                            CatalogControlIndexRecord.tenant_id == tenant_id,
                            CatalogControlIndexRecord.catalog_revision_id == revision.id,
                            CatalogControlIndexRecord.oscal_control_id.in_(control_ids),
                        )
                    )
                )
                if missing := control_ids - found:
                    raise InvalidMapping(
                        f"{side.title()} controls do not exist in the referenced catalog revision: "
                        + ", ".join(sorted(missing))
                    )

    @staticmethod
    def _validate_stable_identities(
        pairs: Sequence[MappingPairSpec],
        old_pairs: dict[UUID, tuple[tuple[UUID, UUID], tuple[UUID, UUID], set[UUID]]],
    ) -> None:
        old_entries = {entry_id for _, _, entries in old_pairs.values() for entry_id in entries}
        old_entry_mapping = {
            entry_id: mapping_id
            for mapping_id, (_, _, entries) in old_pairs.items()
            for entry_id in entries
        }
        supplied_mapping_ids = {pair.id for pair in pairs if pair.id is not None}
        supplied_entry_ids = {
            entry.id for pair in pairs for entry in pair.entries if entry.id is not None
        }
        if supplied_mapping_ids - old_pairs.keys() or supplied_entry_ids - old_entries:
            raise InvalidMapping(
                "An existing mapping or entry identifier is not part of this collection."
            )
        for pair in pairs:
            for entry in pair.entries:
                if entry.id is not None and old_entry_mapping.get(entry.id) != pair.id:
                    raise InvalidMapping(
                        "An existing mapping entry cannot change its mapping identity."
                    )
            if pair.id is None:
                continue
            source, target, _ = old_pairs[pair.id]
            if source != (pair.source_catalog_id, pair.source_revision_id) or target != (
                pair.target_catalog_id,
                pair.target_revision_id,
            ):
                raise InvalidMapping(
                    "An existing mapping cannot change its source or target revision."
                )

    @staticmethod
    def _build_document(
        tenant_id: UUID,
        collection_id: UUID,
        actor: UserIdentity,
        title: str,
        description: str,
        pairs: Sequence[MappingPairSpec],
        now: datetime,
        *,
        previous: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[MappingMemberRecord]]:
        modified = now.isoformat().replace("+00:00", "Z")
        previous_collection = previous.get("mapping-collection", {}) if previous else {}
        previous_metadata = previous_collection.get("metadata", {})
        mapping_documents: list[dict[str, Any]] = []
        members: list[MappingMemberRecord] = []
        for pair in pairs:
            mapping_uuid = pair.id or uuid4()
            maps: list[dict[str, Any]] = []
            for spec in pair.entries:
                entry_uuid = spec.id or uuid4()
                sources = [{"type": "control", "id-ref": control_id} for control_id in spec.sources]
                targets = [{"type": "control", "id-ref": control_id} for control_id in spec.targets]
                maps.append(
                    {
                        "uuid": str(entry_uuid),
                        "matching-rationale": spec.matching_rationale,
                        "relationship": spec.relationship,
                        "sources": sources,
                        "targets": targets,
                        **({"remarks": spec.justification} if spec.justification else {}),
                    }
                )
                for side, catalog_id, revision_id, control_ids in (
                    ("source", pair.source_catalog_id, pair.source_revision_id, spec.sources),
                    ("target", pair.target_catalog_id, pair.target_revision_id, spec.targets),
                ):
                    members.extend(
                        new_member_record(
                            tenant_id=tenant_id,
                            collection_id=collection_id,
                            mapping_uuid=mapping_uuid,
                            entry_uuid=entry_uuid,
                            side=side,
                            catalog_id=catalog_id,
                            revision_id=revision_id,
                            control_id=control_id,
                        )
                        for control_id in control_ids
                    )
            mapping_documents.append(
                {
                    "uuid": str(mapping_uuid),
                    "method": "human",
                    "status": "draft",
                    "source-resource": {
                        "type": "catalog",
                        "href": _catalog_href(
                            tenant_id, pair.source_catalog_id, pair.source_revision_id
                        ),
                    },
                    "target-resource": {
                        "type": "catalog",
                        "href": _catalog_href(
                            tenant_id, pair.target_catalog_id, pair.target_revision_id
                        ),
                    },
                    "mapping-description": description or title,
                    "maps": maps,
                }
            )
        first_rationale = pairs[0].entries[0].matching_rationale
        metadata: dict[str, Any] = {
            "title": title,
            "last-modified": modified,
            "version": _next_document_version(previous_metadata.get("version")),
            "oscal-version": DEFAULT_MAPPING_OSCAL_VERSION,
            "roles": [{"id": "creator", "title": "Creator"}],
            "parties": [
                {
                    "uuid": str(actor.id),
                    "type": "person",
                    "name": actor.display_name or "Authenticated user",
                }
            ],
            "responsible-parties": [{"role-id": "creator", "party-uuids": [str(actor.id)]}],
        }
        if previous_metadata.get("published"):
            metadata["published"] = previous_metadata["published"]
        provenance: dict[str, Any] = {
            "method": "human",
            "matching-rationale": first_rationale,
            "status": "draft",
            "mapping-description": description or title,
        }
        document = {
            "mapping-collection": {
                "uuid": str(uuid4()),
                "metadata": metadata,
                "provenance": provenance,
                "mappings": mapping_documents,
            }
        }
        return document, members


def _catalog_href(tenant_id: UUID, catalog_id: UUID, revision_id: UUID) -> str:
    return f"/api/v1/tenants/{tenant_id}/catalogs/{catalog_id}/revisions/{revision_id}/export"


def _next_document_version(version: str | None) -> str:
    if version is None:
        return "1.0.0"
    try:
        major, minor, patch = (int(value) for value in version.split("."))
    except (ValueError, AttributeError) as error:
        raise RuntimeError("Mapping collection has an invalid document version.") from error
    return f"{major}.{minor}.{patch + 1}"


def _mapping_identities(
    document: dict[str, Any], tenant_id: UUID
) -> dict[UUID, tuple[tuple[UUID, UUID], tuple[UUID, UUID], set[UUID]]]:
    mappings = document["mapping-collection"]["mappings"]
    if isinstance(mappings, dict):
        mappings = [mappings]
    result = {}
    for mapping in mappings:
        mapping_uuid = UUID(mapping["uuid"])
        source = _catalog_revision_from_href(mapping["source-resource"]["href"], tenant_id)
        target = _catalog_revision_from_href(mapping["target-resource"]["href"], tenant_id)
        maps = mapping["maps"] if isinstance(mapping["maps"], list) else [mapping["maps"]]
        result[mapping_uuid] = (
            source,
            target,
            {UUID(entry["uuid"]) for entry in maps},
        )
    return result


def _catalog_revision_from_href(href: str, expected_tenant_id: UUID) -> tuple[UUID, UUID]:
    try:
        parts = href.strip("/").split("/")
        if len(parts) != 9 or parts[0:3] != ["api", "v1", "tenants"]:
            raise ValueError
        tenant_id, catalog_id, revision_id = UUID(parts[3]), UUID(parts[5]), UUID(parts[7])
        if (
            tenant_id != expected_tenant_id
            or parts[4] != "catalogs"
            or parts[6] != "revisions"
            or parts[8] != "export"
        ):
            raise ValueError
        return catalog_id, revision_id
    except (IndexError, ValueError) as error:
        raise RuntimeError(
            "Mapping resource reference does not match the stored revision."
        ) from error


def _find_mapping(document: dict[str, Any], mapping_uuid: UUID) -> dict[str, Any]:
    mappings = document["mapping-collection"]["mappings"]
    if isinstance(mappings, dict):
        mappings = [mappings]
    for mapping in mappings:
        if UUID(mapping["uuid"]) == mapping_uuid:
            return mapping
    raise RuntimeError("Mapping member is missing from its OSCAL document.")


def _find_entry(mapping: dict[str, Any], entry_uuid: UUID) -> dict[str, Any]:
    entries = mapping["maps"]
    if isinstance(entries, dict):
        entries = [entries]
    for entry in entries:
        if UUID(entry["uuid"]) == entry_uuid:
            return entry
    raise RuntimeError("Mapping member entry is missing from its OSCAL document.")
