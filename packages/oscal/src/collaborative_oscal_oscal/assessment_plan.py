from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from jsonschema import Draft7Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError
from trestle.oscal.assessment_plan import Model as TrestleAssessmentPlanModel

from collaborative_oscal_oscal.authoring import (
    OscalAuthoringError,
    serialize_authored_document,
)
from collaborative_oscal_oscal.catalog_import import _OSCAL_DRAFT7_VALIDATOR
from collaborative_oscal_oscal.versions import (
    BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS,
    OscalDocumentModel,
    authoring_version_for,
    is_supported_oscal_version,
    load_oscal_schema,
    uses_trestle_model,
)

DEFAULT_ASSESSMENT_PLAN_OSCAL_VERSION = authoring_version_for(
    OscalDocumentModel.ASSESSMENT_PLAN
)


class AssessmentPlanValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        category: str = "oscal_model",
        path: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.category = category
        self.path = path
        self.reason = reason
        super().__init__(message)


def serialize_authored_assessment_plan(document: Mapping[str, Any]) -> dict[str, Any]:
    try:
        version = document["assessment-plan"]["metadata"]["oscal-version"]
        if uses_trestle_model(OscalDocumentModel.ASSESSMENT_PLAN, version):
            return serialize_authored_document(
                TrestleAssessmentPlanModel,
                document,
                OscalDocumentModel.ASSESSMENT_PLAN,
                version,
            )
        validate_assessment_plan_document(document)
        return dict(document)
    except OscalAuthoringError as error:
        raise AssessmentPlanValidationError(str(error)) from error


def validate_assessment_plan_document(
    document: Mapping[str, Any],
    *,
    expected_ssp_href: str | None = None,
    baseline_control_ids: set[str] | None = None,
    allowed_subject_uuids: set[UUID] | None = None,
) -> None:
    try:
        body = document["assessment-plan"]
        version = body["metadata"]["oscal-version"]
        if not is_supported_oscal_version(OscalDocumentModel.ASSESSMENT_PLAN, version):
            raise AssessmentPlanValidationError(
                "Unsupported OSCAL Assessment Plan version."
            )
        if uses_trestle_model(OscalDocumentModel.ASSESSMENT_PLAN, version):
            TrestleAssessmentPlanModel.model_validate(document)
        if version not in BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS and not uses_trestle_model(
            OscalDocumentModel.ASSESSMENT_PLAN, version
        ):
            raise AssessmentPlanValidationError(
                "No validator is configured for the declared Assessment Plan version."
            )
        if version in BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS:
            _OSCAL_DRAFT7_VALIDATOR(
                load_oscal_schema(OscalDocumentModel.ASSESSMENT_PLAN, version),
                format_checker=Draft7Validator.FORMAT_CHECKER,
            ).validate(document)

        if expected_ssp_href is not None and body["import-ssp"]["href"] != expected_ssp_href:
            raise AssessmentPlanValidationError(
                "Assessment Plan import-ssp reference does not match the pinned SSP version."
            )

        objective_ids = _collect_objective_ids(body)
        reviewed_controls = body.get("reviewed-controls", {})
        _validate_reviewed_controls(reviewed_controls, baseline_control_ids)

        subject_ids = _collect_assessment_subject_ids(body)
        if allowed_subject_uuids is not None and not subject_ids.issubset(allowed_subject_uuids):
            unknown = sorted(str(item) for item in subject_ids - allowed_subject_uuids)
            raise AssessmentPlanValidationError(
                "Assessment subjects reference component UUIDs that are not in the pinned SSP snapshot: "
                + ", ".join(unknown)
            )

        activity_ids = _collect_activity_ids(body)
        role_ids, party_ids = _collect_role_party_ids(body)
        _validate_task_references(
            body,
            subject_ids=subject_ids,
            activity_ids=activity_ids,
            objective_ids=objective_ids,
            role_ids=role_ids,
            party_ids=party_ids,
        )
    except AssessmentPlanValidationError:
        raise
    except OSError as error:
        raise AssessmentPlanValidationError(
            "The schema for the declared Assessment Plan version is unavailable.",
            category="oscal_schema",
            reason="Schema resource unavailable.",
        ) from error
    except JsonSchemaValidationError as error:
        path = ".".join(str(item) for item in error.absolute_path) or "<root>"
        reason = _schema_reason(error)
        raise AssessmentPlanValidationError(
            f"OSCAL Assessment Plan schema validation failed at {path}: {reason}",
            category="oscal_schema",
            path=path,
            reason=reason,
        ) from error
    except PydanticValidationError as error:
        detail = _first_pydantic_error(error)
        path = detail["path"]
        reason = detail["reason"]
        raise AssessmentPlanValidationError(
            f"OSCAL Assessment Plan model validation failed at {path}: {reason}",
            category="oscal_model",
            path=path,
            reason=reason,
        ) from error
    except (KeyError, TypeError, ValueError) as error:
        path = _exception_path(error)
        reason = _exception_reason(error)
        raise AssessmentPlanValidationError(
            f"OSCAL Assessment Plan model validation failed at {path}: {reason}",
            category="oscal_model",
            path=path,
            reason=reason,
        ) from error


