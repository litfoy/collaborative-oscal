from __future__ import annotations

import copy
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from collaborative_oscal_oscal.assessment_plan import (
    AssessmentPlanValidationError,
    serialize_authored_assessment_plan,
    validate_assessment_plan_document,
)
from collaborative_oscal_oscal.catalog_index import canonical_json_sha256
from collaborative_oscal_oscal.versions import (
    OscalDocumentModel,
    authoring_version_for,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.domain.errors import EntityNotFoundError
from app.persistence.models import (
    AssessmentPlanRecord,
    AssessmentPlanVersionRecord,
    CatalogControlIndexRecord,
    CatalogRevisionRecord,
    InformationSystemRecord,
    SystemSecurityPlanRecord,
    SystemSecurityPlanVersionRecord,
)

SessionScope = Callable[[], AbstractContextManager[Session]]


class InvalidAssessmentPlan(ValueError):
    def __init__(self, diagnostics: list[dict[str, str]]) -> None:
        self.diagnostics = diagnostics
        super().__init__(
            "The Assessment Plan working state is not ready to create a valid OSCAL version."
        )


class StaleAssessmentPlanUpdate(ValueError):
    def __init__(self, plan_id: UUID, expected_version: int, current_version: int) -> None:
        self.plan_id = plan_id
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__("The Assessment Plan changed after it was loaded.")


class AssessmentPlanService:
    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    def list_plans(self, tenant_id: UUID, system_id: UUID) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            self._get_system(session, tenant_id, system_id)
            plans = session.scalars(
                select(AssessmentPlanRecord)
                .where(
                    AssessmentPlanRecord.tenant_id == tenant_id,
                    AssessmentPlanRecord.system_id == system_id,
                )
                .order_by(AssessmentPlanRecord.updated_at.desc(), AssessmentPlanRecord.id)
            ).all()
            return [self._plan_payload(session, plan) for plan in plans]

    def create_plan(
        self,
        tenant_id: UUID,
        actor: UUID,
        system_id: UUID,
        *,
        ssp_version_id: UUID,
        title: str,
        description: str | None,
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            self._get_system(session, tenant_id, system_id)
            ssp_version = self._get_ssp_version(session, tenant_id, ssp_version_id)
            ssp = self._get_ssp(session, tenant_id, ssp_version.system_security_plan_id)
            if ssp.system_id != system_id:
                raise InvalidAssessmentPlan(
                    [
                        {
                            "code": "system_ssp_mismatch",
                            "message": "The selected SSP version does not belong to this System.",
                        }
                    ]
                )
            now = datetime.now(UTC)
            plan = AssessmentPlanRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                system_id=system_id,
                system_security_plan_id=ssp.id,
                system_security_plan_version_id=ssp_version.id,
                title=title.strip(),
                description=description,
                working_data=self._default_working_data(),
                created_by=actor,
                updated_by=actor,
                created_at=now,
                updated_at=now,
                concurrency_version=1,
            )
            session.add(plan)
            session.flush()
            return self._plan_payload(session, plan)

    def get_plan(self, tenant_id: UUID, plan_id: UUID) -> dict[str, Any]:
        with self._session_scope() as session:
            return self._plan_payload(session, self._get_plan(session, tenant_id, plan_id))

    def update_plan(
        self,
        tenant_id: UUID,
        actor: UUID,
        plan_id: UUID,
        *,
        expected_version: int,
        title: str,
        description: str | None,
        working_data: dict[str, Any],
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            plan = self._get_plan(session, tenant_id, plan_id, lock=True)
            if plan.concurrency_version != expected_version:
                raise StaleAssessmentPlanUpdate(plan.id, expected_version, plan.concurrency_version)

            normalized_working_data = self._normalize_working_data(
                working_data, previous=plan.working_data
            )
            self._validate_working_integrity(
                normalized_working_data,
                baseline_control_ids=self._baseline_control_ids(
                    session, tenant_id, plan.system_security_plan_version_id
                ),
                allowed_subject_uuids=self._ssp_subject_uuids(
                    self._get_ssp_version(session, tenant_id, plan.system_security_plan_version_id)
                ),
            )
            plan.title = title.strip()
            plan.description = description
            plan.working_data = copy.deepcopy(normalized_working_data)
            plan.updated_by = actor
            plan.updated_at = datetime.now(UTC)
            try:
                session.flush()
            except StaleDataError as error:
                current = session.scalar(
                    select(AssessmentPlanRecord.concurrency_version).where(
                        AssessmentPlanRecord.tenant_id == tenant_id,
                        AssessmentPlanRecord.id == plan_id,
                    )
                )
                raise StaleAssessmentPlanUpdate(
                    plan.id,
                    expected_version,
                    current if current is not None else plan.concurrency_version,
                ) from error
            return self._plan_payload(session, plan)

    def validate_plan(self, tenant_id: UUID, plan_id: UUID) -> dict[str, Any]:
        with self._session_scope() as session:
            plan = self._get_plan(session, tenant_id, plan_id)
            draft, diagnostics = self._build_draft(session, plan)
            source_objectives = self._source_objectives(session, plan)
            errors = [item for item in diagnostics if item["severity"] == "error"]
            return {
                "valid": len(errors) == 0,
                "diagnostics": diagnostics,
                "source_objectives": source_objectives,
                "oscal_candidate": draft,
            }

    def create_version(
        self, tenant_id: UUID, actor: UUID, plan_id: UUID, *, expected_version: int
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            plan = self._get_plan(session, tenant_id, plan_id, lock=True)
            if plan.concurrency_version != expected_version:
                raise StaleAssessmentPlanUpdate(plan.id, expected_version, plan.concurrency_version)

            draft, diagnostics = self._build_draft(session, plan)
            errors = [item for item in diagnostics if item["severity"] == "error"]
            if errors:
                raise InvalidAssessmentPlan(diagnostics)

            previous = session.scalars(
                select(AssessmentPlanVersionRecord)
                .where(
                    AssessmentPlanVersionRecord.tenant_id == tenant_id,
                    AssessmentPlanVersionRecord.assessment_plan_id == plan.id,
                )
                .order_by(AssessmentPlanVersionRecord.created_at.desc())
                .limit(1)
            ).first()
            version = self._next_document_version(previous.document_version if previous else None)
            now = datetime.now(UTC).replace(microsecond=0)
            body = draft["assessment-plan"]
            body["uuid"] = str(uuid4())
            body["metadata"]["last-modified"] = now.isoformat()
            body["metadata"]["version"] = version
            try:
                final_document = serialize_authored_assessment_plan(draft)
                validate_assessment_plan_document(
                    final_document,
                    expected_ssp_href=self._ssp_href(plan),
                    baseline_control_ids=self._baseline_control_ids(
                        session, tenant_id, plan.system_security_plan_version_id
                    ),
                    allowed_subject_uuids=self._ssp_subject_uuids(
                        self._get_ssp_version(
                            session, tenant_id, plan.system_security_plan_version_id
                        )
                    ),
                )
            except AssessmentPlanValidationError as error:
                diagnostics.append(self._oscal_diagnostic(error))
                raise InvalidAssessmentPlan(diagnostics) from error

            stable_document = copy.deepcopy(final_document)
            stable_body = stable_document["assessment-plan"]
            stable_body["uuid"] = ""
            stable_body["metadata"]["last-modified"] = ""
            stable_body["metadata"]["version"] = ""
            digest = canonical_json_sha256(stable_document)
            existing = session.scalar(
                select(AssessmentPlanVersionRecord).where(
                    AssessmentPlanVersionRecord.tenant_id == tenant_id,
                    AssessmentPlanVersionRecord.assessment_plan_id == plan.id,
                    AssessmentPlanVersionRecord.content_sha256 == digest,
                )
            )
            if existing is not None:
                return self._version_payload(existing, created=False)

            record = AssessmentPlanVersionRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                assessment_plan_id=plan.id,
                system_security_plan_version_id=plan.system_security_plan_version_id,
                oscal_document_uuid=UUID(final_document["assessment-plan"]["uuid"]),
                oscal_version=final_document["assessment-plan"]["metadata"]["oscal-version"],
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
            try:
                session.flush()
            except StaleDataError as error:
                current = session.scalar(
                    select(AssessmentPlanRecord.concurrency_version).where(
                        AssessmentPlanRecord.tenant_id == tenant_id,
                        AssessmentPlanRecord.id == plan_id,
                    )
                )
                raise StaleAssessmentPlanUpdate(
                    plan.id,
                    expected_version,
                    current if current is not None else plan.concurrency_version,
                ) from error
            return self._version_payload(record, created=True)

    def list_versions(self, tenant_id: UUID, plan_id: UUID) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            self._get_plan(session, tenant_id, plan_id)
            versions = session.scalars(
                select(AssessmentPlanVersionRecord)
                .where(
                    AssessmentPlanVersionRecord.tenant_id == tenant_id,
                    AssessmentPlanVersionRecord.assessment_plan_id == plan_id,
                )
                .order_by(
                    AssessmentPlanVersionRecord.created_at.desc(),
                    AssessmentPlanVersionRecord.id,
                )
            ).all()
            return [self._version_payload(version, created=False) for version in versions]

    def export_version(self, tenant_id: UUID, plan_id: UUID, version_id: UUID) -> dict[str, Any]:
        with self._session_scope() as session:
            version = session.scalar(
                select(AssessmentPlanVersionRecord).where(
                    AssessmentPlanVersionRecord.tenant_id == tenant_id,
                    AssessmentPlanVersionRecord.assessment_plan_id == plan_id,
                    AssessmentPlanVersionRecord.id == version_id,
                )
            )
            if version is None:
                raise EntityNotFoundError("Assessment Plan version not found.")
            return version.document

    def _build_draft(
        self, session: Session, plan: AssessmentPlanRecord
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        ssp_version = self._get_ssp_version(
            session, plan.tenant_id, plan.system_security_plan_version_id
        )
        baseline_control_ids = self._baseline_control_ids(
            session, plan.tenant_id, plan.system_security_plan_version_id
        )
        allowed_subject_uuids = self._ssp_subject_uuids(ssp_version)

        diagnostics: list[dict[str, str]] = []
        self._validate_working_integrity(
            plan.working_data,
            baseline_control_ids=baseline_control_ids,
            allowed_subject_uuids=allowed_subject_uuids,
        )

        now = datetime.now(UTC).replace(microsecond=0)
        oscal_version = authoring_version_for(OscalDocumentModel.ASSESSMENT_PLAN)
        source_objectives = self._source_objectives(session, plan)

        objective_ids = {
            entry["objective_id"] for entry in plan.working_data.get("source_objectives", [])
        }
        objective_ids.update(
            entry["objective_id"] for entry in plan.working_data.get("local_objectives", [])
        )
        selected_controls = list(dict.fromkeys(plan.working_data.get("control_ids", [])))
        reviewed_controls = {
            "control-selections": [
                {
                    "include-controls": [
                        {"control-id": control_id} for control_id in selected_controls
                    ]
                }
            ]
        }
        if objective_ids:
            reviewed_controls["control-objective-selections"] = [
                {
                    "include-objectives": [
                        {"objective-id": objective_id} for objective_id in sorted(objective_ids)
                    ]
                }
            ]

        metadata: dict[str, Any] = {
            "title": plan.title,
            "last-modified": now.isoformat(),
            "version": "draft",
            "oscal-version": oscal_version,
        }

        roles = plan.working_data.get("roles", [])
        parties = plan.working_data.get("parties", [])
        if roles:
            metadata["roles"] = [
                {
                    "id": role["role_id"],
                    "title": role["title"],
                    **({"description": role["description"]} if role.get("description") else {}),
                }
                for role in roles
            ]
        if parties:
            metadata["parties"] = [
                {
                    "uuid": str(party["uuid"]),
                    "type": party["party_type"],
                    "name": party["name"],
                }
                for party in parties
            ]

        local_definitions: dict[str, Any] = {}
        local_objectives = []
        for local in plan.working_data.get("local_objectives", []):
            methods = local.get("methods", [])
            parts = [{"name": "objective", "prose": local["description"]}]
            parts.extend(
                {
                    "name": "assessment-method",
                    "prose": method,
                }
                for method in methods
            )
            local_objectives.append(
                {
                    "control-id": local["control_id"],
                    "description": local["description"],
                    "parts": [{"id": local["objective_id"], **parts[0]}, *parts[1:]],
                }
            )
        if local_objectives:
            local_definitions["objectives-and-methods"] = local_objectives

        activities = []
        for activity in plan.working_data.get("activities", []):
            item: dict[str, Any] = {
                "uuid": str(activity["id"]),
                "title": activity["title"],
                "description": activity["description"],
            }
            methods = activity.get("methods", [])
            if methods:
                item["props"] = [
                    {
                        "name": "method",
                        "value": method,
                        "ns": "http://csrc.nist.gov/ns/oscal",
                    }
                    for method in methods
                ]
            if activity.get("planned_evidence"):
                item.setdefault("props", []).append(
                    {
                        "name": "planned-evidence",
                        "value": activity["planned_evidence"],
                        "ns": "http://csrc.nist.gov/ns/oscal",
                    }
                )
            steps = []
            for step in activity.get("steps", []):
                steps.append(
                    {
                        "uuid": str(step["id"]),
                        "title": step["title"],
                        "description": step["description"],
                    }
                )
            if steps:
                item["steps"] = steps
            control_ids = activity.get("control_ids", [])
            objective_refs = activity.get("objective_ids", [])
            if control_ids or objective_refs:
                related_controls: dict[str, Any] = {}
                if control_ids:
                    related_controls["control-selections"] = [
                        {
                            "include-controls": [
                                {"control-id": control_id} for control_id in control_ids
                            ]
                        }
                    ]
                if objective_refs:
                    related_controls["control-objective-selections"] = [
                        {
                            "include-objectives": [
                                {"objective-id": objective_id} for objective_id in objective_refs
                            ]
                        }
                    ]
                item["related-controls"] = related_controls
            activities.append(item)
        if activities:
            local_definitions["activities"] = activities

        assessment_subjects = []
        subject_uuids = plan.working_data.get("subject_uuids", [])
        if subject_uuids:
            assessment_subjects.append(
                {
                    "type": "component",
                    "include-subjects": [
                        {"subject-uuid": str(subject_uuid), "type": "component"}
                        for subject_uuid in subject_uuids
                    ],
                }
            )

        role_map = {item["role_id"]: item for item in roles}
        tasks = []
        for task in plan.working_data.get("tasks", []):
            task_entry: dict[str, Any] = {
                "uuid": str(task["id"]),
                "type": "action",
                "title": task["title"],
            }
            if task.get("description"):
                task_entry["description"] = task["description"]
            if task.get("on_date"):
                task_entry["timing"] = {"on-date": {"date": self._dt(task["on_date"])}}
            elif task.get("start") and task.get("end"):
                task_entry["timing"] = {
                    "within-date-range": {
                        "start": self._dt(task["start"]),
                        "end": self._dt(task["end"]),
                    }
                }

            role_refs = [
                self._responsible_role(role_map[item])
                for item in task.get("role_ids", [])
                if item in role_map
            ]
            if role_refs:
                task_entry["responsible-roles"] = role_refs

            subjects = self._subjects(task.get("subject_uuids", []))
            if subjects:
                task_entry["subjects"] = subjects

            activity_refs = []
            for activity_id in task.get("activity_ids", []):
                associated: dict[str, Any] = {"activity-uuid": str(activity_id)}
                if subjects:
                    associated["subjects"] = subjects
                if role_refs:
                    associated["responsible-roles"] = role_refs
                activity_refs.append(associated)
            if activity_refs:
                task_entry["associated-activities"] = activity_refs
            tasks.append(task_entry)

        terms = plan.working_data.get("terms")
        document: dict[str, Any] = {
            "assessment-plan": {
                "uuid": str(uuid4()),
                "metadata": metadata,
                "import-ssp": {"href": self._ssp_href(plan)},
                "reviewed-controls": reviewed_controls,
                **({"assessment-subjects": assessment_subjects} if assessment_subjects else {}),
                **({"local-definitions": local_definitions} if local_definitions else {}),
                **({"tasks": tasks} if tasks else {}),
                **(
                    {"terms-and-conditions": {"parts": [{"name": "conditions", "prose": terms}]}}
                    if terms
                    else {}
                ),
            }
        }

        try:
            validate_assessment_plan_document(
                document,
                expected_ssp_href=self._ssp_href(plan),
                baseline_control_ids=baseline_control_ids,
                allowed_subject_uuids=allowed_subject_uuids,
            )
        except AssessmentPlanValidationError as error:
            diagnostics.append(self._oscal_diagnostic(error))

        source_by_id = {item["objective_id"]: item for item in source_objectives}
        for selection in plan.working_data.get("source_objectives", []):
            selected = source_by_id.get(selection["objective_id"])
            if selected is None:
                diagnostics.append(
                    {
                        "severity": "error",
                        "category": "application_reference",
                        "code": "unknown_source_objective",
                        "message": (
                            "Selected source objective "
                            f"{selection['objective_id']!r} was not found in the pinned baseline."
                        ),
                    }
                )
                continue
            if selected["control_id"] != selection["control_id"]:
                diagnostics.append(
                    {
                        "severity": "error",
                        "category": "application_reference",
                        "code": "source_objective_control_mismatch",
                        "message": (
                            "Source objective "
                            f"{selection['objective_id']!r} belongs to control "
                            f"{selected['control_id']!r}, not {selection['control_id']!r}."
                        ),
                    }
                )

        return document, diagnostics

    def _validate_working_integrity(
        self,
        working_data: dict[str, Any],
        *,
        baseline_control_ids: set[str],
        allowed_subject_uuids: set[UUID],
    ) -> None:
        diagnostics: list[dict[str, str]] = []

        control_ids = [item for item in working_data.get("control_ids", []) if item]
        if len(control_ids) != len(set(control_ids)):
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_controls",
                    "message": "Reviewed controls must be unique.",
                }
            )
        unknown_controls = sorted(set(control_ids) - baseline_control_ids)
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

        subject_uuids = {UUID(str(item)) for item in working_data.get("subject_uuids", []) if item}
        missing_subjects = sorted(
            str(item) for item in subject_uuids if item not in allowed_subject_uuids
        )
        if missing_subjects:
            diagnostics.append(
                {
                    "category": "application_reference",
                    "code": "unknown_ssp_subject",
                    "message": (
                        "Assessment subjects are not present in the pinned SSP snapshot: "
                        + ", ".join(missing_subjects)
                    ),
                }
            )

        local_objective_ids = [
            item.get("objective_id") for item in working_data.get("local_objectives", [])
        ]
        source_objective_ids = [
            item.get("objective_id") for item in working_data.get("source_objectives", [])
        ]
        if len(local_objective_ids) != len(set(local_objective_ids)):
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_local_objectives",
                    "message": "Local objective identifiers must be unique.",
                }
            )
        conflicts = sorted(set(local_objective_ids).intersection(source_objective_ids))
        if conflicts:
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "objective_id_conflict",
                    "message": (
                        "Local objective identifiers conflict with selected source objectives: "
                        + ", ".join(conflicts)
                    ),
                }
            )

        objective_to_control = {
            item["objective_id"]: item["control_id"]
            for item in working_data.get("source_objectives", [])
        }
        objective_to_control.update(
            {
                item["objective_id"]: item["control_id"]
                for item in working_data.get("local_objectives", [])
            }
        )

        selected_controls = set(control_ids)
        for objective_id, control_id in objective_to_control.items():
            if control_id not in selected_controls:
                diagnostics.append(
                    {
                        "category": "application_reference",
                        "code": "objective_outside_scope",
                        "message": (
                            f"Objective {objective_id!r} references control {control_id!r} "
                            "outside the reviewed control scope."
                        ),
                    }
                )

        activity_ids = [
            UUID(str(item["id"])) for item in working_data.get("activities", []) if item.get("id")
        ]
        if len(activity_ids) != len(set(activity_ids)):
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_activity_ids",
                    "message": "Activity UUIDs must be unique.",
                }
            )

        role_ids = [item.get("role_id") for item in working_data.get("roles", [])]
        if len(role_ids) != len(set(role_ids)):
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_roles",
                    "message": "Assessment role identifiers must be unique.",
                }
            )

        party_ids = [UUID(str(item.get("uuid"))) for item in working_data.get("parties", [])]
        if len(party_ids) != len(set(party_ids)):
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_parties",
                    "message": "Assessment party UUIDs must be unique.",
                }
            )

        known_objectives = set(objective_to_control)
        known_activities = set(activity_ids)
        known_roles = set(role_ids)
        for activity in working_data.get("activities", []):
            unknown_refs = sorted(set(activity.get("objective_ids", [])) - known_objectives)
            if unknown_refs:
                diagnostics.append(
                    {
                        "category": "application_reference",
                        "code": "activity_unknown_objective",
                        "message": (
                            f"Activity {activity.get('id')} references unknown objectives: "
                            + ", ".join(unknown_refs)
                        ),
                    }
                )
            unknown_activity_controls = sorted(
                set(activity.get("control_ids", [])) - selected_controls
            )
            if unknown_activity_controls:
                diagnostics.append(
                    {
                        "category": "application_reference",
                        "code": "activity_control_outside_scope",
                        "message": (
                            f"Activity {activity.get('id')} references controls outside scope: "
                            + ", ".join(unknown_activity_controls)
                        ),
                    }
                )

        task_ids = [
            UUID(str(item["id"])) for item in working_data.get("tasks", []) if item.get("id")
        ]
        if len(task_ids) != len(set(task_ids)):
            diagnostics.append(
                {
                    "category": "application_integrity",
                    "code": "duplicate_task_ids",
                    "message": "Task UUIDs must be unique.",
                }
            )

        for task in working_data.get("tasks", []):
            unknown_task_activities = sorted(
                str(item)
                for item in {UUID(str(item)) for item in task.get("activity_ids", [])}
                if item not in known_activities
            )
            if unknown_task_activities:
                diagnostics.append(
                    {
                        "category": "application_reference",
                        "code": "task_unknown_activity",
                        "message": (
                            f"Task {task.get('id')} references unknown activities: "
                            + ", ".join(unknown_task_activities)
                        ),
                    }
                )
            unknown_task_subjects = sorted(
                str(item)
                for item in {UUID(str(subject)) for subject in task.get("subject_uuids", [])}
                if item not in subject_uuids
            )
            if unknown_task_subjects:
                diagnostics.append(
                    {
                        "category": "application_reference",
                        "code": "task_unknown_subject",
                        "message": (
                            f"Task {task.get('id')} references unknown subjects: "
                            + ", ".join(unknown_task_subjects)
                        ),
                    }
                )
            unknown_task_roles = sorted(set(task.get("role_ids", [])) - known_roles)
            if unknown_task_roles:
                diagnostics.append(
                    {
                        "category": "application_reference",
                        "code": "task_unknown_role",
                        "message": (
                            f"Task {task.get('id')} references unknown roles: "
                            + ", ".join(unknown_task_roles)
                        ),
                    }
                )

        if diagnostics:
            raise InvalidAssessmentPlan(
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
    def _oscal_diagnostic(error: AssessmentPlanValidationError) -> dict[str, str]:
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

    @staticmethod
    def _default_working_data() -> dict[str, Any]:
        return {
            "control_ids": [],
            "source_objectives": [],
            "local_objectives": [],
            "subject_uuids": [],
            "activities": [],
            "tasks": [],
            "roles": [],
            "parties": [],
            "terms": None,
        }

    @staticmethod
    def _normalize_working_data(
        working_data: dict[str, Any], *, previous: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        previous = previous or {}
        normalized = copy.deepcopy(working_data)

        preserved_step_ids: dict[tuple[str, int], str] = {}
        for previous_activity in previous.get("activities", []):
            activity_id = previous_activity.get("id")
            if not activity_id:
                continue
            for index, step in enumerate(previous_activity.get("steps", [])):
                step_id = step.get("id")
                if step_id:
                    preserved_step_ids[(str(activity_id), index)] = str(step_id)

        for activity in normalized.get("activities", []):
            if not activity.get("id"):
                activity["id"] = str(uuid4())
            activity_id = str(activity["id"])
            for index, step in enumerate(activity.get("steps", [])):
                if step.get("id"):
                    continue
                step["id"] = preserved_step_ids.get((activity_id, index), str(uuid4()))

        for task in normalized.get("tasks", []):
            if not task.get("id"):
                task["id"] = str(uuid4())

        preserved_parties: dict[tuple[str, str], str] = {}
        for party in previous.get("parties", []):
            party_type = party.get("party_type")
            party_name = party.get("name")
            party_uuid = party.get("uuid")
            if party_type and party_name and party_uuid:
                preserved_parties[(str(party_type), str(party_name))] = str(party_uuid)
        for party in normalized.get("parties", []):
            if party.get("uuid"):
                continue
            key = (str(party.get("party_type")), str(party.get("name")))
            party["uuid"] = preserved_parties.get(key, str(uuid4()))

        return normalized

    @staticmethod
    def _subjects(subject_uuids: list[UUID]) -> list[dict[str, Any]]:
        if not subject_uuids:
            return []
        return [
            {
                "type": "component",
                "include-subjects": [
                    {"subject-uuid": str(subject_uuid), "type": "component"}
                    for subject_uuid in subject_uuids
                ],
            }
        ]

    @staticmethod
    def _dt(value: datetime | str) -> str:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.astimezone(UTC).replace(microsecond=0).isoformat()

    @staticmethod
    def _responsible_role(role: dict[str, Any]) -> dict[str, Any]:
        item: dict[str, Any] = {"role-id": role["role_id"]}
        if role.get("party_uuids"):
            item["party-uuids"] = [str(entry) for entry in role["party_uuids"]]
        return item

    @staticmethod
    def _next_document_version(previous: str | None) -> str:
        if not previous:
            return "1.0"
        parts = previous.split(".")
        if len(parts) == 2 and all(item.isdigit() for item in parts):
            return f"{parts[0]}.{int(parts[1]) + 1}"
        return f"{previous}.1"

    def _plan_payload(self, session: Session, plan: AssessmentPlanRecord) -> dict[str, Any]:
        ssp_version = self._get_ssp_version(
            session, plan.tenant_id, plan.system_security_plan_version_id
        )
        working = copy.deepcopy(plan.working_data)
        return {
            "id": plan.id,
            "tenant_id": plan.tenant_id,
            "system_id": plan.system_id,
            "system_security_plan_id": plan.system_security_plan_id,
            "system_security_plan_version_id": plan.system_security_plan_version_id,
            "title": plan.title,
            "description": plan.description,
            "control_ids": working.get("control_ids", []),
            "source_objectives": working.get("source_objectives", []),
            "local_objectives": working.get("local_objectives", []),
            "subject_uuids": working.get("subject_uuids", []),
            "activities": working.get("activities", []),
            "tasks": working.get("tasks", []),
            "roles": working.get("roles", []),
            "parties": working.get("parties", []),
            "terms": working.get("terms"),
            "baseline_catalog_id": ssp_version.catalog_id,
            "baseline_revision_id": ssp_version.revision_id,
            "ssp_oscal_version": ssp_version.oscal_version,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
            "concurrency_version": plan.concurrency_version,
        }

    @staticmethod
    def _version_payload(record: AssessmentPlanVersionRecord, *, created: bool) -> dict[str, Any]:
        return {
            "id": record.id,
            "assessment_plan_id": record.assessment_plan_id,
            "system_security_plan_version_id": record.system_security_plan_version_id,
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
    def _ssp_href(plan: AssessmentPlanRecord) -> str:
        return (
            f"/api/v1/tenants/{plan.tenant_id}/system-security-plans/"
            f"{plan.system_security_plan_id}/versions/"
            f"{plan.system_security_plan_version_id}/export"
        )

    def _baseline_control_ids(
        self, session: Session, tenant_id: UUID, ssp_version_id: UUID
    ) -> set[str]:
        ssp_version = self._get_ssp_version(session, tenant_id, ssp_version_id)
        controls = session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id).where(
                CatalogControlIndexRecord.tenant_id == ssp_version.tenant_id,
                CatalogControlIndexRecord.catalog_revision_id == ssp_version.revision_id,
            )
        ).all()
        return set(controls)

    @staticmethod
    def _ssp_subject_uuids(ssp_version: SystemSecurityPlanVersionRecord) -> set[UUID]:
        body = ssp_version.document.get("system-security-plan", {})
        components = body.get("system-implementation", {}).get("components", [])
        return {UUID(component["uuid"]) for component in components if "uuid" in component}

    def _source_objectives(
        self, session: Session, plan: AssessmentPlanRecord
    ) -> list[dict[str, Any]]:
        ssp_version = self._get_ssp_version(
            session, plan.tenant_id, plan.system_security_plan_version_id
        )
        revision = self._get_revision(
            session, plan.tenant_id, ssp_version.catalog_id, ssp_version.revision_id
        )
        by_control = self._extract_catalog_objectives(revision.content)
        selected_controls = set(plan.working_data.get("control_ids", []))
        result: list[dict[str, Any]] = []
        for control_id, objectives in sorted(by_control.items()):
            if control_id not in selected_controls:
                continue
            for objective in objectives:
                result.append(objective)
        return result

    @staticmethod
    def _extract_catalog_objectives(content: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        by_control: dict[str, list[dict[str, Any]]] = {}
        catalog = content.get("catalog", {})

        def walk_controls(controls: list[dict[str, Any]]) -> None:
            for control in controls:
                control_id = control.get("id")
                if isinstance(control_id, str):
                    entries = by_control.setdefault(control_id, [])
                    for part in control.get("parts", []):
                        if part.get("name") != "objective":
                            continue
                        objective_id = part.get("id")
                        if not isinstance(objective_id, str) or not objective_id:
                            continue
                        entries.append(
                            {
                                "objective_id": objective_id,
                                "control_id": control_id,
                                "title": part.get("title") or objective_id,
                                "description": part.get("prose"),
                            }
                        )
                    for objective in control.get("objectives", []):
                        objective_id = objective.get("objective-id") or objective.get("id")
                        if not isinstance(objective_id, str) or not objective_id:
                            continue
                        entries.append(
                            {
                                "objective_id": objective_id,
                                "control_id": control_id,
                                "title": objective.get("title") or objective_id,
                                "description": objective.get("description"),
                            }
                        )
                walk_controls(control.get("controls", []))

        def walk_groups(groups: list[dict[str, Any]]) -> None:
            for group in groups:
                walk_controls(group.get("controls", []))
                walk_groups(group.get("groups", []))

        walk_controls(catalog.get("controls", []))
        walk_groups(catalog.get("groups", []))

        deduped: dict[str, list[dict[str, Any]]] = {}
        for control_id, objectives in by_control.items():
            seen: set[str] = set()
            unique = []
            for objective in objectives:
                objective_id = objective["objective_id"]
                if objective_id in seen:
                    continue
                seen.add(objective_id)
                unique.append(objective)
            deduped[control_id] = unique
        return deduped

    @staticmethod
    def _get_system(session: Session, tenant_id: UUID, system_id: UUID) -> InformationSystemRecord:
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
    def _get_ssp(
        session: Session, tenant_id: UUID, system_security_plan_id: UUID
    ) -> SystemSecurityPlanRecord:
        plan = session.scalar(
            select(SystemSecurityPlanRecord).where(
                SystemSecurityPlanRecord.tenant_id == tenant_id,
                SystemSecurityPlanRecord.id == system_security_plan_id,
            )
        )
        if plan is None:
            raise EntityNotFoundError("System Security Plan not found.")
        return plan

    @staticmethod
    def _get_ssp_version(
        session: Session,
        tenant_id: UUID,
        ssp_version_id: UUID,
    ) -> SystemSecurityPlanVersionRecord:
        record = session.scalar(
            select(SystemSecurityPlanVersionRecord).where(
                SystemSecurityPlanVersionRecord.tenant_id == tenant_id,
                SystemSecurityPlanVersionRecord.id == ssp_version_id,
            )
        )
        if record is None:
            raise EntityNotFoundError("System Security Plan version not found.")
        return record

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
    def _get_plan(
        session: Session, tenant_id: UUID, plan_id: UUID, *, lock: bool = False
    ) -> AssessmentPlanRecord:
        query = select(AssessmentPlanRecord).where(
            AssessmentPlanRecord.tenant_id == tenant_id,
            AssessmentPlanRecord.id == plan_id,
        )
        if lock:
            query = query.with_for_update()
        plan = session.scalar(query)
        if plan is None:
            raise EntityNotFoundError("Assessment Plan not found.")
        return plan
