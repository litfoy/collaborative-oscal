from __future__ import annotations

import copy
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from collaborative_oscal_oscal.assessment_result import (
    AssessmentResultValidationError,
    serialize_authored_assessment_result,
    validate_assessment_result_document,
)
from collaborative_oscal_oscal.catalog_index import canonical_json_sha256
from collaborative_oscal_oscal.versions import OscalDocumentModel, authoring_version_for
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.domain.errors import EntityNotFoundError
from app.persistence.models import (
    AssessmentPlanRecord,
    AssessmentPlanVersionRecord,
    AssessmentResultRecord,
    AssessmentResultVersionRecord,
    CatalogRevisionRecord,
    InformationSystemRecord,
    SystemSecurityPlanVersionRecord,
)

SessionScope = Callable[[], AbstractContextManager[Session]]
_ALLOWED_METHODS = frozenset({"EXAMINE", "INTERVIEW", "TEST"})
_HOST_LABEL_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
_IPV4_DOTTED_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


class InvalidAssessmentResult(ValueError):
    def __init__(self, diagnostics: list[dict[str, str]]) -> None:
        self.diagnostics = diagnostics
        super().__init__(
            "The Assessment Results working state is not ready to create a valid OSCAL version."
        )


class StaleAssessmentResultUpdate(ValueError):
    def __init__(self, result_id: UUID, expected_version: int, current_version: int) -> None:
        self.result_id = result_id
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__("The Assessment Results record changed after it was loaded.")