def _validate_reviewed_controls(
    reviewed_controls: Mapping[str, Any], baseline_control_ids: set[str] | None
) -> None:
    seen_controls: set[str] = set()
    for selection in reviewed_controls.get("control-selections", []):
        for include in selection.get("include-controls", []):
            control_id = include["control-id"]
            if baseline_control_ids is not None and control_id not in baseline_control_ids:
                raise AssessmentPlanValidationError(
                    f"Reviewed control {control_id!r} is not in the pinned baseline."
                )
            if control_id in seen_controls:
                raise AssessmentPlanValidationError(
                    f"Reviewed control {control_id!r} is selected more than once."
                )
            seen_controls.add(control_id)


def _collect_objective_ids(body: Mapping[str, Any]) -> set[str]:
    objective_ids: set[str] = set()
    for selection in body.get("reviewed-controls", {}).get(
        "control-objective-selections", []
    ):
        for include in selection.get("include-objectives", []):
            objective_id = include["objective-id"]
            if objective_id in objective_ids:
                raise AssessmentPlanValidationError(
                    f"Assessment objective {objective_id!r} is selected more than once."
                )
            objective_ids.add(objective_id)

    local_ids: set[str] = set()
    for objective in body.get("local-definitions", {}).get("objectives-and-methods", []):
        objective_id = _local_objective_identity(objective)
        if objective_id in local_ids:
            raise AssessmentPlanValidationError(
                f"Local objective identifier {objective_id!r} is defined more than once."
            )
        local_ids.add(objective_id)
    return objective_ids.union(local_ids)


def _local_objective_identity(objective: Mapping[str, Any]) -> str:
    for part in objective.get("parts", []):
        if part.get("name") == "objective" and part.get("id"):
            return str(part["id"])
    return str(objective["control-id"])


def _first_pydantic_error(error: PydanticValidationError) -> dict[str, str]:
    items = error.errors(include_url=False, include_input=False)
    if not items:
        return {"path": "<root>", "reason": "Model validation failed."}
    first = items[0]
    location = ".".join(str(item) for item in first.get("loc", ())) or "<root>"
    reason = str(first.get("msg", "Model validation failed."))
    return {"path": location, "reason": reason}


def _exception_path(error: Exception) -> str:
    if isinstance(error, KeyError):
        key = error.args[0] if error.args else "unknown"
        return f"<root>.{key}"
    return "<root>"


def _exception_reason(error: Exception) -> str:
    if isinstance(error, KeyError):
        key = error.args[0] if error.args else "unknown"
        return f"Missing required property {key!r}."
    if isinstance(error, TypeError):
        return "Unexpected value type encountered while reading the document."
    if isinstance(error, ValueError):
        return str(error) or "Invalid value encountered while reading the document."
    return "Model validation failed."


