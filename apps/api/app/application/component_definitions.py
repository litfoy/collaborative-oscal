# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from collaborative_oscal_oscal.component_definition import (
    build_component_definition_document,
    component_definition_authoring_version,
)
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domain.catalogs.read_models import Page
from app.domain.component_definitions import (
    ComponentDefinition,
    ComponentRequirement,
    ReusableComponent,
)
from app.domain.errors import EntityNotFoundError
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogRevisionRecord,
    ComponentDefinitionComponentRecord,
    ComponentDefinitionRecord,
    ComponentDefinitionSourceRecord,
)

SessionScope = Callable[[], AbstractContextManager[Session]]


class InvalidComponentDefinition(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ComponentRequirementInput:
    catalog_id: UUID
    revision_id: UUID
    control_id: str
    description: str


@dataclass(frozen=True, slots=True)
class ComponentInput:
    id: UUID | None
    component_type: str
    title: str
    description: str
    requirements: Sequence[ComponentRequirementInput]


class ComponentDefinitionService:
    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    def create(
        self,
        tenant_id: UUID,
        actor: UUID,
        title: str,
        component_type: str,
        description: str,
        requirements: Sequence[ComponentRequirementInput],
    ) -> ComponentDefinition:
        now = datetime.now(UTC)
        document_id = uuid4()
        component_id = uuid4()
        component_uuid = uuid4()
        with self._session_scope() as session:
            self._lock_and_validate_sources(session, tenant_id, requirements)
            component_json, sources = self._build_component(
                tenant_id,
                component_uuid,
                ComponentInput(None, component_type, title, description, requirements),
                {},
            )
            document = build_component_definition_document(
                document_uuid=uuid4(),
                title=title,
                components=[component_json],
                last_modified=now,
                oscal_version=component_definition_authoring_version([component_type]),
            )
            record = ComponentDefinitionRecord(
                id=document_id,
                tenant_id=tenant_id,
                document=document,
                created_by=actor,
                updated_by=actor,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            component_record = ComponentDefinitionComponentRecord(
                id=component_id,
                tenant_id=tenant_id,
                document_id=document_id,
                oscal_component_uuid=component_uuid,
            )
            session.add(component_record)
            session.flush()
            session.add_all(
                self._source_records(
                    tenant_id, document_id, component_id, sources
                )
            )
            return self._to_domain(session, record)

    def get(self, tenant_id: UUID, document_id: UUID) -> ComponentDefinition:
        with self._session_scope() as session:
            record = self._get_record(session, tenant_id, document_id)
            return self._to_domain(session, record)

    def export(self, tenant_id: UUID, document_id: UUID) -> dict:
        with self._session_scope() as session:
            return self._get_record(session, tenant_id, document_id).document

    def list(self, tenant_id: UUID, *, limit: int, offset: int) -> Page[ComponentDefinition]:
        with self._session_scope() as session:
            total = (
                session.scalar(
                    select(func.count())
                    .select_from(ComponentDefinitionRecord)
                    .where(ComponentDefinitionRecord.tenant_id == tenant_id)
                )
                or 0
            )
            records = session.scalars(
                select(ComponentDefinitionRecord)
                .where(ComponentDefinitionRecord.tenant_id == tenant_id)
                .order_by(ComponentDefinitionRecord.updated_at.desc(), ComponentDefinitionRecord.id)
                .limit(limit)
                .offset(offset)
            ).all()
            return Page(
                [self._to_domain(session, record) for record in records],
                total,
                limit,
                offset,
            )

    def update(
        self,
        tenant_id: UUID,
        actor: UUID,
        document_id: UUID,
        title: str,
        components: Sequence[ComponentInput],
    ) -> ComponentDefinition:
        if not components or len(
            {component.id for component in components if component.id is not None}
        ) != sum(component.id is not None for component in components):
            raise InvalidComponentDefinition(
                "A document must contain uniquely identified components."
            )
        with self._session_scope() as session:
            record = self._get_record(session, tenant_id, document_id, lock=True)
            current = self._to_domain(session, record)
            current_by_id = {component.id: component for component in current.components}
            supplied_ids = {component.id for component in components if component.id is not None}
            if supplied_ids - current_by_id.keys():
                raise InvalidComponentDefinition(
                    "A component identity does not belong to this document."
                )
            all_requirements = [
                requirement for component in components for requirement in component.requirements
            ]
            self._lock_and_validate_sources(session, tenant_id, all_requirements)

            old_identity_records = {
                row.id: row
                for row in session.scalars(
                    select(ComponentDefinitionComponentRecord).where(
                        ComponentDefinitionComponentRecord.tenant_id == tenant_id,
                        ComponentDefinitionComponentRecord.document_id == document_id,
                    )
                )
            }
            generated: list[tuple[UUID, UUID, dict, list[tuple]]] = []
            for item in components:
                old_component = current_by_id.get(item.id) if item.id else None
                component_id = item.id or uuid4()
                component_uuid = (
                    old_component.oscal_uuid if old_component is not None else uuid4()
                )
                old_source_refs = self._old_source_refs(session, tenant_id, component_id)
                component_json, sources = self._build_component(
                    tenant_id, component_uuid, item, old_source_refs
                )
                generated.append((component_id, component_uuid, component_json, sources))

            old_json = record.document["component-definition"]
            component_jsons = [item[2] for item in generated]
            if title == old_json["metadata"]["title"] and component_jsons == old_json["components"]:
                return current

            now = datetime.now(UTC)
            document = build_component_definition_document(
                document_uuid=uuid4(),
                title=title,
                components=component_jsons,
                last_modified=_next_modified(old_json["metadata"]["last-modified"], now),
                version=_next_version(old_json["metadata"]["version"]),
                oscal_version=old_json["metadata"]["oscal-version"],
            )
            record.document = document
            record.updated_by = actor
            record.updated_at = now

            active_ids = {item[0] for item in generated}
            removed_ids = set(old_identity_records) - active_ids
            if removed_ids:
                session.execute(
                    delete(ComponentDefinitionComponentRecord).where(
                        ComponentDefinitionComponentRecord.tenant_id == tenant_id,
                        ComponentDefinitionComponentRecord.document_id == document_id,
                        ComponentDefinitionComponentRecord.id.in_(removed_ids),
                    )
                )
            session.flush()
            for component_id, component_uuid, _component_json, sources in generated:
                identity = old_identity_records.get(component_id)
                if identity is None:
                    session.add(
                        ComponentDefinitionComponentRecord(
                            id=component_id,
                            tenant_id=tenant_id,
                            document_id=document_id,
                            oscal_component_uuid=component_uuid,
                        )
                    )
                source_rows = self._source_records(
                    tenant_id, document_id, component_id, sources
                )
                session.execute(
                    delete(ComponentDefinitionSourceRecord).where(
                        ComponentDefinitionSourceRecord.tenant_id == tenant_id,
                        ComponentDefinitionSourceRecord.document_id == document_id,
                        ComponentDefinitionSourceRecord.component_id == component_id,
                    )
                )
                session.flush()
                session.add_all(source_rows)
            return self._to_domain(session, record)

    def delete_component(
        self, tenant_id: UUID, actor: UUID, document_id: UUID, component_id: UUID
    ) -> None:
        with self._session_scope() as session:
            record = self._get_record(session, tenant_id, document_id, lock=True)
            current = self._to_domain(session, record)
            component = next((item for item in current.components if item.id == component_id), None)
            if component is None:
                raise EntityNotFoundError("Component not found.")
            if len(current.components) == 1:
                session.delete(record)
                return
            remaining_json = [
                item
                for item in record.document["component-definition"]["components"]
                if UUID(item["uuid"]) != component.oscal_uuid
            ]
            now = datetime.now(UTC)
            body = record.document["component-definition"]
            record.document = build_component_definition_document(
                document_uuid=uuid4(),
                title=body["metadata"]["title"],
                components=remaining_json,
                last_modified=_next_modified(body["metadata"]["last-modified"], now),
                version=_next_version(body["metadata"]["version"]),
                oscal_version=body["metadata"]["oscal-version"],
            )
            record.updated_by = actor
            record.updated_at = now
            session.execute(
                delete(ComponentDefinitionComponentRecord).where(
                    ComponentDefinitionComponentRecord.tenant_id == tenant_id,
                    ComponentDefinitionComponentRecord.document_id == document_id,
                    ComponentDefinitionComponentRecord.id == component_id,
                )
            )

    def delete(self, tenant_id: UUID, document_id: UUID) -> None:
        with self._session_scope() as session:
            session.delete(self._get_record(session, tenant_id, document_id, lock=True))

    @staticmethod
    def _build_component(
        tenant_id: UUID,
        component_uuid: UUID,
        item: ComponentInput,
        old_source_refs: dict[tuple[UUID, UUID, str], tuple[UUID, UUID]],
    ) -> tuple[dict, list[tuple]]:
        grouped: dict[tuple[UUID, UUID], list[ComponentRequirementInput]] = defaultdict(list)
        seen: set[tuple[UUID, UUID, str]] = set()
        for requirement in item.requirements:
            key = (requirement.catalog_id, requirement.revision_id, requirement.control_id)
            if key in seen:
                raise InvalidComponentDefinition("A requirement may be associated only once.")
            if not requirement.description.strip():
                raise InvalidComponentDefinition(
                    "Describe how the component addresses each selected requirement."
                )
            seen.add(key)
            grouped[(requirement.catalog_id, requirement.revision_id)].append(requirement)

        control_implementations: list[dict] = []
        source_rows: list[tuple] = []
        old_set_ids = {
            source_key: value[0]
            for source_key, value in old_source_refs_by_source(old_source_refs).items()
        }
        for (catalog_id, revision_id), requirements in grouped.items():
            set_uuid = old_set_ids.get((catalog_id, revision_id), uuid4())
            implemented: list[dict] = []
            for requirement in requirements:
                old_ids = old_source_refs.get(
                    (catalog_id, revision_id, requirement.control_id)
                )
                requirement_uuid = old_ids[1] if old_ids else uuid4()
                implemented.append(
                    {
                        "uuid": str(requirement_uuid),
                        "control-id": requirement.control_id,
                        "description": requirement.description.strip(),
                    }
                )
                source_rows.append(
                    (
                        set_uuid,
                        requirement_uuid,
                        catalog_id,
                        revision_id,
                        requirement.control_id,
                    )
                )
            control_implementations.append(
                {
                    "uuid": str(set_uuid),
                    "source": _catalog_href(tenant_id, catalog_id, revision_id),
                    "description": "Guidance for the explicitly listed requirements.",
                    "implemented-requirements": implemented,
                }
            )
        return (
            {
                "uuid": str(component_uuid),
                "type": item.component_type,
                "title": item.title.strip(),
                "description": item.description,
                **(
                    {"control-implementations": control_implementations}
                    if control_implementations
                    else {}
                ),
            },
            source_rows,
        )

    @staticmethod
    def _lock_and_validate_sources(
        session: Session,
        tenant_id: UUID,
        requirements: Sequence[ComponentRequirementInput],
    ) -> None:
        source_keys = sorted(
            {(item.catalog_id, item.revision_id) for item in requirements},
            key=lambda item: (str(item[0]), str(item[1])),
        )
        for catalog_id, revision_id in source_keys:
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
        for (catalog_id, revision_id), controls in _group_control_ids(requirements).items():
            found = set(
                session.scalars(
                    select(CatalogControlIndexRecord.oscal_control_id).where(
                        CatalogControlIndexRecord.tenant_id == tenant_id,
                        CatalogControlIndexRecord.catalog_revision_id == revision_id,
                        CatalogControlIndexRecord.oscal_control_id.in_(controls),
                    )
                )
            )
            if found != controls:
                raise InvalidComponentDefinition(
                    "Selected controls do not exist in the referenced catalog revision."
                )

    @staticmethod
    def _old_source_refs(
        session: Session, tenant_id: UUID, component_id: UUID
    ) -> dict[tuple[UUID, UUID, str], tuple[UUID, UUID]]:
        rows = session.scalars(
            select(ComponentDefinitionSourceRecord).where(
                ComponentDefinitionSourceRecord.tenant_id == tenant_id,
                ComponentDefinitionSourceRecord.component_id == component_id,
            )
        )
        return {
            (row.catalog_id, row.revision_id, row.oscal_control_id): (
                row.control_implementation_uuid,
                row.implemented_requirement_uuid,
            )
            for row in rows
        }

    @staticmethod
    def _source_records(
        tenant_id: UUID, document_id: UUID, component_id: UUID, sources: Sequence[tuple]
    ) -> list[ComponentDefinitionSourceRecord]:
        return [
            ComponentDefinitionSourceRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                document_id=document_id,
                component_id=component_id,
                control_implementation_uuid=set_uuid,
                implemented_requirement_uuid=requirement_uuid,
                catalog_id=catalog_id,
                revision_id=revision_id,
                oscal_control_id=control_id,
            )
            for set_uuid, requirement_uuid, catalog_id, revision_id, control_id in sources
        ]

    @staticmethod
    def _get_record(
        session: Session, tenant_id: UUID, document_id: UUID, *, lock: bool = False
    ) -> ComponentDefinitionRecord:
        query = select(ComponentDefinitionRecord).where(
            ComponentDefinitionRecord.tenant_id == tenant_id,
            ComponentDefinitionRecord.id == document_id,
        )
        record = session.scalar(query.with_for_update() if lock else query)
        if record is None:
            raise EntityNotFoundError("Component Definition not found.")
        return record

    @staticmethod
    def _to_domain(session: Session, record: ComponentDefinitionRecord) -> ComponentDefinition:
        body = record.document["component-definition"]
        json_components = body.get("components", [])
        identities = session.scalars(
            select(ComponentDefinitionComponentRecord).where(
                ComponentDefinitionComponentRecord.tenant_id == record.tenant_id,
                ComponentDefinitionComponentRecord.document_id == record.id,
            )
        ).all()
        refs = session.scalars(
            select(ComponentDefinitionSourceRecord).where(
                ComponentDefinitionSourceRecord.tenant_id == record.tenant_id,
                ComponentDefinitionSourceRecord.document_id == record.id,
            )
        ).all()
        identities_by_uuid = {identity.oscal_component_uuid: identity for identity in identities}
        refs_by_requirement: dict[UUID, ComponentDefinitionSourceRecord] = {}
        for ref in refs:
            if ref.implemented_requirement_uuid in refs_by_requirement:
                raise RuntimeError(
                    "Component source registry does not match the OSCAL document."
                )
            refs_by_requirement[ref.implemented_requirement_uuid] = ref
        components: list[ReusableComponent] = []
        if (
            len(identities) != len(json_components)
            or len(identities_by_uuid) != len(identities)
        ):
            raise RuntimeError("Component identity registry does not match the OSCAL document.")
        used_refs: set[UUID] = set()
        for item in json_components:
            component_uuid = UUID(item["uuid"])
            identity = identities_by_uuid.get(component_uuid)
            if identity is None:
                raise RuntimeError("Component identity registry does not match the OSCAL document.")
            requirements = []
            for implementation in item.get("control-implementations", []):
                set_uuid = UUID(implementation["uuid"])
                for requirement in implementation["implemented-requirements"]:
                    requirement_uuid = UUID(requirement["uuid"])
                    ref = refs_by_requirement.get(requirement_uuid)
                    if (
                        ref is None
                        or ref.component_id != identity.id
                        or ref.control_implementation_uuid != set_uuid
                        or ref.oscal_control_id != requirement["control-id"]
                        or implementation["source"]
                        != _catalog_href(
                            record.tenant_id, ref.catalog_id, ref.revision_id
                        )
                    ):
                        raise RuntimeError(
                            "Component source registry does not match the OSCAL document."
                        )
                    used_refs.add(requirement_uuid)
                    requirements.append(
                        ComponentRequirement(
                            ref.catalog_id,
                            ref.revision_id,
                            ref.oscal_control_id,
                            requirement["description"],
                        )
                    )
            components.append(
                ReusableComponent(
                    identity.id,
                    component_uuid,
                    item["type"],
                    item["title"],
                    item["description"],
                    requirements,
                )
            )
        if len(used_refs) != len(refs):
            raise RuntimeError("Component source registry does not match the OSCAL document.")
        return ComponentDefinition(
            record.id,
            record.tenant_id,
            body["metadata"]["title"],
            UUID(body["uuid"]),
            body["metadata"]["oscal-version"],
            body["metadata"]["version"],
            components,
            record.created_by,
            record.updated_by,
            record.created_at,
            record.updated_at,
        )


def _catalog_href(tenant_id: UUID, catalog_id: UUID, revision_id: UUID) -> str:
    return (
        f"/api/v1/tenants/{tenant_id}/catalogs/{catalog_id}"
        f"/revisions/{revision_id}/export"
    )


def _group_control_ids(
    requirements: Sequence[ComponentRequirementInput],
) -> dict[tuple[UUID, UUID], set[str]]:
    grouped: dict[tuple[UUID, UUID], set[str]] = defaultdict(set)
    for requirement in requirements:
        grouped[(requirement.catalog_id, requirement.revision_id)].add(requirement.control_id)
    return grouped


def old_source_refs_by_source(
    old_refs: dict[tuple[UUID, UUID, str], tuple[UUID, UUID]],
) -> dict[tuple[UUID, UUID], tuple[UUID, dict[str, UUID]]]:
    grouped: dict[tuple[UUID, UUID], tuple[UUID, dict[str, UUID]]] = {}
    for (catalog_id, revision_id, control_id), (set_uuid, requirement_uuid) in old_refs.items():
        key = (catalog_id, revision_id)
        if key not in grouped:
            grouped[key] = (set_uuid, {})
        grouped[key][1][control_id] = requirement_uuid
    return grouped


def _next_modified(previous: str, now: datetime) -> datetime:
    previous_modified = datetime.fromisoformat(previous.replace("Z", "+00:00"))
    return max(now.replace(microsecond=0), previous_modified + timedelta(seconds=1))


def _next_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3:
        raise RuntimeError("Component Definition has an invalid document version.")
    try:
        major, minor, patch = (int(part) for part in parts)
    except ValueError as error:
        raise RuntimeError("Component Definition has an invalid document version.") from error
    return f"{major}.{minor}.{patch + 1}"
