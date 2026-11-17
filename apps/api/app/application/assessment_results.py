from __future__ import annotations

import copy
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any
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

from app.domain.errors import EntityNotFoundError
from app.persistence.models import (
    AssessmentPlanRecord,
    AssessmentPlanVersionRecord,
    AssessmentResultRecord,
    AssessmentResultVersionRecord,
    CatalogControlIndexRecord,
    CatalogRevisionRecord,
    InformationSystemRecord,
    SystemSecurityPlanVersionRecord,
)

SessionScope = Callable[[], AbstractContextManager[Session]]
_ALLOWED_METHODS = frozenset({"EXAMINE", "INTERVIEW", "TEST"})


class InvalidAssessmentResult(ValueError):
    def __init__(self, diagnostics: list[dict[str, str]]) -> None:
        self.diagnostics = diagnostics
        super().__init__(
            "The Assessment Results working state is not ready to create a valid OSCAL version."
        )


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
        title: str,
        description: str | None,
        working_data: dict[str, Any],
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            record = self._get_result(session, tenant_id, result_id, lock=True)
            context = self._context_for_result(session, record)
            normalized = self._normalize_working_data(working_data, previous=record.working_data)
            self._validate_working_integrity(
                normalized,
                baseline_control_ids=context["baseline_control_ids"],
                allowed_subject_uuids=context["subject_uuid_set"],
                allowed_statement_ids=context["statement_id_set"],
                allowed_objective_ids=context["objective_id_set"],
            )
            record.title = title.strip()
            record.description = description
            record.working_data = copy.deepcopy(normalized)
            record.updated_by = actor
            record.updated_at = datetime.now(UTC)
            session.flush()
            return self._result_payload(session, record)

    def validate_result(self, tenant_id: UUID, result_id: UUID) -> dict[str, Any]:
        with self._session_scope() as session:
            record = self._get_result(session, tenant_id, result_id)
            draft, diagnostics, context = self._build_draft(session, record)
            errors = [item for item in diagnostics if item["severity"] == "error"]
            return {
                "valid": len(errors) == 0,
                "diagnostics": diagnostics,
                "statement_options": context["statement_options"],
                "objective_options": context["objective_options"],
                "subject_options": context["subject_options"],
                "oscal_candidate": draft,
            }

    def create_version(
        self, tenant_id: UUID, actor: UUID, result_id: UUID
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            record = self._get_result(session, tenant_id, result_id, lock=True)
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
                return self._version_payload(existing, created=False)

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
            session.flush()
            return self._version_payload(snapshot, created=True)

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

        self._validate_working_integrity(
            record.working_data,
            baseline_control_ids=context["baseline_control_ids"],
            allowed_subject_uuids=context["subject_uuid_set"],
            allowed_statement_ids=context["statement_id_set"],
            allowed_objective_ids=context["objective_id_set"],
        )

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
        subject_uuid_set = {
            item["uuid"] if isinstance(item["uuid"], UUID) else UUID(str(item["uuid"]))
            for item in subject_options
        }

        statement_options = self._statement_options(revision.content)
        statement_id_set = {item["statement_id"] for item in statement_options}

        objective_options = self._objective_options(plan_version.document, revision.content)
        objective_id_set = {item["objective_id"] for item in objective_options}

        baseline_control_ids = self._baseline_control_ids(
            session, record.tenant_id, ssp_version.revision_id
        )

        return {
            "subject_options": subject_options,
            "subject_uuid_set": subject_uuid_set,
            "statement_options": statement_options,
            "statement_id_set": statement_id_set,
            "objective_options": objective_options,
            "objective_id_set": objective_id_set,
            "baseline_control_ids": baseline_control_ids,
        }

    def _validate_working_integrity(
        self,
        working_data: dict[str, Any],
        *,
        baseline_control_ids: set[str],
        allowed_subject_uuids: set[UUID],
        allowed_statement_ids: set[str],
        allowed_objective_ids: set[str],
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
        unknown_controls = sorted(set(reviewed_control_ids) - baseline_control_ids)
        if unknown_controls:
            diagnostics.append(
                {
                    "category": "application_reference",
                    "code": "control_outside_baseline",
                    "message": (
                        "Reviewed controls are outside the pinned baseline: "
                        + ", ".join(unknown_controls)
                    ),
                }
            )

        observation_ids: list[UUID] = []
        for observation in working_data.get("observations", []):
            observation_id = UUID(str(observation["id"]))
            observation_ids.append(observation_id)
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
                            "Observations reference subjects outside the pinned SSP snapshot: "
                            + ", ".join(missing)
                        ),
                    }
                )

            evidence_ids = [UUID(str(item["id"])) for item in observation.get("evidence", [])]
            if len(evidence_ids) != len(set(evidence_ids)):
                diagnostics.append(
                    {
                        "category": "application_integrity",
                        "code": "duplicate_evidence_ids",
                        "message": "Evidence UUIDs must be unique per observation.",
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
        for finding in working_data.get("findings", []):
            finding_id = UUID(str(finding["id"]))
            finding_ids.append(finding_id)

            target_type = finding["target_type"]
            target_id = str(finding["target_id"])
            if target_type == "statement-id" and target_id not in allowed_statement_ids:
                diagnostics.append(
                    {
                        "category": "application_reference",
                        "code": "unknown_statement_target",
                        "message": (
                            "Finding target statement-id "
                            f"{target_id!r} is outside the pinned historical baseline."
                        ),
                    }
                )
            if target_type == "objective-id" and target_id not in allowed_objective_ids:
                diagnostics.append(
                    {
                        "category": "application_reference",
                        "code": "unknown_objective_target",
                        "message": (
                            "Finding target objective-id "
                            f"{target_id!r} is outside the pinned Assessment Plan context."
                        ),
                    }
                )
            if target_type not in {"statement-id", "objective-id"}:
                diagnostics.append(
                    {
                        "category": "application_integrity",
                        "code": "invalid_target_type",
                        "message": "Finding target type must be statement-id or objective-id.",
                    }
                )

            related = {
                UUID(str(item)) for item in finding.get("related_observation_ids", []) if item
            }
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

        if diagnostics:
            raise InvalidAssessmentResult(
                [
                    {
                        "severity": "error",
                        "category": item["category"],
                        "code": item["code"],
                        "message": item["message"],
                    }
                    for item in diagnostics
                ]
            )

    @staticmethod
    def _normalize_working_data(
        working_data: dict[str, Any], *, previous: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        previous = previous or {}
        normalized = copy.deepcopy(working_data)

        previous_observations = previous.get("observations", [])
        for index, observation in enumerate(normalized.get("observations", [])):
            if not observation.get("id"):
                preserved = (
                    previous_observations[index].get("id")
                    if index < len(previous_observations)
                    else None
                )
                observation["id"] = preserved or str(uuid4())
            previous_evidence = (
                previous_observations[index].get("evidence", [])
                if index < len(previous_observations)
                else []
            )
            for evidence_index, evidence in enumerate(observation.get("evidence", [])):
                if evidence.get("id"):
                    continue
                preserved = (
                    previous_evidence[evidence_index].get("id")
                    if evidence_index < len(previous_evidence)
                    else None
                )
                evidence["id"] = preserved or str(uuid4())

        previous_findings = previous.get("findings", [])
        for index, finding in enumerate(normalized.get("findings", [])):
            if finding.get("id"):
                continue
            preserved = (
                previous_findings[index].get("id") if index < len(previous_findings) else None
            )
            finding["id"] = preserved or str(uuid4())

        return normalized

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
        }

    @staticmethod
    def _version_payload(
        record: AssessmentResultVersionRecord, *, created: bool
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
    def _statement_options(catalog_content: dict[str, Any]) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []
        by_id: set[str] = set()

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
                        if statement_id in by_id:
                            continue
                        by_id.add(statement_id)
                        options.append(
                            {
                                "statement_id": statement_id,
                                "control_id": control_id,
                                "title": part.get("title") or statement_id,
                            }
                        )
                walk_controls(control.get("controls", []))

        def walk_groups(groups: list[dict[str, Any]]) -> None:
            for group in groups:
                walk_controls(group.get("controls", []))
                walk_groups(group.get("groups", []))

        catalog = catalog_content.get("catalog", {})
        walk_controls(catalog.get("controls", []))
        walk_groups(catalog.get("groups", []))
        return options

    @staticmethod
    def _objective_options(
        plan_document: dict[str, Any], catalog_content: dict[str, Any]
    ) -> list[dict[str, Any]]:
        body = plan_document.get("assessment-plan", {})

        catalog_objectives: dict[str, str] = {}

        def walk_controls(controls: list[dict[str, Any]]) -> None:
            for control in controls:
                control_id = control.get("id")
                if isinstance(control_id, str):
                    for part in control.get("parts", []):
                        if part.get("name") != "objective":
                            continue
                        objective_id = part.get("id")
                        if isinstance(objective_id, str) and objective_id:
                            catalog_objectives[objective_id] = control_id
                    for objective in control.get("objectives", []):
                        objective_id = objective.get("objective-id") or objective.get("id")
                        if isinstance(objective_id, str) and objective_id:
                            catalog_objectives[objective_id] = control_id
                walk_controls(control.get("controls", []))

        def walk_groups(groups: list[dict[str, Any]]) -> None:
            for group in groups:
                walk_controls(group.get("controls", []))
                walk_groups(group.get("groups", []))

        catalog = catalog_content.get("catalog", {})
        walk_controls(catalog.get("controls", []))
        walk_groups(catalog.get("groups", []))

        local_objectives: dict[str, str] = {}
        for local in body.get("local-definitions", {}).get("objectives-and-methods", []):
            control_id = local.get("control-id")
            objective_id = None
            for part in local.get("parts", []):
                if part.get("name") == "objective" and part.get("id"):
                    objective_id = part["id"]
                    break
            if isinstance(objective_id, str) and isinstance(control_id, str):
                local_objectives[objective_id] = control_id

        reviewed_ids = {
            include["objective-id"]
            for selection in body.get("reviewed-controls", {}).get(
                "control-objective-selections", []
            )
            for include in selection.get("include-objectives", [])
            if include.get("objective-id")
        }

        options: list[dict[str, Any]] = []
        for objective_id in sorted(reviewed_ids.union(local_objectives)):
            control_id = local_objectives.get(objective_id) or catalog_objectives.get(
                objective_id, "unknown"
            )
            options.append(
                {
                    "objective_id": objective_id,
                    "control_id": control_id,
                    "title": objective_id,
                }
            )
        return options

    @staticmethod
    def _plan_reviewed_control_ids(plan_version: AssessmentPlanVersionRecord) -> list[str]:
        body = plan_version.document.get("assessment-plan", {})
        ids = []
        for selection in body.get("reviewed-controls", {}).get("control-selections", []):
            for include in selection.get("include-controls", []):
                control_id = include.get("control-id")
                if isinstance(control_id, str) and control_id not in ids:
                    ids.append(control_id)
        return ids

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

    def _baseline_control_ids(
        self, session: Session, tenant_id: UUID, revision_id: UUID
    ) -> set[str]:
        controls = session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id).where(
                CatalogControlIndexRecord.tenant_id == tenant_id,
                CatalogControlIndexRecord.catalog_revision_id == revision_id,
            )
        ).all()
        return set(controls)

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