def _schema_reason(error: JsonSchemaValidationError) -> str:
    if error.validator == "required":
        match = re.search(r"'([^']+)' is a required property", error.message)
        if match:
            return f"Missing required property {match.group(1)!r}."
        return "Missing required property."
    if error.validator == "pattern":
        return "Value does not match the required pattern."
    if error.validator == "type":
        return "Value has an invalid type."
    if error.validator == "enum":
        return "Value is not one of the allowed options."
    return f"Schema constraint {error.validator!r} is not satisfied."


def _collect_assessment_subject_ids(body: Mapping[str, Any]) -> set[UUID]:
    ids: set[UUID] = set()
    for subject in body.get("assessment-subjects", []):
        for selected in subject.get("include-subjects", []):
            ids.add(UUID(selected["subject-uuid"]))
    return ids


def _collect_activity_ids(body: Mapping[str, Any]) -> set[UUID]:
    activity_ids: set[UUID] = set()
    for activity in body.get("local-definitions", {}).get("activities", []):
        activity_id = UUID(activity["uuid"])
        if activity_id in activity_ids:
            raise AssessmentPlanValidationError(
                f"Assessment activity UUID {activity['uuid']!r} must be unique."
            )
        activity_ids.add(activity_id)
    return activity_ids


def _collect_role_party_ids(body: Mapping[str, Any]) -> tuple[set[str], set[UUID]]:
    role_ids = {role["id"] for role in body.get("metadata", {}).get("roles", [])}
    party_ids = {
        UUID(party["uuid"])
        for party in body.get("metadata", {}).get("parties", [])
        if "uuid" in party
    }
    return role_ids, party_ids


def _validate_task_references(
    body: Mapping[str, Any],
    *,
    subject_ids: set[UUID],
    activity_ids: set[UUID],
    objective_ids: set[str],
    role_ids: set[str],
    party_ids: set[UUID],
) -> None:
    task_ids: set[UUID] = set()
    for task in body.get("tasks", []):
        task_id = UUID(task["uuid"])
        if task_id in task_ids:
            raise AssessmentPlanValidationError(
                f"Assessment task UUID {task['uuid']!r} must be unique."
            )
        task_ids.add(task_id)

        for associated in task.get("associated-activities", []):
            if UUID(associated["activity-uuid"]) not in activity_ids:
                raise AssessmentPlanValidationError(
                    f"Task references unknown activity UUID {associated['activity-uuid']!r}."
                )
            for subject in associated.get("subjects", []):
                resolved = {
                    UUID(selected["subject-uuid"])
                    for selected in subject.get("include-subjects", [])
                }
                if not resolved.issubset(subject_ids):
                    raise AssessmentPlanValidationError(
                        "Task-associated activity references unknown assessment subject UUIDs."
                    )
            for role in associated.get("responsible-roles", []):
                _validate_responsible_role(role, role_ids=role_ids, party_ids=party_ids)

        for subject in task.get("subjects", []):
            resolved = {
                UUID(selected["subject-uuid"])
                for selected in subject.get("include-subjects", [])
            }
            if not resolved.issubset(subject_ids):
                raise AssessmentPlanValidationError(
                    "Task references unknown assessment subject UUIDs."
                )

        for role in task.get("responsible-roles", []):
            _validate_responsible_role(role, role_ids=role_ids, party_ids=party_ids)

    for activity in body.get("local-definitions", {}).get("activities", []):
        related_controls = activity.get("related-controls", {})
        for objective_selection in related_controls.get("control-objective-selections", []):
            for selected in objective_selection.get("include-objectives", []):
                if selected["objective-id"] not in objective_ids:
                    raise AssessmentPlanValidationError(
                        f"Activity references unknown objective {selected['objective-id']!r}."
                    )


def _validate_responsible_role(
    role: Mapping[str, Any], *, role_ids: set[str], party_ids: set[UUID]
) -> None:
    role_id = role["role-id"]
    if role_id not in role_ids:
        raise AssessmentPlanValidationError(
            f"Responsible role reference {role_id!r} is not declared in metadata.roles."
        )
    for party_uuid in role.get("party-uuids", []):
        if UUID(party_uuid) not in party_ids:
            raise AssessmentPlanValidationError(
                "Responsible role references a party that is not declared in metadata.parties."
            )


