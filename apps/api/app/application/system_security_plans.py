from __future__ import annotations

import copy
from collections import defaultdict
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4, uuid5

from collaborative_oscal_oscal.catalog_index import canonical_json_sha256
from collaborative_oscal_oscal.system_security_plan import (
    SystemSecurityPlanValidationError,
    serialize_authored_system_security_plan,
    validate_system_security_plan_document,
)
from collaborative_oscal_oscal.versions import (
    OscalDocumentModel,
    authoring_version_for_component_types,
)
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.domain.errors import EntityNotFoundError
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogRevisionRecord,
    ComponentDefinitionComponentRecord,
    ComponentDefinitionRecord,
    ComponentDefinitionSnapshotRecord,
    ControlImplementationRecord,
    ImplementationResponsibilityRecord,
    InformationSystemRecord,
    OrganizationRecord,
    SystemComponentRecord,
    SystemSecurityPlanImplementationRecord,
    SystemSecurityPlanRecord,
    SystemSecurityPlanVersionRecord,
)

SessionScope = Callable[[], AbstractContextManager[Session]]

_SYSTEM_STATUSES = {
    "operational",
    "under-development",
    "under-major-modification",
    "disposition",
    "other",
}
_COMPONENT_STATUSES = {"operational", "under-development", "disposition", "other"}
_IMPLEMENTATION_EXPLANATION_STATES = {"planned", "alternative", "not-applicable"}
_VERSION_NAMESPACE = UUID("a3041081-fc77-4fc7-a843-1cf3a5b784bc")


class InvalidSystemSecurityPlan(ValueError):
    def __init__(self, diagnostics: list[dict[str, str]]) -> None:
        self.diagnostics = diagnostics
        super().__init__("The SSP working state is not ready to create a valid OSCAL version.")


class StaleSystemSecurityPlanUpdate(ValueError):
    def __init__(self, plan_id: UUID, expected_version: int, current_version: int) -> None:
        self.plan_id = plan_id
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__("The System Security Plan changed after it was loaded.")


class _StaleSystemSecurityPlanFlush(RuntimeError):
    def __init__(self, plan_id: UUID, expected_version: int) -> None:
        self.plan_id = plan_id
        self.expected_version = expected_version
        super().__init__("System Security Plan flush detected stale mapper version.")