class AssessmentResultService:
    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    def list_results(self, tenant_id: UUID, system_id: UUID) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            self._get_system(session, tenant_id, system_id)
            records = session.scalars(
                select(AssessmentResultRecord)
                .where(
                    AssessmentResultRecord.tenant_id == tenant_id,
                    AssessmentResultRecord.system_id == system_id,
                )
                .order_by(
                    AssessmentResultRecord.updated_at.desc(),
                    AssessmentResultRecord.id,
                )
            ).all()
            return [self._result_payload(session, record) for record in records]

    def create_result(
        self,
        tenant_id: UUID,
        actor: UUID,
        system_id: UUID,
        *,
        assessment_plan_id: UUID,
        assessment_plan_version_id: UUID,
        title: str,
        description: str | None,
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            self._get_system(session, tenant_id, system_id)
            plan = self._get_plan(session, tenant_id, assessment_plan_id)
            if plan.system_id != system_id:
                raise InvalidAssessmentResult(
                    [
                        {
                            "code": "system_plan_mismatch",
                            "message": (
                                "The selected Assessment Plan does not belong to this "
                                "System."
                            ),
                        }
                    ]
                )
            plan_version = self._get_plan_version(session, tenant_id, assessment_plan_version_id)
            if plan_version.assessment_plan_id != assessment_plan_id:
                raise InvalidAssessmentResult(
                    [
                        {
                            "code": "plan_version_mismatch",
                            "message": (
                                "The selected Assessment Plan version does not belong to "
                                "this Assessment Plan."
                            ),
                        }
                    ]
                )

            controls = self._plan_reviewed_control_ids(plan_version)
            now = datetime.now(UTC)
            record = AssessmentResultRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                system_id=system_id,
                assessment_plan_id=assessment_plan_id,
                assessment_plan_version_id=assessment_plan_version_id,
                title=title.strip(),
                description=description,
                working_data=self._default_working_data(reviewed_control_ids=controls),
                created_by=actor,
                updated_by=actor,
                created_at=now,
                updated_at=now,
                concurrency_version=1,
            )
            session.add(record)
            session.flush()
            return self._result_payload(session, record)

    def get_result(self, tenant_id: UUID, result_id: UUID) -> dict[str, Any]:
        with self._session_scope() as session:
            record = self._get_result(session, tenant_id, result_id)
            return self._result_payload(session, record)

    def update_result(
        self,
        tenant_id: UUID,
        actor: UUID,
        result_id: UUID,
        *,
        expected_version: int,
        title: str,
        description: str | None,
        working_data: dict[str, Any],
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            record = self._get_result(session, tenant_id, result_id, lock=True)
            if record.concurrency_version != expected_version:
                raise StaleAssessmentResultUpdate(
                    record.id, expected_version, record.concurrency_version
                )
            context = self._context_for_result(session, record)
            normalized = self._normalize_working_data(working_data, previous=record.working_data)
            self._validate_working_integrity(
                normalized,
                result_uuid=record.id,
                planned_control_ids=context["planned_control_set"],
                allowed_subject_uuids=context["subject_uuid_set"],
                statement_controls=context["statement_controls"],
                catalog_objective_controls=context["catalog_objective_controls"],
                selected_catalog_objective_ids=context["selected_catalog_objective_ids"],
                local_objective_controls=context["local_objective_controls"],
                require_related_observations=False,
            )
            record.title = title.strip()
            record.description = description
            record.working_data = copy.deepcopy(normalized)
            record.updated_by = actor
            record.updated_at = datetime.now(UTC)
            try:
                session.flush()
            except StaleDataError as error:
                current = self._current_result_version(tenant_id, result_id)
                raise StaleAssessmentResultUpdate(
                    result_id,
                    expected_version,
                    current,
                ) from error
            return self._result_payload(session, record)

    def validate_result(self, tenant_id: UUID, result_id: UUID) -> dict[str, Any]:
        with self._session_scope() as session:
            record = self._get_result(session, tenant_id, result_id)
            draft, diagnostics, context = self._build_draft(session, record)
            errors = [item for item in diagnostics if item["severity"] == "error"]
            return {
                "valid": len(errors) == 0,
                "diagnostics": diagnostics,
                "planned_control_ids": context["planned_control_ids"],
                "statement_options": context["statement_options"],
                "objective_options": context["objective_options"],
                "subject_options": context["subject_options"],
                "oscal_candidate": draft,
            }

    def create_version(
        self,
        tenant_id: UUID,
        actor: UUID,
        result_id: UUID,
        *,
        expected_version: int,
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            record = self._get_result(session, tenant_id, result_id, lock=True)
            if record.concurrency_version != expected_version:
                raise StaleAssessmentResultUpdate(
                    record.id, expected_version, record.concurrency_version
                )
            draft, diagnostics, context = self._build_draft(session, record)
            errors = [item for item in diagnostics if item["severity"] == "error"]
            if errors:
                raise InvalidAssessmentResult(diagnostics)

            previous = session.scalars(
                select(AssessmentResultVersionRecord)
                .where(
                    AssessmentResultVersionRecord.tenant_id == tenant_id,
                    AssessmentResultVersionRecord.assessment_result_id == record.id,
                )
                .order_by(AssessmentResultVersionRecord.created_at.desc())
                .limit(1)
            ).first()
            version = self._next_document_version(
                previous.document_version if previous else None
            )
            now = datetime.now(UTC).replace(microsecond=0)
            body = draft["assessment-results"]
            body["uuid"] = str(uuid4())
            body["metadata"]["last-modified"] = now.isoformat()
            body["metadata"]["version"] = version

            try:
                final_document = serialize_authored_assessment_result(draft)
                validate_assessment_result_document(
                    final_document,
                    expected_assessment_plan_href=self._plan_href(record),
                    allowed_statement_ids=context["statement_id_set"],
                    allowed_objective_ids=context["objective_id_set"],
                    allowed_observation_methods=_ALLOWED_METHODS,
                )
            except AssessmentResultValidationError as error:
                diagnostics.append(self._oscal_diagnostic(error))
                raise InvalidAssessmentResult(diagnostics) from error

            stable_document = copy.deepcopy(final_document)
            stable_body = stable_document["assessment-results"]
            stable_body["uuid"] = ""
            stable_body["metadata"]["last-modified"] = ""
            stable_body["metadata"]["version"] = ""
            digest = canonical_json_sha256(stable_document)

            existing = session.scalar(
                select(AssessmentResultVersionRecord).where(
                    AssessmentResultVersionRecord.tenant_id == tenant_id,
                    AssessmentResultVersionRecord.assessment_result_id == record.id,
                    AssessmentResultVersionRecord.content_sha256 == digest,
                )
            )
            if existing is not None:
                return self._version_payload(
                    existing,
                    created=False,
                    concurrency_version=record.concurrency_version,
                )

            snapshot = AssessmentResultVersionRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                assessment_result_id=record.id,
                assessment_plan_version_id=record.assessment_plan_version_id,
                oscal_document_uuid=UUID(final_document["assessment-results"]["uuid"]),
                oscal_version=final_document["assessment-results"]["metadata"][
                    "oscal-version"
                ],
                document_version=version,
                last_modified=now,
                content_sha256=digest,
                document=final_document,
                diagnostics=diagnostics,
                created_at=now,
            )
            session.add(snapshot)
            record.updated_by = actor
            record.updated_at = now
            try:
                session.flush()
            except StaleDataError as error:
                current = self._current_result_version(tenant_id, result_id)
                raise StaleAssessmentResultUpdate(
                    result_id,
                    expected_version,
                    current,
                ) from error
            return self._version_payload(
                snapshot,
                created=True,
                concurrency_version=record.concurrency_version,
            )

    def _current_result_version(self, tenant_id: UUID, result_id: UUID) -> int:
        with self._session_scope() as session:
            current = session.scalar(
                select(AssessmentResultRecord.concurrency_version).where(
                    AssessmentResultRecord.tenant_id == tenant_id,
                    AssessmentResultRecord.id == result_id,
                )
            )
            if current is None:
                raise EntityNotFoundError("Assessment Results record not found.")
            return int(current)

    def list_versions(self, tenant_id: UUID, result_id: UUID) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            self._get_result(session, tenant_id, result_id)
            versions = session.scalars(
                select(AssessmentResultVersionRecord)
                .where(
                    AssessmentResultVersionRecord.tenant_id == tenant_id,
                    AssessmentResultVersionRecord.assessment_result_id == result_id,
                )
                .order_by(
                    AssessmentResultVersionRecord.created_at.desc(),
                    AssessmentResultVersionRecord.id,
                )
            ).all()
            return [self._version_payload(item, created=False) for item in versions]

    def export_version(
        self, tenant_id: UUID, result_id: UUID, version_id: UUID
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            version = session.scalar(
                select(AssessmentResultVersionRecord).where(
                    AssessmentResultVersionRecord.tenant_id == tenant_id,
                    AssessmentResultVersionRecord.assessment_result_id == result_id,
                    AssessmentResultVersionRecord.id == version_id,
                )
            )
            if version is None:
                raise EntityNotFoundError("Assessment Results version not found.")
            return version.document

    def _build_draft(
        self, session: Session, record: AssessmentResultRecord
    ) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, Any]]:
        context = self._context_for_result(session, record)
        diagnostics: list[dict[str, str]] = []
        try:
            self._validate_working_integrity(
                record.working_data,
                result_uuid=record.id,
                planned_control_ids=context["planned_control_set"],
                allowed_subject_uuids=context["subject_uuid_set"],
                statement_controls=context["statement_controls"],
                catalog_objective_controls=context["catalog_objective_controls"],
                selected_catalog_objective_ids=context["selected_catalog_objective_ids"],
                local_objective_controls=context["local_objective_controls"],
                require_related_observations=True,
            )
        except InvalidAssessmentResult as error:
            diagnostics.extend(error.diagnostics)

        now = datetime.now(UTC).replace(microsecond=0)
        oscal_version = authoring_version_for(OscalDocumentModel.ASSESSMENT_RESULT)

        resources: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        for observation in record.working_data.get("observations", []):
            evidence_refs = []
            for evidence in observation.get("evidence", []):
                evidence_uuid = str(evidence["id"])
                resource: dict[str, Any] = {
                    "uuid": evidence_uuid,
                    "title": evidence["title"],
                    "description": evidence["description"],
                }
                if evidence.get("href"):
                    resource["rlinks"] = [{"href": evidence["href"]}]
                resources.append(resource)
                evidence_refs.append(
                    {
                        "href": f"#{evidence_uuid}",
                        "description": evidence.get("description") or evidence["title"],
                    }
                )

            entry: dict[str, Any] = {
                "uuid": str(observation["id"]),
                "title": observation["title"],
                "description": observation["description"],
                "methods": list(observation.get("methods", [])),
                "collected": self._dt(observation["collected_at"]),
            }
            if observation.get("subject_uuids"):
                entry["subjects"] = [
                    {
                        "type": "component",
                        "subject-uuid": str(subject_uuid),
                    }
                    for subject_uuid in observation["subject_uuids"]
                ]
            if evidence_refs:
                entry["relevant-evidence"] = evidence_refs
            observations.append(entry)

        findings: list[dict[str, Any]] = []
        for finding in record.working_data.get("findings", []):
            entry: dict[str, Any] = {
                "uuid": str(finding["id"]),
                "title": finding["title"],
                "description": finding["description"],
                "target": {
                    "type": finding["target_type"],
                    "target-id": finding["target_id"],
                    "status": {"state": finding["status"]},
                },
            }
            if finding.get("related_observation_ids"):
                entry["related-observations"] = [
                    {"observation-uuid": str(item)}
                    for item in finding["related_observation_ids"]
                ]
            findings.append(entry)

        reviewed_controls = {
            "control-selections": [
                {
                    "include-controls": [
                        {"control-id": control_id}
                        for control_id in record.working_data.get("reviewed_control_ids", [])
                    ]
                }
            ]
        }

        result_body: dict[str, Any] = {
            "uuid": str(record.id),
            "title": record.title,
            "description": record.description or record.title,
            "reviewed-controls": reviewed_controls,
            "observations": observations,
            "findings": findings,
        }
        if record.working_data.get("start"):
            result_body["start"] = self._dt(record.working_data["start"])
        if record.working_data.get("end"):
            result_body["end"] = self._dt(record.working_data["end"])

        document: dict[str, Any] = {
            "assessment-results": {
                "uuid": str(uuid4()),
                "metadata": {
                    "title": record.title,
                    "last-modified": now.isoformat(),
                    "version": "draft",
                    "oscal-version": oscal_version,
                },
                "import-ap": {"href": self._plan_href(record)},
                "results": [result_body],
            }
        }
        if resources:
            document["assessment-results"]["back-matter"] = {"resources": resources}

        try:
            validate_assessment_result_document(
                document,
                expected_assessment_plan_href=self._plan_href(record),
                allowed_statement_ids=context["statement_id_set"],
                allowed_objective_ids=context["objective_id_set"],
                allowed_observation_methods=_ALLOWED_METHODS,
            )
        except AssessmentResultValidationError as error:
            diagnostics.append(self._oscal_diagnostic(error))

        return document, diagnostics, context

    def _context_for_result(
        self, session: Session, record: AssessmentResultRecord
    ) -> dict[str, Any]:
        plan_version = self._get_plan_version(
            session, record.tenant_id, record.assessment_plan_version_id
        )
        ssp_version = self._get_ssp_version(
            session, record.tenant_id, plan_version.system_security_plan_version_id
        )
        revision = self._get_revision(
            session, record.tenant_id, ssp_version.catalog_id, ssp_version.revision_id
        )

        subject_options = self._subject_options(ssp_version)
        component_titles = {
            item["uuid"] if isinstance(item["uuid"], UUID) else UUID(str(item["uuid"])): {
                "title": item["title"],
                "type": item["type"],
            }
            for item in subject_options
        }

        plan_scope = self._plan_scope(plan_version.document)
        planned_control_ids = plan_scope["planned_control_ids"]
        planned_control_set = set(planned_control_ids)

        selected_subjects = [
            subject
            for subject in plan_scope["selected_subject_uuids"]
            if subject in component_titles
        ]
        scoped_subject_options = [
            {
                "uuid": subject,
                "title": component_titles[subject]["title"],
                "type": component_titles[subject]["type"],
            }
            for subject in selected_subjects
        ]
        subject_uuid_set = set(selected_subjects)

        statement_controls = self._statement_controls(revision.content)
        statement_options = self._statement_options(
            statement_controls,
            planned_control_set,
        )

        catalog_objective_controls = self._catalog_objective_controls(revision.content)
        local_objective_controls = plan_scope["local_objective_controls"]
        selected_catalog_objective_ids = plan_scope["selected_catalog_objective_ids"]
        objective_options = self._objective_options(
            catalog_objective_controls=catalog_objective_controls,
            selected_catalog_objective_ids=selected_catalog_objective_ids,
            local_objective_controls=local_objective_controls,
            planned_control_ids=planned_control_set,
        )

        return {
            "planned_control_ids": planned_control_ids,
            "planned_control_set": planned_control_set,
            "subject_options": scoped_subject_options,
            "subject_uuid_set": subject_uuid_set,
            "statement_options": statement_options,
            "statement_id_set": {item["statement_id"] for item in statement_options},
            "statement_controls": statement_controls,
            "objective_options": objective_options,
            "objective_id_set": {item["objective_id"] for item in objective_options},
            "catalog_objective_controls": catalog_objective_controls,
            "selected_catalog_objective_ids": selected_catalog_objective_ids,
            "local_objective_controls": local_objective_controls,
        }

    def _validate_working_integrity(
        self,
        working_data: dict[str, Any],
        *,
        result_uuid: UUID | None,
        planned_control_ids: set[str],
        allowed_subject_uuids: set[UUID],
        statement_controls: dict[str, dict[str, int]],
        catalog_objective_controls: dict[str, dict[str, int]],
        selected_catalog_objective_ids: set[str],
        local_objective_controls: dict[str, str],
        require_related_observations: bool,
    ) -> None:
        diagnostics: list[dict[str, str]] = []

        reviewed_control_ids = [
            str(item) for item in working_data.get("reviewed_control_ids", []) if item
        ]
        if len(reviewed_control_ids) != len(set(reviewed_control_ids)):
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_reviewed_controls",
                    "message": "Reviewed controls must be unique.",
                }
            )
        reviewed_control_set = set(reviewed_control_ids)
        unknown_controls = sorted(reviewed_control_set - planned_control_ids)
        if unknown_controls:
            diagnostics.append(
                {
                    "category": "application_reference",
                    "code": "control_outside_assessment_plan_scope",
                    "message": (
                        "Reviewed controls are outside the pinned Assessment Plan scope: "
                        + ", ".join(unknown_controls)
                    ),
                }
            )

        observation_ids: list[UUID] = []
        document_evidence_ids: list[UUID] = []
        authored_entity_definitions: list[tuple[str, UUID]] = []
        if result_uuid is not None:
            authored_entity_definitions.append(("assessment-results", result_uuid))
        for observation_index, observation in enumerate(working_data.get("observations", [])):
            observation_id = UUID(str(observation["id"]))
            observation_ids.append(observation_id)
            authored_entity_definitions.append(("observation", observation_id))
            methods = set(observation.get("methods", []))
            disallowed = sorted(method for method in methods if method not in _ALLOWED_METHODS)
            if disallowed:
                diagnostics.append(
                    {
                        "category": "application_integrity",
                        "code": "invalid_observation_method",
                        "message": (
                            "Observation methods must be one of EXAMINE, INTERVIEW, TEST: "
                            + ", ".join(disallowed)
                        ),
                    }
                )
            subjects = {
                UUID(str(item)) for item in observation.get("subject_uuids", []) if item
            }
            missing = sorted(str(item) for item in subjects if item not in allowed_subject_uuids)
            if missing:
                diagnostics.append(
                    {
                        "category": "application_reference",
                        "code": "unknown_subject_uuid",
                        "message": (
                            "Observations reference subjects outside the pinned "
                            "Assessment Plan selection: "
                            + ", ".join(missing)
                        ),
                    }
                )

            evidence_ids: list[UUID] = []
            for evidence_index, evidence in enumerate(observation.get("evidence", [])):
                evidence_id = UUID(str(evidence["id"]))
                evidence_ids.append(evidence_id)
                document_evidence_ids.append(evidence_id)
                authored_entity_definitions.append(("evidence", evidence_id))
                href_error = self._validate_authored_evidence_href(evidence.get("href"))
                if href_error is not None:
                    diagnostics.append(
                        {
                            "category": "application_integrity",
                            "code": "invalid_evidence_href",
                            "message": href_error,
                            "path": (
                                f"$.observations[{observation_index}]"
                                f".evidence[{evidence_index}].href"
                            ),
                        }
                    )
            if len(evidence_ids) != len(set(evidence_ids)):
                diagnostics.append(
                    {
                        "category": "application_integrity",
                        "code": "duplicate_evidence_ids",
                        "message": "Evidence UUIDs must be unique per observation.",
                    }
                )

        duplicate_document_evidence_ids = self._duplicate_uuids(document_evidence_ids)
        if duplicate_document_evidence_ids:
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_evidence_ids_document",
                    "message": (
                        "Evidence UUIDs must be unique across the entire Assessment Results "
                        "document: "
                        + ", ".join(duplicate_document_evidence_ids)
                    ),
                }
            )

        if len(observation_ids) != len(set(observation_ids)):
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_observation_ids",
                    "message": "Observation UUIDs must be unique.",
                }
            )

        observation_set = set(observation_ids)
        finding_ids: list[UUID] = []
        for finding_index, finding in enumerate(working_data.get("findings", [])):
            finding_id = UUID(str(finding["id"]))
            finding_ids.append(finding_id)
            authored_entity_definitions.append(("finding", finding_id))

            target_type = finding["target_type"]
            target_id = str(finding["target_id"])
            if target_type == "statement-id":
                statement_candidate_counts = self._planned_definition_counts(
                    statement_controls.get(target_id, {}), planned_control_ids
                )
                if not statement_candidate_counts:
                    diagnostics.append(
                        {
                            "category": "application_reference",
                            "code": "unknown_statement_target",
                            "message": (
                                "Finding target statement-id "
                                f"{target_id!r} is outside the pinned historical baseline."
                            ),
                            "path": f"$.findings[{finding_index}].target_id",
                        }
                    )
                else:
                    statement_controls_in_scope = sorted(statement_candidate_counts)
                    if not self._is_unambiguous_target(statement_candidate_counts):
                        diagnostics.append(
                            {
                                "category": "application_reference",
                                "code": "ambiguous_statement_target",
                                "message": (
                                    "Finding target statement-id "
                                    f"{target_id!r} resolves to ambiguous definitions in "
                                    "the pinned Assessment Plan context: "
                                    + ", ".join(statement_controls_in_scope)
                                ),
                                "path": f"$.findings[{finding_index}].target_id",
                            }
                        )
                    else:
                        statement_control = next(iter(statement_candidate_counts))
                        actual_statement_controls = (
                            {statement_control} & reviewed_control_set
                        )
                        if not actual_statement_controls:
                            diagnostics.append(
                                {
                                    "category": "application_reference",
                                    "code": "statement_target_outside_actual_scope",
                                    "message": (
                                        "Finding target statement-id "
                                        f"{target_id!r} is outside the current "
                                        "reviewed control scope."
                                    ),
                                    "path": f"$.findings[{finding_index}].target_id",
                                }
                            )
            if target_type == "objective-id":
                has_local_objective = target_id in local_objective_controls
                local_control_id = local_objective_controls.get(target_id)
                catalog_candidate_counts: dict[str, int] = {}
                if target_id in selected_catalog_objective_ids:
                    catalog_candidate_counts = self._planned_definition_counts(
                        catalog_objective_controls.get(target_id, {}), planned_control_ids
                    )
                if has_local_objective and catalog_candidate_counts:
                    diagnostics.append(
                        {
                            "category": "application_reference",
                            "code": "ambiguous_objective_target",
                            "message": (
                                "Finding target objective-id "
                                f"{target_id!r} is ambiguous between local and catalog objectives."
                            ),
                            "path": f"$.findings[{finding_index}].target_id",
                        }
                    )
                else:
                    objective_candidate_counts: dict[str, int] = {}
                    if local_control_id is not None and local_control_id in planned_control_ids:
                        objective_candidate_counts[local_control_id] = 1
                    for control_id, count in catalog_candidate_counts.items():
                        objective_candidate_counts[control_id] = (
                            objective_candidate_counts.get(control_id, 0) + count
                        )

                    if not objective_candidate_counts:
                        diagnostics.append(
                            {
                                "category": "application_reference",
                                "code": "unknown_objective_target",
                                "message": (
                                    "Finding target objective-id "
                                    f"{target_id!r} is outside the pinned Assessment Plan context."
                                ),
                                "path": f"$.findings[{finding_index}].target_id",
                            }
                        )
                    elif not self._is_unambiguous_target(objective_candidate_counts):
                        diagnostics.append(
                            {
                                "category": "application_reference",
                                "code": "ambiguous_objective_target",
                                "message": (
                                    "Finding target objective-id "
                                    f"{target_id!r} resolves to ambiguous definitions in "
                                    "the pinned Assessment Plan context: "
                                    + ", ".join(sorted(objective_candidate_counts))
                                ),
                                "path": f"$.findings[{finding_index}].target_id",
                            }
                        )
                    else:
                        objective_control = next(iter(objective_candidate_counts))
                        actual_objective_controls = (
                            {objective_control} & reviewed_control_set
                        )
                        if not actual_objective_controls:
                            diagnostics.append(
                                {
                                    "category": "application_reference",
                                    "code": "objective_target_outside_actual_scope",
                                    "message": (
                                        "Finding target objective-id "
                                        f"{target_id!r} is outside the current "
                                        "reviewed control scope."
                                    ),
                                    "path": f"$.findings[{finding_index}].target_id",
                                }
                            )
            if target_type not in {"statement-id", "objective-id"}:
                diagnostics.append(
                    {
                        "category": "application_integrity",
                        "code": "invalid_target_type",
                        "message": "Finding target type must be statement-id or objective-id.",
                        "path": f"$.findings[{finding_index}].target_type",
                    }
                )

            related = {
                UUID(str(item)) for item in finding.get("related_observation_ids", []) if item
            }
            if require_related_observations and not related:
                diagnostics.append(
                    {
                        "category": "application_integrity",
                        "code": "finding_missing_related_observations",
                        "message": (
                            "Every finding must reference at least one related observation "
                            "before validation and immutable publication."
                        ),
                    }
                )
            missing_related = sorted(str(item) for item in related if item not in observation_set)
            if missing_related:
                diagnostics.append(
                    {
                        "category": "application_reference",
                        "code": "unknown_related_observation",
                        "message": (
                            "Findings reference observations that are not defined: "
                            + ", ".join(missing_related)
                        ),
                    }
                )

        if len(finding_ids) != len(set(finding_ids)):
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_finding_ids",
                    "message": "Finding UUIDs must be unique.",
                }
            )

        duplicate_entity_ids = self._cross_entity_uuid_collisions(authored_entity_definitions)
        if duplicate_entity_ids:
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_authored_entity_ids",
                    "message": (
                        "OSCAL authored entity UUIDs must be unambiguous across "
                        "assessment-results, "
                        "observations, findings, and evidence resources: "
                        + ", ".join(duplicate_entity_ids)
                    ),
                }
            )

        if diagnostics:
            raise InvalidAssessmentResult(
                [
                    {
                        "severity": "error",
                        "category": item["category"],
                        "code": item["code"],
                        "message": item["message"],
                        **({"path": item["path"]} if "path" in item else {}),
                    }
                    for item in diagnostics
                ]
            )

    @staticmethod
    def _normalize_working_data(
        working_data: dict[str, Any], *, previous: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        del previous
        normalized = copy.deepcopy(working_data)

        for observation in normalized.get("observations", []):
            if not observation.get("id"):
                observation["id"] = str(uuid4())
            for evidence in observation.get("evidence", []):
                if evidence.get("id"):
                    continue
                evidence["id"] = str(uuid4())

        for finding in normalized.get("findings", []):
            if finding.get("id"):
                continue
            finding["id"] = str(uuid4())

        return normalized

    @staticmethod
    def _duplicate_uuids(values: list[UUID]) -> list[str]:
        seen: set[UUID] = set()
        duplicates: list[str] = []
        for value in values:
            if value in seen and str(value) not in duplicates:
                duplicates.append(str(value))
            seen.add(value)
        return duplicates

    @staticmethod
    def _cross_entity_uuid_collisions(values: list[tuple[str, UUID]]) -> list[str]:
        entities_by_uuid: dict[UUID, set[str]] = {}
        for entity_kind, value in values:
            entities_by_uuid.setdefault(value, set()).add(entity_kind)
        collisions: list[str] = []
        for value in sorted(entities_by_uuid, key=str):
            entity_kinds = entities_by_uuid[value]
            if len(entity_kinds) > 1:
                collisions.append(f"{value} ({', '.join(sorted(entity_kinds))})")
        return collisions

    @staticmethod
    def _planned_definition_counts(
        definitions: dict[str, int], planned_control_ids: set[str]
    ) -> dict[str, int]:
        return {
            control_id: count
            for control_id, count in definitions.items()
            if control_id in planned_control_ids
        }

    @staticmethod
    def _is_unambiguous_target(definitions: dict[str, int]) -> bool:
        return len(definitions) == 1 and next(iter(definitions.values())) == 1

    @staticmethod
    def _validate_authored_evidence_href(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return "Evidence href must be a string when provided."
        if not value:
            return "Evidence href cannot be an empty string."
        if value != value.strip():
            return "Evidence href cannot contain leading or trailing whitespace."
        if value.startswith("#"):
            return (
                "Evidence href must be an absolute HTTP(S) URL; fragment-only references "
                "are not allowed."
            )
        if any(char.isspace() for char in value):
            return "Evidence href cannot contain whitespace characters."
        if "\\" in value:
            return "Evidence href cannot contain backslashes."
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            return "Evidence href cannot contain control characters."
        if AssessmentResultService._has_malformed_percent_encoding(value):
            return "Evidence href cannot contain malformed percent-encoding."

        try:
            parsed = urlsplit(value)
        except ValueError:
            return "Evidence href must be a syntactically valid URL."
        if parsed.scheme not in {"http", "https"}:
            return "Evidence href must use http or https."
        if parsed.fragment:
            return (
                "Evidence href must be an absolute HTTP(S) URL without a URL fragment. "
                "Use the full document URL instead."
            )
        if parsed.username is not None or parsed.password is not None:
            return "Evidence href cannot include embedded credentials."
        try:
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError:
            return "Evidence href must include a valid hostname and optional port."
        if not parsed.netloc or hostname is None:
            return "Evidence href must include a valid hostname."
        if AssessmentResultService._is_invalid_bracketed_host_literal(parsed.netloc):
            return "Evidence href must include a valid hostname."
        if not AssessmentResultService._is_valid_http_host(hostname):
            return "Evidence href must include a valid hostname."
        return None

    @staticmethod
    def _has_malformed_percent_encoding(value: str) -> bool:
        for index, char in enumerate(value):
            if char != "%":
                continue
            if index + 2 >= len(value):
                return True
            if not all(
                next_char in "0123456789ABCDEFabcdef"
                for next_char in value[index + 1 : index + 3]
            ):
                return True
        return False

    @staticmethod
    def _is_invalid_bracketed_host_literal(netloc: str) -> bool:
        if not netloc.startswith("["):
            return False
        closing_index = netloc.find("]")
        if closing_index == -1:
            return True
        host_literal = netloc[1:closing_index]
        remainder = netloc[closing_index + 1 :]
        if remainder and not remainder.startswith(":"):
            return True
        try:
            parsed = ip_address(host_literal)
        except ValueError:
            return True
        return parsed.version != 6

    @staticmethod
    def _is_valid_http_host(hostname: str) -> bool:
        if not hostname:
            return False
        if ":" in hostname:
            # IPv6 literals are normalized without brackets by urlsplit().
            try:
                ip_address(hostname)
                return True
            except ValueError:
                return False
        try:
            ip_address(hostname)
            return True
        except ValueError:
            pass
        if _IPV4_DOTTED_RE.fullmatch(hostname):
            return False

        ascii_host = hostname
        if ascii_host.endswith("."):
            ascii_host = ascii_host[:-1]
            if not ascii_host or ascii_host.endswith("."):
                return False
        if not ascii_host or len(ascii_host) > 253:
            return False
        if _IPV4_DOTTED_RE.fullmatch(ascii_host):
            return False
        return all(_HOST_LABEL_RE.fullmatch(label) for label in ascii_host.split("."))

    @staticmethod
    def _default_working_data(*, reviewed_control_ids: list[str]) -> dict[str, Any]:
        return {
            "reviewed_control_ids": reviewed_control_ids,
            "observations": [],
            "findings": [],
            "start": None,
            "end": None,
        }

    @staticmethod
    def _next_document_version(previous: str | None) -> str:
        if not previous:
            return "1.0"
        parts = previous.split(".")
        if len(parts) == 2 and all(item.isdigit() for item in parts):
            return f"{parts[0]}.{int(parts[1]) + 1}"
        return f"{previous}.1"

    @staticmethod
    def _oscal_diagnostic(error: AssessmentResultValidationError) -> dict[str, str]:
        code = "oscal_model" if error.category == "oscal_model" else "oscal_schema"
        diagnostic: dict[str, str] = {
            "severity": "error",
            "category": error.category,
            "code": code,
            "message": str(error),
        }
        if error.path:
            diagnostic["path"] = error.path
        return diagnostic

    def _result_payload(
        self, session: Session, record: AssessmentResultRecord
    ) -> dict[str, Any]:
        context = self._context_for_result(session, record)
        working = copy.deepcopy(record.working_data)
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "system_id": record.system_id,
            "assessment_plan_id": record.assessment_plan_id,
            "assessment_plan_version_id": record.assessment_plan_version_id,
            "title": record.title,
            "description": record.description,
            "planned_control_ids": context["planned_control_ids"],
            "reviewed_control_ids": working.get("reviewed_control_ids", []),
            "observations": working.get("observations", []),
            "findings": working.get("findings", []),
            "subject_options": context["subject_options"],
            "statement_options": context["statement_options"],
            "objective_options": context["objective_options"],
            "start": working.get("start"),
            "end": working.get("end"),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "concurrency_version": record.concurrency_version,
        }

    @staticmethod
    def _version_payload(
        record: AssessmentResultVersionRecord,
        *,
        created: bool,
        concurrency_version: int | None = None,
    ) -> dict[str, Any]:
        return {
            "id": record.id,
            "assessment_result_id": record.assessment_result_id,
            "assessment_plan_version_id": record.assessment_plan_version_id,
            "oscal_document_uuid": record.oscal_document_uuid,
            "oscal_version": record.oscal_version,
            "document_version": record.document_version,
            "last_modified": record.last_modified,
            "content_sha256": record.content_sha256,
            "diagnostics": record.diagnostics,
            "created_at": record.created_at,
            "created": created,
            "concurrency_version": concurrency_version,
        }

    @staticmethod
    def _subject_options(ssp_version: SystemSecurityPlanVersionRecord) -> list[dict[str, Any]]:
        body = ssp_version.document.get("system-security-plan", {})
        components = body.get("system-implementation", {}).get("components", [])
        options: list[dict[str, Any]] = []
        for component in components:
            if "uuid" not in component:
                continue
            options.append(
                {
                    "uuid": UUID(component["uuid"]),
                    "title": component.get("title") or component["uuid"],
                    "type": component.get("type") or "component",
                }
            )
        return options

    @staticmethod
    def _statement_controls(catalog_content: dict[str, Any]) -> dict[str, dict[str, int]]:
        controls_by_statement: dict[str, dict[str, int]] = {}

        def walk_controls(controls: list[dict[str, Any]]) -> None:
            for control in controls:
                control_id = control.get("id")
                if isinstance(control_id, str):
                    for part in control.get("parts", []):
                        if part.get("name") != "statement":
                            continue
                        statement_id = part.get("id")
                        if not isinstance(statement_id, str) or not statement_id:
                            continue
                        controls = controls_by_statement.setdefault(statement_id, {})
                        controls[control_id] = controls.get(control_id, 0) + 1
                walk_controls(control.get("controls", []))

        def walk_groups(groups: list[dict[str, Any]]) -> None:
            for group in groups:
                walk_controls(group.get("controls", []))
                walk_groups(group.get("groups", []))

        catalog = catalog_content.get("catalog", {})
        walk_controls(catalog.get("controls", []))
        walk_groups(catalog.get("groups", []))
        return controls_by_statement

    @staticmethod
    def _statement_options(
        statement_controls: dict[str, dict[str, int]], planned_control_ids: set[str]
    ) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []
        for statement_id in sorted(statement_controls):
            controls = AssessmentResultService._planned_definition_counts(
                statement_controls[statement_id], planned_control_ids
            )
            if not AssessmentResultService._is_unambiguous_target(controls):
                continue
            options.append(
                {
                    "statement_id": statement_id,
                    "control_id": next(iter(controls)),
                    "title": statement_id,
                }
            )
        return options

    @staticmethod
    def _catalog_objective_controls(catalog_content: dict[str, Any]) -> dict[str, dict[str, int]]:
        catalog_objectives: dict[str, dict[str, int]] = {}

        def walk_controls(controls: list[dict[str, Any]]) -> None:
            for control in controls:
                control_id = control.get("id")
                if isinstance(control_id, str):
                    for part in control.get("parts", []):
                        if part.get("name") != "objective":
                            continue
                        objective_id = part.get("id")
                        if isinstance(objective_id, str) and objective_id:
                            controls = catalog_objectives.setdefault(objective_id, {})
                            controls[control_id] = controls.get(control_id, 0) + 1
                    for objective in control.get("objectives", []):
                        objective_id = objective.get("objective-id") or objective.get("id")
                        if isinstance(objective_id, str) and objective_id:
                            controls = catalog_objectives.setdefault(objective_id, {})
                            controls[control_id] = controls.get(control_id, 0) + 1
                walk_controls(control.get("controls", []))

        def walk_groups(groups: list[dict[str, Any]]) -> None:
            for group in groups:
                walk_controls(group.get("controls", []))
                walk_groups(group.get("groups", []))

        catalog = catalog_content.get("catalog", {})
        walk_controls(catalog.get("controls", []))
        walk_groups(catalog.get("groups", []))
        return catalog_objectives

    @staticmethod
    def _objective_options(
        *,
        catalog_objective_controls: dict[str, dict[str, int]],
        selected_catalog_objective_ids: set[str],
        local_objective_controls: dict[str, str],
        planned_control_ids: set[str],
    ) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []

        for objective_id, control_id in sorted(local_objective_controls.items()):
            if control_id not in planned_control_ids:
                continue
            options.append(
                {
                    "objective_id": objective_id,
                    "control_id": control_id,
                    "title": objective_id,
                }
            )

        for objective_id in sorted(selected_catalog_objective_ids):
            if objective_id in local_objective_controls:
                continue
            controls = AssessmentResultService._planned_definition_counts(
                catalog_objective_controls.get(objective_id, {}), planned_control_ids
            )
            if not AssessmentResultService._is_unambiguous_target(controls):
                continue
            options.append(
                {
                    "objective_id": objective_id,
                    "control_id": next(iter(controls)),
                    "title": objective_id,
                }
            )
        return options

    @staticmethod
    def _plan_scope(plan_document: dict[str, Any]) -> dict[str, Any]:
        body = plan_document.get("assessment-plan", {})
        planned_control_ids = AssessmentResultService._plan_reviewed_control_ids_from_body(body)

        selected_catalog_objective_ids = {
            include["objective-id"]
            for selection in body.get("reviewed-controls", {}).get(
                "control-objective-selections", []
            )
            for include in selection.get("include-objectives", [])
            if include.get("objective-id")
        }

        local_objective_controls: dict[str, str] = {}
        for local in body.get("local-definitions", {}).get("objectives-and-methods", []):
            control_id = local.get("control-id")
            objective_id = None
            for part in local.get("parts", []):
                if part.get("name") == "objective" and part.get("id"):
                    objective_id = part["id"]
                    break
            if isinstance(objective_id, str) and isinstance(control_id, str):
                local_objective_controls[objective_id] = control_id

        selected_subject_uuids: list[UUID] = []
        for subject in body.get("assessment-subjects", []):
            include_subjects = subject.get("include-subjects", [])
            if not isinstance(include_subjects, list):
                continue
            for selected in include_subjects:
                subject_uuid = selected.get("subject-uuid")
                subject_type = selected.get("type") or subject.get("type")
                if subject_type != "component":
                    continue
                if not subject_uuid:
                    continue
                try:
                    parsed = UUID(str(subject_uuid))
                except ValueError:
                    continue
                if parsed not in selected_subject_uuids:
                    selected_subject_uuids.append(parsed)

        return {
            "planned_control_ids": planned_control_ids,
            "selected_catalog_objective_ids": selected_catalog_objective_ids,
            "local_objective_controls": local_objective_controls,
            "selected_subject_uuids": selected_subject_uuids,
        }

    @staticmethod
    def _plan_reviewed_control_ids_from_body(body: dict[str, Any]) -> list[str]:
        ids = []
        for selection in body.get("reviewed-controls", {}).get("control-selections", []):
            for include in selection.get("include-controls", []):
                control_id = include.get("control-id")
                if isinstance(control_id, str) and control_id not in ids:
                    ids.append(control_id)
        return ids

    @staticmethod
    def _plan_reviewed_control_ids(plan_version: AssessmentPlanVersionRecord) -> list[str]:
        body = plan_version.document.get("assessment-plan", {})
        return AssessmentResultService._plan_reviewed_control_ids_from_body(body)

    @staticmethod
    def _plan_href(record: AssessmentResultRecord) -> str:
        return (
            f"/api/v1/tenants/{record.tenant_id}/assessment-plans/"
            f"{record.assessment_plan_id}/versions/{record.assessment_plan_version_id}/export"
        )

    @staticmethod
    def _dt(value: datetime | str) -> str:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.astimezone(UTC).replace(microsecond=0).isoformat()

    @staticmethod
    def _get_system(
        session: Session, tenant_id: UUID, system_id: UUID
    ) -> InformationSystemRecord:
        system = session.scalar(
            select(InformationSystemRecord).where(
                InformationSystemRecord.tenant_id == tenant_id,
                InformationSystemRecord.id == system_id,
            )
        )
        if system is None:
            raise EntityNotFoundError("System not found.")
        return system

    @staticmethod
    def _get_plan(
        session: Session, tenant_id: UUID, plan_id: UUID
    ) -> AssessmentPlanRecord:
        plan = session.scalar(
            select(AssessmentPlanRecord).where(
                AssessmentPlanRecord.tenant_id == tenant_id,
                AssessmentPlanRecord.id == plan_id,
            )
        )
        if plan is None:
            raise EntityNotFoundError("Assessment Plan not found.")
        return plan

    @staticmethod
    def _get_plan_version(
        session: Session, tenant_id: UUID, plan_version_id: UUID
    ) -> AssessmentPlanVersionRecord:
        version = session.scalar(
            select(AssessmentPlanVersionRecord).where(
                AssessmentPlanVersionRecord.tenant_id == tenant_id,
                AssessmentPlanVersionRecord.id == plan_version_id,
            )
        )
        if version is None:
            raise EntityNotFoundError("Assessment Plan version not found.")
        return version

    @staticmethod
    def _get_ssp_version(
        session: Session, tenant_id: UUID, ssp_version_id: UUID
    ) -> SystemSecurityPlanVersionRecord:
        version = session.scalar(
            select(SystemSecurityPlanVersionRecord).where(
                SystemSecurityPlanVersionRecord.tenant_id == tenant_id,
                SystemSecurityPlanVersionRecord.id == ssp_version_id,
            )
        )
        if version is None:
            raise EntityNotFoundError("System Security Plan version not found.")
        return version

    @staticmethod
    def _get_revision(
        session: Session, tenant_id: UUID, catalog_id: UUID, revision_id: UUID
    ) -> CatalogRevisionRecord:
        revision = session.scalar(
            select(CatalogRevisionRecord).where(
                CatalogRevisionRecord.tenant_id == tenant_id,
                CatalogRevisionRecord.catalog_id == catalog_id,
                CatalogRevisionRecord.id == revision_id,
            )
        )
        if revision is None:
            raise EntityNotFoundError("Catalog revision not found.")
        return revision

    @staticmethod
    def _get_result(
        session: Session,
        tenant_id: UUID,
        result_id: UUID,
        *,
        lock: bool = False,
    ) -> AssessmentResultRecord:
        query = select(AssessmentResultRecord).where(
            AssessmentResultRecord.tenant_id == tenant_id,
            AssessmentResultRecord.id == result_id,
        )
        if lock:
            query = query.with_for_update()
        record = session.scalar(query)
        if record is None:
            raise EntityNotFoundError("Assessment Results record not found.")
        return record