class SystemSecurityPlanService:
    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    def list_systems(self, tenant_id: UUID) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            systems = session.scalars(
                select(InformationSystemRecord)
                .where(InformationSystemRecord.tenant_id == tenant_id)
                .order_by(InformationSystemRecord.name, InformationSystemRecord.id)
            ).all()
            return [self._system_payload(system) for system in systems]

    def get_system(self, tenant_id: UUID, system_id: UUID) -> dict[str, Any]:
        with self._session_scope() as session:
            return self._system_payload(self._get_system(session, tenant_id, system_id))

    def create_system(
        self,
        tenant_id: UUID,
        actor: UUID,
        *,
        name: str,
        organization_id: UUID | None,
        description: str | None,
        system_boundary: str | None,
        system_ids: list[dict[str, Any]],
        information_types: list[dict[str, Any]],
        operational_status: str | None,
        status_remarks: str | None,
        security_sensitivity_level: str | None,
    ) -> dict[str, Any]:
        self._validate_system_fields(
            name, operational_status, status_remarks, system_ids, information_types
        )
        with self._session_scope() as session:
            if (
                organization_id is not None
                and session.scalar(
                    select(OrganizationRecord.id).where(
                        OrganizationRecord.tenant_id == tenant_id,
                        OrganizationRecord.id == organization_id,
                    )
                )
                is None
            ):
                raise EntityNotFoundError("Organization not found.")
            now = datetime.now(UTC)
            system = InformationSystemRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                organization_id=organization_id,
                name=name.strip(),
                description=description,
                system_boundary=system_boundary,
                system_ids=self._normalize_system_ids(system_ids),
                information_types=self._normalize_information_types(information_types),
                operational_status=operational_status,
                status_remarks=status_remarks,
                security_sensitivity_level=security_sensitivity_level,
                created_by=actor,
                updated_by=actor,
                created_at=now,
                updated_at=now,
            )
            session.add(system)
            session.flush()
            return self._system_payload(system)

    def update_system(
        self,
        tenant_id: UUID,
        actor: UUID,
        system_id: UUID,
        *,
        name: str,
        description: str | None,
        system_boundary: str | None,
        system_ids: list[dict[str, Any]],
        information_types: list[dict[str, Any]],
        operational_status: str | None,
        status_remarks: str | None,
        security_sensitivity_level: str | None,
    ) -> dict[str, Any]:
        self._validate_system_fields(
            name, operational_status, status_remarks, system_ids, information_types
        )
        with self._session_scope() as session:
            system = self._get_system(session, tenant_id, system_id, lock=True)
            system.name = name.strip()
            system.description = description
            system.system_boundary = system_boundary
            system.system_ids = self._normalize_system_ids(system_ids)
            system.information_types = self._normalize_information_types(
                information_types, system.information_types
            )
            system.operational_status = operational_status
            system.status_remarks = status_remarks
            system.security_sensitivity_level = security_sensitivity_level
            system.updated_by = actor
            system.updated_at = datetime.now(UTC)
            session.flush()
            return self._system_payload(system)

    def list_components(self, tenant_id: UUID, system_id: UUID) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            self._get_system(session, tenant_id, system_id)
            components = session.scalars(
                select(SystemComponentRecord)
                .where(
                    SystemComponentRecord.tenant_id == tenant_id,
                    SystemComponentRecord.system_id == system_id,
                )
                .order_by(SystemComponentRecord.created_at, SystemComponentRecord.id)
            ).all()
            return [self._component_payload(component) for component in components]

    def create_component(
        self,
        tenant_id: UUID,
        actor: UUID,
        system_id: UUID,
        *,
        component_type: str,
        title: str,
        description: str,
        purpose: str | None,
        status: str,
        status_remarks: str | None,
        is_system_component: bool = False,
    ) -> dict[str, Any]:
        self._validate_component_fields(title, description, status, status_remarks)
        if is_system_component and component_type != "this-system":
            raise InvalidSystemSecurityPlan(
                [
                    {
                        "code": "invalid_system_component",
                        "message": "System-wide components must use OSCAL type 'this-system'.",
                    }
                ]
            )
        if not is_system_component and component_type == "this-system":
            raise InvalidSystemSecurityPlan(
                [
                    {
                        "code": "invalid_system_component",
                        "message": (
                            "The 'this-system' type is reserved for explicit "
                            "system-wide contributions."
                        ),
                    }
                ]
            )
        with self._session_scope() as session:
            self._get_system(session, tenant_id, system_id)
            if (
                is_system_component
                and session.scalar(
                    select(SystemComponentRecord.id).where(
                        SystemComponentRecord.tenant_id == tenant_id,
                        SystemComponentRecord.system_id == system_id,
                        SystemComponentRecord.is_system_component.is_(True),
                    )
                )
                is not None
            ):
                raise InvalidSystemSecurityPlan(
                    [
                        {
                            "code": "system_component_exists",
                            "message": "This System already has its stable this-system component.",
                        }
                    ]
                )
            now = datetime.now(UTC)
            component = {
                "uuid": str(uuid4()),
                "type": component_type,
                "title": title.strip(),
                "description": description.strip(),
                "status": self._oscal_status(status, status_remarks),
            }
            if purpose:
                component["purpose"] = purpose
            record = SystemComponentRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                system_id=system_id,
                oscal_component_uuid=UUID(component["uuid"]),
                source_snapshot_id=None,
                source_component_uuid=None,
                is_system_component=is_system_component,
                component=component,
                created_by=actor,
                updated_by=actor,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            return self._component_payload(record)

    def update_component(
        self,
        tenant_id: UUID,
        actor: UUID,
        system_id: UUID,
        component_id: UUID,
        *,
        title: str,
        description: str,
        purpose: str | None,
        status: str,
        status_remarks: str | None,
    ) -> dict[str, Any]:
        self._validate_component_fields(title, description, status, status_remarks)
        with self._session_scope() as session:
            component = session.scalar(
                select(SystemComponentRecord)
                .where(
                    SystemComponentRecord.tenant_id == tenant_id,
                    SystemComponentRecord.system_id == system_id,
                    SystemComponentRecord.id == component_id,
                )
                .with_for_update()
            )
            if component is None:
                raise EntityNotFoundError("System component not found.")
            actual = copy.deepcopy(component.component)
            actual["title"] = title.strip()
            actual["description"] = description.strip()
            actual["status"] = self._oscal_status(status, status_remarks)
            actual.pop("purpose", None)
            if purpose:
                actual["purpose"] = purpose
            component.component = actual
            component.updated_by = actor
            component.updated_at = datetime.now(UTC)
            session.flush()
            return self._component_payload(component)

    def adopt_component_definition(
        self,
        tenant_id: UUID,
        actor: UUID,
        system_id: UUID,
        source_document_id: UUID,
        source_component_id: UUID,
        *,
        title: str,
        description: str,
        purpose: str | None,
        status: str,
        status_remarks: str | None,
    ) -> dict[str, Any]:
        self._validate_component_fields(title, description, status, status_remarks)
        with self._session_scope() as session:
            self._get_system(session, tenant_id, system_id)
            source = session.scalar(
                select(ComponentDefinitionRecord)
                .where(
                    ComponentDefinitionRecord.tenant_id == tenant_id,
                    ComponentDefinitionRecord.id == source_document_id,
                )
                .with_for_update()
            )
            if source is None:
                raise EntityNotFoundError("Component Definition not found.")
            source_component = session.scalar(
                select(ComponentDefinitionComponentRecord).where(
                    ComponentDefinitionComponentRecord.tenant_id == tenant_id,
                    ComponentDefinitionComponentRecord.document_id == source_document_id,
                    ComponentDefinitionComponentRecord.id == source_component_id,
                )
            )
            if source_component is None:
                raise EntityNotFoundError("Component Definition component not found.")
            source_document = copy.deepcopy(source.document)
            source_body = source_document["component-definition"]
            matching = [
                component
                for component in source_body["components"]
                if UUID(component["uuid"]) == source_component.oscal_component_uuid
            ]
            if len(matching) != 1:
                raise EntityNotFoundError("Component Definition component not found.")
            now = datetime.now(UTC)
            digest = canonical_json_sha256(source_document)
            snapshot_id = uuid4()
            session.execute(
                insert(ComponentDefinitionSnapshotRecord)
                .values(
                    id=snapshot_id,
                    tenant_id=tenant_id,
                    source_document_uuid=UUID(source_body["uuid"]),
                    content_sha256=digest,
                    document=source_document,
                    diagnostics=[],
                    created_at=now,
                )
                .on_conflict_do_nothing(constraint="uq_component_definition_snapshots_digest")
            )
            snapshot = session.scalar(
                select(ComponentDefinitionSnapshotRecord).where(
                    ComponentDefinitionSnapshotRecord.tenant_id == tenant_id,
                    ComponentDefinitionSnapshotRecord.content_sha256 == digest,
                )
            )
            if snapshot is None:
                raise RuntimeError("The immutable Component Definition snapshot was not persisted.")
            adopted = matching[0]
            component = {
                "uuid": str(uuid4()),
                "type": adopted["type"],
                "title": title.strip(),
                "description": description.strip(),
                "status": self._oscal_status(status, status_remarks),
                "links": [
                    {
                        "href": (
                            f"/api/v1/tenants/{tenant_id}/component-definition-snapshots/"
                            f"{snapshot.id}/components/{source_component_id}/export"
                        ),
                        "rel": "imported-from",
                    }
                ],
            }
            if purpose:
                component["purpose"] = purpose
            record = SystemComponentRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                system_id=system_id,
                oscal_component_uuid=UUID(component["uuid"]),
                source_snapshot_id=snapshot.id,
                source_component_uuid=source_component.oscal_component_uuid,
                is_system_component=False,
                component=component,
                created_by=actor,
                updated_by=actor,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            return self._component_payload(record)

    def export_adopted_component(
        self,
        tenant_id: UUID,
        snapshot_id: UUID,
        component_id: UUID,
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            snapshot = session.scalar(
                select(ComponentDefinitionSnapshotRecord).where(
                    ComponentDefinitionSnapshotRecord.tenant_id == tenant_id,
                    ComponentDefinitionSnapshotRecord.id == snapshot_id,
                )
            )
            if snapshot is None:
                raise EntityNotFoundError("Component Definition snapshot not found.")
            body = snapshot.document["component-definition"]
            component = next(
                (value for value in body["components"] if UUID(value["uuid"]) == component_id),
                None,
            )
            if component is None:
                raise EntityNotFoundError("Component Definition component snapshot not found.")
            return {"component-definition": {**body, "components": [component]}}

    def list_plans(self, tenant_id: UUID, system_id: UUID) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            self._get_system(session, tenant_id, system_id)
            plans = session.scalars(
                select(SystemSecurityPlanRecord)
                .where(
                    SystemSecurityPlanRecord.tenant_id == tenant_id,
                    SystemSecurityPlanRecord.system_id == system_id,
                )
                .order_by(SystemSecurityPlanRecord.created_at, SystemSecurityPlanRecord.id)
            ).all()
            return [self._plan_payload(session, plan) for plan in plans]

    def get_plan(self, tenant_id: UUID, plan_id: UUID) -> dict[str, Any]:
        with self._session_scope() as session:
            return self._plan_payload(session, self._get_plan(session, tenant_id, plan_id))

    def create_plan(
        self,
        tenant_id: UUID,
        actor: UUID,
        system_id: UUID,
        *,
        catalog_id: UUID,
        revision_id: UUID,
        title: str,
        control_implementation_description: str | None,
    ) -> dict[str, Any]:
        if not title.strip():
            raise InvalidSystemSecurityPlan(
                [{"code": "missing_title", "message": "An SSP title is required."}]
            )
        with self._session_scope() as session:
            self._get_system(session, tenant_id, system_id)
            revision = self._get_revision(session, tenant_id, catalog_id, revision_id, lock=True)
            now = datetime.now(UTC)
            plan = SystemSecurityPlanRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                system_id=system_id,
                catalog_id=catalog_id,
                revision_id=revision_id,
                title=title.strip(),
                control_implementation_description=control_implementation_description,
                created_by=actor,
                updated_by=actor,
                created_at=now,
                updated_at=now,
                concurrency_version=1,
            )
            session.add(plan)
            session.flush()
            return self._plan_payload(session, plan, revision=revision)

    def update_plan(
        self,
        tenant_id: UUID,
        actor: UUID,
        plan_id: UUID,
        *,
        expected_version: int,
        title: str,
        control_implementation_description: str | None,
    ) -> dict[str, Any]:
        if not title.strip():
            raise InvalidSystemSecurityPlan(
                [{"code": "missing_title", "message": "An SSP title is required."}]
            )
        try:
            with self._session_scope() as session:
                plan = self._get_plan(session, tenant_id, plan_id, lock=True)
                if plan.concurrency_version != expected_version:
                    raise StaleSystemSecurityPlanUpdate(
                        plan.id, expected_version, plan.concurrency_version
                    )
                plan.title = title.strip()
                plan.control_implementation_description = control_implementation_description
                plan.updated_by = actor
                plan.updated_at = datetime.now(UTC)
                try:
                    session.flush()
                except StaleDataError as error:
                    raise _StaleSystemSecurityPlanFlush(plan_id, expected_version) from error
                return self._plan_payload(session, plan)
        except _StaleSystemSecurityPlanFlush as stale:
            current = self._current_plan_version(tenant_id, stale.plan_id)
            raise StaleSystemSecurityPlanUpdate(
                stale.plan_id,
                stale.expected_version,
                current,
            ) from stale.__cause__

    def associate_implementation(
        self,
        tenant_id: UUID,
        actor: UUID,
        plan_id: UUID,
        implementation_id: UUID,
        system_component_id: UUID,
        *,
        expected_version: int,
    ) -> dict[str, Any]:
        try:
            with self._session_scope() as session:
                plan = self._get_plan(session, tenant_id, plan_id, lock=True)
                if plan.concurrency_version != expected_version:
                    raise StaleSystemSecurityPlanUpdate(
                        plan.id, expected_version, plan.concurrency_version
                    )
                system = self._get_system(session, tenant_id, plan.system_id, lock=True)
                record = session.scalar(
                    select(ControlImplementationRecord)
                    .where(
                        ControlImplementationRecord.tenant_id == tenant_id,
                        ControlImplementationRecord.id == implementation_id,
                    )
                    .with_for_update()
                )
                if record is None:
                    raise EntityNotFoundError("Implementation not found.")
                component = session.scalar(
                    select(SystemComponentRecord).where(
                        SystemComponentRecord.tenant_id == tenant_id,
                        SystemComponentRecord.system_id == plan.system_id,
                        SystemComponentRecord.id == system_component_id,
                    )
                )
                if component is None:
                    raise EntityNotFoundError("System component not found.")
                if record.catalog_id != plan.catalog_id or record.revision_id != plan.revision_id:
                    raise InvalidSystemSecurityPlan(
                        [
                            {
                                "code": "baseline_mismatch",
                                "message": (
                                    "The implementation must reference this SSP's exact "
                                    "Catalog revision."
                                ),
                            }
                        ]
                    )
                if record.system_id not in {None, plan.system_id}:
                    raise InvalidSystemSecurityPlan(
                        [
                            {
                                "code": "system_mismatch",
                                "message": (
                                    "The implementation is already assigned to another "
                                    "System."
                                ),
                            }
                        ]
                    )
                if record.system_component_id not in {None, system_component_id}:
                    raise InvalidSystemSecurityPlan(
                        [
                            {
                                "code": "component_mismatch",
                                "message": (
                                    "The implementation is already assigned to another component. "
                                    "Update its context explicitly before including it."
                                ),
                            }
                        ]
                    )
                if (
                    record.organization_id is not None
                    and record.organization_id != system.organization_id
                ):
                    raise InvalidSystemSecurityPlan(
                        [
                            {
                                "code": "organization_mismatch",
                                "message": (
                                    "The implementation's organization scope is incompatible "
                                    "with this System."
                                ),
                            }
                        ]
                    )
                existing = session.scalar(
                    select(SystemSecurityPlanImplementationRecord.id).where(
                        SystemSecurityPlanImplementationRecord.tenant_id == tenant_id,
                        SystemSecurityPlanImplementationRecord.system_security_plan_id == plan_id,
                        (
                            SystemSecurityPlanImplementationRecord.implementation_id
                            == implementation_id
                        ),
                    )
                )
                if existing is not None:
                    raise InvalidSystemSecurityPlan(
                        [
                            {
                                "code": "already_included",
                                "message": (
                                    "This implementation is already explicitly included in the SSP."
                                ),
                            }
                        ]
                    )
                now = datetime.now(UTC)
                record.system_id = plan.system_id
                record.system_component_id = system_component_id
                record.updated_by = actor
                record.updated_at = now
                association = SystemSecurityPlanImplementationRecord(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    system_security_plan_id=plan_id,
                    implementation_id=record.id,
                    system_id=plan.system_id,
                    system_component_id=system_component_id,
                    catalog_id=record.catalog_id,
                    revision_id=record.revision_id,
                    oscal_control_id=record.oscal_control_id,
                    created_at=now,
                )
                session.add(association)
                plan.updated_by = actor
                plan.updated_at = now
                try:
                    session.flush()
                except StaleDataError as error:
                    raise _StaleSystemSecurityPlanFlush(plan_id, expected_version) from error
                return {
                    "implementation_id": record.id,
                    "system_component_id": system_component_id,
                    "oscal_control_id": record.oscal_control_id,
                    "concurrency_version": plan.concurrency_version,
                }
        except _StaleSystemSecurityPlanFlush as stale:
            current = self._current_plan_version(tenant_id, stale.plan_id)
            raise StaleSystemSecurityPlanUpdate(
                stale.plan_id,
                stale.expected_version,
                current,
            ) from stale.__cause__

    def remove_implementation(
        self,
        tenant_id: UUID,
        actor: UUID,
        plan_id: UUID,
        implementation_id: UUID,
        *,
        expected_version: int,
    ) -> dict[str, int]:
        try:
            with self._session_scope() as session:
                plan = self._get_plan(session, tenant_id, plan_id, lock=True)
                if plan.concurrency_version != expected_version:
                    raise StaleSystemSecurityPlanUpdate(
                        plan.id, expected_version, plan.concurrency_version
                    )
                association = session.scalar(
                    select(SystemSecurityPlanImplementationRecord)
                    .where(
                        SystemSecurityPlanImplementationRecord.tenant_id == tenant_id,
                        SystemSecurityPlanImplementationRecord.system_security_plan_id == plan_id,
                        (
                            SystemSecurityPlanImplementationRecord.implementation_id
                            == implementation_id
                        ),
                    )
                    .with_for_update()
                )
                if association is None:
                    raise EntityNotFoundError("SSP implementation contribution not found.")
                session.delete(association)
                plan.updated_by = actor
                plan.updated_at = datetime.now(UTC)
                try:
                    session.flush()
                except StaleDataError as error:
                    raise _StaleSystemSecurityPlanFlush(plan_id, expected_version) from error
                return {"concurrency_version": int(plan.concurrency_version)}
        except _StaleSystemSecurityPlanFlush as stale:
            current = self._current_plan_version(tenant_id, stale.plan_id)
            raise StaleSystemSecurityPlanUpdate(
                stale.plan_id,
                stale.expected_version,
                current,
            ) from stale.__cause__

    def validate_plan(self, tenant_id: UUID, plan_id: UUID) -> dict[str, Any]:
        with self._session_scope() as session:
            plan = self._get_plan(session, tenant_id, plan_id)
            draft, diagnostics, baseline_count, documented_count = self._build_draft(session, plan)
            if not any(item["code"] == "oscal_schema" for item in diagnostics):
                try:
                    validate_system_security_plan_document(
                        draft,
                        baseline_control_ids=self._baseline_control_ids(
                            session, plan.revision_id
                        ),
                        expected_baseline_href=self._catalog_href(plan),
                    )
                except SystemSecurityPlanValidationError as error:
                    diagnostics.append(
                        {"severity": "error", "code": "oscal_schema", "message": str(error)}
                    )
            return {
                "valid": not any(item["severity"] == "error" for item in diagnostics),
                "diagnostics": diagnostics,
                "baseline_control_count": baseline_count,
                "documented_control_count": documented_count,
            }

    def create_version(
        self,
        tenant_id: UUID,
        actor: UUID,
        plan_id: UUID,
        *,
        expected_version: int,
    ) -> dict[str, Any]:
        try:
            with self._session_scope() as session:
                plan = self._get_plan(session, tenant_id, plan_id, lock=True)
                if plan.concurrency_version != expected_version:
                    raise StaleSystemSecurityPlanUpdate(
                        plan.id, expected_version, plan.concurrency_version
                    )
                self._get_system(session, tenant_id, plan.system_id, lock=True)
                revision = self._get_revision(
                    session, tenant_id, plan.catalog_id, plan.revision_id, lock=True
                )
                draft, diagnostics, _, _ = self._build_draft(session, plan, revision=revision)
                if not any(item["code"] == "oscal_schema" for item in diagnostics):
                    try:
                        validate_system_security_plan_document(
                            draft,
                            baseline_control_ids=self._baseline_control_ids(
                                session, plan.revision_id
                            ),
                            expected_baseline_href=self._catalog_href(plan),
                        )
                    except SystemSecurityPlanValidationError as error:
                        diagnostics.append(
                            {"severity": "error", "code": "oscal_schema", "message": str(error)}
                        )
                errors = [item for item in diagnostics if item["severity"] == "error"]
                if errors:
                    raise InvalidSystemSecurityPlan(diagnostics)

                previous = session.scalars(
                    select(SystemSecurityPlanVersionRecord)
                    .where(
                        SystemSecurityPlanVersionRecord.tenant_id == tenant_id,
                        SystemSecurityPlanVersionRecord.system_security_plan_id == plan.id,
                    )
                    .order_by(SystemSecurityPlanVersionRecord.created_at.desc())
                    .limit(1)
                ).first()
                version = self._next_document_version(
                    previous.document_version if previous else None
                )
                now = datetime.now(UTC).replace(microsecond=0)
                body = draft["system-security-plan"]
                body["uuid"] = str(uuid4())
                body["metadata"]["last-modified"] = now.isoformat()
                body["metadata"]["version"] = version
                try:
                    final_document = serialize_authored_system_security_plan(draft)
                    validate_system_security_plan_document(
                        final_document,
                        baseline_control_ids=self._baseline_control_ids(
                            session, plan.revision_id
                        ),
                        expected_baseline_href=self._catalog_href(plan),
                    )
                except SystemSecurityPlanValidationError as error:
                    diagnostics.append(
                        {"severity": "error", "code": "oscal_schema", "message": str(error)}
                    )
                    raise InvalidSystemSecurityPlan(diagnostics) from error

                stable_document = copy.deepcopy(final_document)
                stable_body = stable_document["system-security-plan"]
                stable_body["uuid"] = ""
                stable_body["metadata"]["last-modified"] = ""
                stable_body["metadata"]["version"] = ""
                digest = canonical_json_sha256(stable_document)
                existing = session.scalar(
                    select(SystemSecurityPlanVersionRecord).where(
                        SystemSecurityPlanVersionRecord.tenant_id == tenant_id,
                        SystemSecurityPlanVersionRecord.system_security_plan_id == plan.id,
                        SystemSecurityPlanVersionRecord.content_sha256 == digest,
                    )
                )
                if existing is not None:
                    return self._version_payload(
                        existing,
                        created=False,
                        concurrency_version=plan.concurrency_version,
                    )

                record = SystemSecurityPlanVersionRecord(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    system_security_plan_id=plan.id,
                    catalog_id=plan.catalog_id,
                    revision_id=plan.revision_id,
                    oscal_document_uuid=UUID(final_document["system-security-plan"]["uuid"]),
                    oscal_version=final_document["system-security-plan"]["metadata"][
                        "oscal-version"
                    ],
                    document_version=version,
                    last_modified=now,
                    content_sha256=digest,
                    document=final_document,
                    diagnostics=diagnostics,
                    created_at=now,
                )
                session.add(record)
                plan.updated_by = actor
                plan.updated_at = now
                plan.concurrency_version = plan.concurrency_version + 1
                try:
                    session.flush()
                except StaleDataError as error:
                    raise _StaleSystemSecurityPlanFlush(plan_id, expected_version) from error
                return self._version_payload(
                    record,
                    created=True,
                    concurrency_version=plan.concurrency_version,
                )
        except _StaleSystemSecurityPlanFlush as stale:
            current = self._current_plan_version(tenant_id, stale.plan_id)
            raise StaleSystemSecurityPlanUpdate(
                stale.plan_id,
                stale.expected_version,
                current,
            ) from stale.__cause__

    def _current_plan_version(self, tenant_id: UUID, plan_id: UUID) -> int:
        with self._session_scope() as session:
            current = session.scalar(
                select(SystemSecurityPlanRecord.concurrency_version).where(
                    SystemSecurityPlanRecord.tenant_id == tenant_id,
                    SystemSecurityPlanRecord.id == plan_id,
                )
            )
            if current is None:
                raise EntityNotFoundError("SSP not found.")
            return int(current)

    def list_versions(self, tenant_id: UUID, plan_id: UUID) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            self._get_plan(session, tenant_id, plan_id)
            versions = session.scalars(
                select(SystemSecurityPlanVersionRecord)
                .where(
                    SystemSecurityPlanVersionRecord.tenant_id == tenant_id,
                    SystemSecurityPlanVersionRecord.system_security_plan_id == plan_id,
                )
                .order_by(
                    SystemSecurityPlanVersionRecord.created_at.desc(),
                    SystemSecurityPlanVersionRecord.id,
                )
            ).all()
            return [self._version_payload(version, created=False) for version in versions]

    def export_version(self, tenant_id: UUID, plan_id: UUID, version_id: UUID) -> dict[str, Any]:
        with self._session_scope() as session:
            version = session.scalar(
                select(SystemSecurityPlanVersionRecord).where(
                    SystemSecurityPlanVersionRecord.tenant_id == tenant_id,
                    SystemSecurityPlanVersionRecord.system_security_plan_id == plan_id,
                    SystemSecurityPlanVersionRecord.id == version_id,
                )
            )
            if version is None:
                raise EntityNotFoundError("SSP version not found.")
            return version.document

    def _build_draft(
        self,
        session: Session,
        plan: SystemSecurityPlanRecord,
        *,
        revision: CatalogRevisionRecord | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, str]], int, int]:
        system = self._get_system(session, plan.tenant_id, plan.system_id)
        revision = revision or self._get_revision(
            session, plan.tenant_id, plan.catalog_id, plan.revision_id
        )
        components = session.scalars(
            select(SystemComponentRecord)
            .where(
                SystemComponentRecord.tenant_id == plan.tenant_id,
                SystemComponentRecord.system_id == plan.system_id,
            )
            .order_by(SystemComponentRecord.created_at, SystemComponentRecord.id)
            .with_for_update()
        ).all()
        associations = session.scalars(
            select(SystemSecurityPlanImplementationRecord)
            .where(
                SystemSecurityPlanImplementationRecord.tenant_id == plan.tenant_id,
                SystemSecurityPlanImplementationRecord.system_security_plan_id == plan.id,
            )
            .order_by(
                SystemSecurityPlanImplementationRecord.oscal_control_id,
                SystemSecurityPlanImplementationRecord.system_component_id,
                SystemSecurityPlanImplementationRecord.implementation_id,
            )
            .with_for_update()
        ).all()
        implementations: dict[UUID, ControlImplementationRecord] = {}
        responsibilities_count = 0
        evidence_omitted_count = 0
        for association in associations:
            implementation = session.scalar(
                select(ControlImplementationRecord)
                .where(
                    ControlImplementationRecord.tenant_id == plan.tenant_id,
                    ControlImplementationRecord.id == association.implementation_id,
                )
                .with_for_update()
            )
            if implementation is None:
                raise RuntimeError("An SSP contribution has no Implementation Register record.")
            implementations[implementation.id] = implementation
            responsibilities_count += (
                session.scalar(
                    select(func.count())
                    .select_from(ImplementationResponsibilityRecord)
                    .where(
                        ImplementationResponsibilityRecord.tenant_id == plan.tenant_id,
                        ImplementationResponsibilityRecord.implementation_id == implementation.id,
                    )
                )
                or 0
            )
            evidence_omitted_count += sum(
                1
                for reference in implementation.evidence_references
                if not self._is_safe_link(reference)
            )
        diagnostics: list[dict[str, str]] = []
        if responsibilities_count:
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "responsibilities_omitted",
                    "message": (
                        f"{responsibilities_count} operational responsibilities remain in "
                        "the Implementation Register but are omitted because no OSCAL "
                        "role/party identity mapping exists."
                    ),
                }
            )
        if evidence_omitted_count:
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "evidence_references_omitted",
                    "message": (
                        f"{evidence_omitted_count} evidence references remain in the "
                        "Implementation Register but are omitted because they are not "
                        "absolute HTTP(S) links."
                    ),
                }
            )
        errors: list[tuple[str, str]] = []
        if not system.system_ids:
            errors.append(
                ("system_ids_required", "Add at least one user-authored system identifier.")
            )
        if not system.description:
            errors.append(("system_description_required", "Add a system description."))
        if not system.system_boundary:
            errors.append(
                ("system_boundary_required", "Describe the system authorization boundary.")
            )
        if not system.information_types:
            errors.append(
                (
                    "information_types_required",
                    "Add at least one information type with a title and description.",
                )
            )
        if not system.operational_status:
            errors.append(
                ("system_status_required", "Select the system's OSCAL operational status.")
            )
        if system.operational_status == "other" and not (system.status_remarks or "").strip():
            errors.append(
                (
                    "system_status_remarks_required",
                    "Explain the system's 'other' operational status.",
                )
            )
        if not components:
            errors.append(("components_required", "Add at least one concrete system component."))
        if any(
            not item.get("status", {}).get("state")
            for item in (component.component for component in components)
        ):
            errors.append(
                (
                    "component_status_required",
                    "Select an OSCAL operational status for every system component.",
                )
            )
        if not (plan.control_implementation_description or "").strip():
            errors.append(
                (
                    "control_implementation_description_required",
                    "Describe the control implementation approach.",
                )
            )
        if not associations:
            errors.append(
                (
                    "implementation_contributions_required",
                    (
                        "Explicitly include at least one requirement-specific implementation "
                        "contribution."
                    ),
                )
            )
        for code, message in errors:
            diagnostics.append({"severity": "error", "code": code, "message": message})

        component_json = [copy.deepcopy(component.component) for component in components]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for association in associations:
            implementation = implementations[association.implementation_id]
            component = next(
                (item for item in components if item.id == association.system_component_id),
                None,
            )
            if component is None:
                raise RuntimeError("An SSP contribution references a missing System component.")
            state = implementation.oscal_implementation_status
            if state is None:
                diagnostics.append(
                    {
                        "severity": "error",
                        "code": "implementation_status_required",
                        "message": (
                            f"Select an explicit OSCAL implementation status for contribution "
                            f"{implementation.id}."
                        ),
                    }
                )
            if not implementation.description.strip():
                diagnostics.append(
                    {
                        "severity": "error",
                        "code": "implementation_description_required",
                        "message": (
                            f"Add an implementation description for contribution "
                            f"{implementation.id}."
                        ),
                    }
                )
            if (
                state in _IMPLEMENTATION_EXPLANATION_STATES
                and not (implementation.oscal_status_explanation or "").strip()
            ):
                diagnostics.append(
                    {
                        "severity": "error",
                        "code": "implementation_status_explanation_required",
                        "message": (
                            f"Explain the {state} state for contribution {implementation.id}."
                        ),
                    }
                )
            by_component: dict[str, Any] = {
                "component-uuid": str(component.oscal_component_uuid),
                "uuid": str(implementation.id),
                "description": implementation.description,
            }
            if state is not None:
                status: dict[str, str] = {"state": state}
                if implementation.oscal_status_explanation:
                    status["remarks"] = implementation.oscal_status_explanation
                by_component["implementation-status"] = status
            safe_evidence = [
                value for value in implementation.evidence_references if self._is_safe_link(value)
            ]
            if safe_evidence:
                by_component["links"] = [
                    {"href": value, "rel": "related"} for value in safe_evidence
                ]
            grouped[implementation.oscal_control_id].append(by_component)
        implemented_requirements = [
            {
                "uuid": str(uuid5(_VERSION_NAMESPACE, f"{plan.id}:{control_id}")),
                "control-id": control_id,
                "by-components": values,
            }
            for control_id, values in sorted(grouped.items())
        ]
        authoring_version = authoring_version_for_component_types(
            OscalDocumentModel.SYSTEM_SECURITY_PLAN,
            [component.get("type", "") for component in component_json],
        )
        body = {
            "uuid": str(uuid5(_VERSION_NAMESPACE, f"{plan.id}:draft-document")),
            "metadata": {
                "title": plan.title,
                "last-modified": "2000-01-01T00:00:00+00:00",
                "version": "0.0.0",
                "oscal-version": authoring_version,
            },
            "import-profile": {"href": self._catalog_href(plan)},
            "system-characteristics": {
                "system-ids": copy.deepcopy(system.system_ids),
                "system-name": system.name,
                "description": system.description or "",
                "system-information": {
                    "information-types": [
                        {
                            "uuid": item["uuid"],
                            "title": item["title"],
                            "description": item["description"],
                        }
                        for item in system.information_types
                    ]
                },
                "status": (
                    self._oscal_status(system.operational_status, system.status_remarks)
                    if system.operational_status
                    else {"state": "other"}
                ),
                "authorization-boundary": {"description": system.system_boundary or ""},
            },
            "system-implementation": {"components": component_json},
            "control-implementation": {
                "description": plan.control_implementation_description or "",
                "implemented-requirements": implemented_requirements,
            },
        }
        if system.security_sensitivity_level:
            body["system-characteristics"]["security-sensitivity-level"] = (
                system.security_sensitivity_level
            )
        document = {"system-security-plan": body}
        try:
            document = serialize_authored_system_security_plan(document)
        except SystemSecurityPlanValidationError as error:
            diagnostics.append(
                {"severity": "error", "code": "oscal_schema", "message": str(error)}
            )
        baseline_ids = self._baseline_control_ids(session, plan.revision_id)
        documented_ids = set(grouped)
        baseline_count = len(baseline_ids)
        if documented_ids - baseline_ids:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "control_not_in_baseline",
                    "message": (
                        "An explicitly included implementation references a control outside "
                        "the pinned Catalog revision."
                    ),
                }
            )
        return document, diagnostics, baseline_count, len(documented_ids)

    @staticmethod
    def _baseline_control_ids(session: Session, revision_id: UUID) -> set[str]:
        return set(
            session.scalars(
                select(CatalogControlIndexRecord.oscal_control_id).where(
                    CatalogControlIndexRecord.catalog_revision_id == revision_id
                )
            )
        )

    @staticmethod
    def _catalog_href(plan: SystemSecurityPlanRecord) -> str:
        return (
            f"/api/v1/tenants/{plan.tenant_id}/catalogs/{plan.catalog_id}/"
            f"revisions/{plan.revision_id}/export"
        )

    @staticmethod
    def _is_safe_link(value: str) -> bool:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _oscal_status(state: str, remarks: str | None) -> dict[str, str]:
        result = {"state": state}
        if remarks and remarks.strip():
            result["remarks"] = remarks.strip()
        return result

    @staticmethod
    def _validate_system_fields(
        name: str,
        status: str | None,
        remarks: str | None,
        system_ids: list[dict[str, Any]],
        information_types: list[dict[str, Any]],
    ) -> None:
        if not name.strip():
            raise InvalidSystemSecurityPlan(
                [{"code": "missing_system_name", "message": "A System name is required."}]
            )
        if status is not None and status not in _SYSTEM_STATUSES:
            raise InvalidSystemSecurityPlan(
                [
                    {
                        "code": "invalid_system_status",
                        "message": "Select a valid OSCAL System operational status.",
                    }
                ]
            )
        if status == "other" and not (remarks or "").strip():
            raise InvalidSystemSecurityPlan(
                [
                    {
                        "code": "system_status_remarks_required",
                        "message": "Explain the 'other' System operational status.",
                    }
                ]
            )
        if len(system_ids) > 100 or len(information_types) > 100:
            raise InvalidSystemSecurityPlan(
                [
                    {
                        "code": "too_many_characteristics",
                        "message": (
                            "A System can include at most 100 identifiers and information types."
                        ),
                    }
                ]
            )

    @staticmethod
    def _normalize_system_ids(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in values:
            identifier = str(item["id"]).strip()
            if not identifier:
                raise InvalidSystemSecurityPlan(
                    [
                        {
                            "code": "invalid_system_identifier",
                            "message": "System identifiers must be nonempty user-provided values.",
                        }
                    ]
                )
            value = {"id": identifier}
            if item.get("identifier_type"):
                value["identifier-type"] = item["identifier_type"]
            normalized.append(value)
        if len({item["id"] for item in normalized}) != len(normalized):
            raise InvalidSystemSecurityPlan(
                [
                    {
                        "code": "duplicate_system_identifier",
                        "message": "System identifiers must be unique.",
                    }
                ]
            )
        return normalized

    @staticmethod
    def _normalize_information_types(
        values: list[dict[str, Any]], previous: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        existing = {
            item["title"]: item
            for item in (previous or [])
            if isinstance(item, dict) and "title" in item
        }
        normalized: list[dict[str, Any]] = []
        for item in values:
            title = str(item["title"]).strip()
            description = str(item["description"]).strip()
            if not title or not description:
                raise InvalidSystemSecurityPlan(
                    [
                        {
                            "code": "invalid_information_type",
                            "message": (
                                "Information types need user-authored titles and descriptions."
                            ),
                        }
                    ]
                )
            supplied = item.get("uuid")
            stable_id = (
                UUID(str(supplied)) if supplied else existing.get(title, {}).get("uuid", uuid4())
            )
            normalized.append({"uuid": str(stable_id), "title": title, "description": description})
        if len({item["uuid"] for item in normalized}) != len(normalized):
            raise InvalidSystemSecurityPlan(
                [
                    {
                        "code": "duplicate_information_type",
                        "message": "Information type identities must be unique.",
                    }
                ]
            )
        return normalized

    @staticmethod
    def _validate_component_fields(
        title: str, description: str, status: str, remarks: str | None
    ) -> None:
        if not title.strip() or not description.strip():
            raise InvalidSystemSecurityPlan(
                [
                    {
                        "code": "component_description_required",
                        "message": (
                            "Concrete components need user-authored titles and descriptions."
                        ),
                    }
                ]
            )
        if status not in _COMPONENT_STATUSES:
            raise InvalidSystemSecurityPlan(
                [
                    {
                        "code": "invalid_component_status",
                        "message": ("Select a valid OSCAL component operational status."),
                    }
                ]
            )
        if status == "other" and not (remarks or "").strip():
            raise InvalidSystemSecurityPlan(
                [
                    {
                        "code": "component_status_remarks_required",
                        "message": ("Explain the 'other' component operational status."),
                    }
                ]
            )

    @staticmethod
    def _next_document_version(previous: str | None) -> str:
        if previous is None:
            return "1.0.0"
        try:
            major, minor, patch = (int(value) for value in previous.split("."))
        except ValueError as error:
            raise RuntimeError("Stored SSP document version is malformed.") from error
        return f"{major}.{minor}.{patch + 1}"

    @staticmethod
    def _get_system(
        session: Session, tenant_id: UUID, system_id: UUID, *, lock: bool = False
    ) -> InformationSystemRecord:
        query = select(InformationSystemRecord).where(
            InformationSystemRecord.tenant_id == tenant_id,
            InformationSystemRecord.id == system_id,
        )
        record = session.scalar(query.with_for_update() if lock else query)
        if record is None:
            raise EntityNotFoundError("System not found.")
        return record

    @staticmethod
    def _get_revision(
        session: Session,
        tenant_id: UUID,
        catalog_id: UUID,
        revision_id: UUID,
        *,
        lock: bool = False,
    ) -> CatalogRevisionRecord:
        query = select(CatalogRevisionRecord).where(
            CatalogRevisionRecord.tenant_id == tenant_id,
            CatalogRevisionRecord.catalog_id == catalog_id,
            CatalogRevisionRecord.id == revision_id,
        )
        revision = session.scalar(query.with_for_update() if lock else query)
        if revision is None:
            raise EntityNotFoundError("Catalog revision not found.")
        return revision

    @staticmethod
    def _get_plan(
        session: Session, tenant_id: UUID, plan_id: UUID, *, lock: bool = False
    ) -> SystemSecurityPlanRecord:
        query = select(SystemSecurityPlanRecord).where(
            SystemSecurityPlanRecord.tenant_id == tenant_id,
            SystemSecurityPlanRecord.id == plan_id,
        )
        plan = session.scalar(query.with_for_update() if lock else query)
        if plan is None:
            raise EntityNotFoundError("SSP not found.")
        return plan

    @staticmethod
    def _system_payload(system: InformationSystemRecord) -> dict[str, Any]:
        return {
            "id": system.id,
            "tenant_id": system.tenant_id,
            "organization_id": system.organization_id,
            "name": system.name,
            "description": system.description,
            "system_boundary": system.system_boundary,
            "system_ids": system.system_ids,
            "information_types": system.information_types,
            "operational_status": system.operational_status,
            "status_remarks": system.status_remarks,
            "security_sensitivity_level": system.security_sensitivity_level,
            "created_at": system.created_at,
            "updated_at": system.updated_at,
        }

    @staticmethod
    def _component_payload(component: SystemComponentRecord) -> dict[str, Any]:
        return {
            "id": component.id,
            "system_id": component.system_id,
            "oscal_component_uuid": component.oscal_component_uuid,
            "component": component.component,
            "is_system_component": component.is_system_component,
            "source_snapshot_id": component.source_snapshot_id,
            "source_component_uuid": component.source_component_uuid,
        }

    def _plan_payload(
        self,
        session: Session,
        plan: SystemSecurityPlanRecord,
        *,
        revision: CatalogRevisionRecord | None = None,
    ) -> dict[str, Any]:
        revision = revision or self._get_revision(
            session, plan.tenant_id, plan.catalog_id, plan.revision_id
        )
        included = session.execute(
            select(
                SystemSecurityPlanImplementationRecord.implementation_id,
                SystemSecurityPlanImplementationRecord.oscal_control_id,
                SystemSecurityPlanImplementationRecord.system_component_id,
            )
            .where(
                SystemSecurityPlanImplementationRecord.tenant_id == plan.tenant_id,
                SystemSecurityPlanImplementationRecord.system_security_plan_id == plan.id,
            )
            .order_by(
                SystemSecurityPlanImplementationRecord.oscal_control_id,
                SystemSecurityPlanImplementationRecord.implementation_id,
            )
        ).all()
        baseline_count = (
            session.scalar(
                select(func.count())
                .select_from(CatalogControlIndexRecord)
                .where(CatalogControlIndexRecord.catalog_revision_id == plan.revision_id)
            )
            or 0
        )
        return {
            "id": plan.id,
            "tenant_id": plan.tenant_id,
            "system_id": plan.system_id,
            "catalog_id": plan.catalog_id,
            "revision_id": plan.revision_id,
            "catalog_name": revision.content.get("catalog", {})
            .get("metadata", {})
            .get("title", ""),
            "title": plan.title,
            "control_implementation_description": plan.control_implementation_description,
            "included_implementations": [
                {
                    "implementation_id": row.implementation_id,
                    "oscal_control_id": row.oscal_control_id,
                    "system_component_id": row.system_component_id,
                }
                for row in included
            ],
            "baseline_control_count": baseline_count,
            "documented_control_count": len({row.oscal_control_id for row in included}),
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
            "concurrency_version": plan.concurrency_version,
        }

    @staticmethod
    def _version_payload(
        version: SystemSecurityPlanVersionRecord,
        *,
        created: bool,
        concurrency_version: int | None = None,
    ) -> dict[str, Any]:
        return {
            "id": version.id,
            "system_security_plan_id": version.system_security_plan_id,
            "catalog_id": version.catalog_id,
            "revision_id": version.revision_id,
            "oscal_document_uuid": version.oscal_document_uuid,
            "oscal_version": version.oscal_version,
            "document_version": version.document_version,
            "last_modified": version.last_modified,
            "content_sha256": version.content_sha256,
            "diagnostics": version.diagnostics,
            "created_at": version.created_at,
            "created": created,
            "concurrency_version": concurrency_version,
        }
