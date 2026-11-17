from __future__ import annotations

import re
from collections.abc import Mapping, Set
from typing import Any
from uuid import UUID

from jsonschema import Draft7Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError
from trestle.oscal.assessment_results import Model as TrestleAssessmentResultModel

from collaborative_oscal_oscal.authoring import (
    OscalAuthoringError,
    serialize_authored_document,
)
from collaborative_oscal_oscal.catalog_import import _OSCAL_DRAFT7_VALIDATOR
from collaborative_oscal_oscal.versions import (
    BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS,
    OscalDocumentModel,
    authoring_version_for,
    document_root_key,
    is_supported_oscal_version,
    load_oscal_schema,
    uses_trestle_model,
)

DEFAULT_ASSESSMENT_RESULT_OSCAL_VERSION = authoring_version_for(
    OscalDocumentModel.ASSESSMENT_RESULT
)


class AssessmentResultValidationError(ValueError):
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


def serialize_authored_assessment_result(document: Mapping[str, Any]) -> dict[str, Any]:
    try:
        root_key = document_root_key(OscalDocumentModel.ASSESSMENT_RESULT)
        version = document[root_key]["metadata"]["oscal-version"]
        if uses_trestle_model(OscalDocumentModel.ASSESSMENT_RESULT, version):
            return serialize_authored_document(
                TrestleAssessmentResultModel,
                document,
                OscalDocumentModel.ASSESSMENT_RESULT,
                version,
            )
        validate_assessment_result_document(document)
        return dict(document)
    except OscalAuthoringError as error:
        raise AssessmentResultValidationError(str(error)) from error


def validate_assessment_result_document(
    document: Mapping[str, Any],
    *,
    expected_assessment_plan_href: str | None = None,
    allowed_statement_ids: set[str] | None = None,
    allowed_objective_ids: set[str] | None = None,
    allowed_observation_methods: Set[str] | None = None,
) -> None:
    try:
        body = document[document_root_key(OscalDocumentModel.ASSESSMENT_RESULT)]
        version = body["metadata"]["oscal-version"]
        if not is_supported_oscal_version(OscalDocumentModel.ASSESSMENT_RESULT, version):
            raise AssessmentResultValidationError(
                "Unsupported OSCAL Assessment Results version."
            )
        if uses_trestle_model(OscalDocumentModel.ASSESSMENT_RESULT, version):
            TrestleAssessmentResultModel.model_validate(document)
        if version not in BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS and not uses_trestle_model(
            OscalDocumentModel.ASSESSMENT_RESULT, version
        ):
            raise AssessmentResultValidationError(
                "No validator is configured for the declared Assessment Results version."
            )
        if version in BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS:
            _OSCAL_DRAFT7_VALIDATOR(
                load_oscal_schema(OscalDocumentModel.ASSESSMENT_RESULT, version),
                format_checker=Draft7Validator.FORMAT_CHECKER,
            ).validate(document)

        if (
            expected_assessment_plan_href is not None
            and body["import-ap"]["href"] != expected_assessment_plan_href
        ):
            raise AssessmentResultValidationError(
                "Assessment Results import-ap reference does not match the pinned Assessment Plan version."
            )

        observations = _collect_observation_ids(body)
        _validate_method_policy(body, allowed_observation_methods=allowed_observation_methods)
        _validate_findings(
            body,
            observations=observations,
            allowed_statement_ids=allowed_statement_ids,
            allowed_objective_ids=allowed_objective_ids,
        )
    except AssessmentResultValidationError:
        raise
    except OSError as error:
        raise AssessmentResultValidationError(
            "The schema for the declared Assessment Results version is unavailable.",
            category="oscal_schema",
            reason="Schema resource unavailable.",
        ) from error
    except JsonSchemaValidationError as error:
        path = ".".join(str(item) for item in error.absolute_path) or "<root>"
        reason = _schema_reason(error)
        raise AssessmentResultValidationError(
            f"OSCAL Assessment Results schema validation failed at {path}: {reason}",
            category="oscal_schema",
            path=path,
            reason=reason,
        ) from error
    except PydanticValidationError as error:
        detail = _first_pydantic_error(error)
        path = detail["path"]
        reason = detail["reason"]
        raise AssessmentResultValidationError(
            f"OSCAL Assessment Results model validation failed at {path}: {reason}",
            category="oscal_model",
            path=path,
            reason=reason,
        ) from error
    except (KeyError, TypeError, ValueError) as error:
        path = _exception_path(error)
        reason = _exception_reason(error)
        raise AssessmentResultValidationError(
            f"OSCAL Assessment Results model validation failed at {path}: {reason}",
            category="oscal_model",
            path=path,
            reason=reason,
        ) from error


def _collect_observation_ids(body: Mapping[str, Any]) -> set[UUID]:
    observation_ids: set[UUID] = set()
    for result in body.get("results", []):
        for observation in result.get("observations", []):
            observation_uuid = UUID(observation["uuid"])
            if observation_uuid in observation_ids:
                raise AssessmentResultValidationError(
                    f"Observation UUID {observation['uuid']!r} must be unique."
                )
            observation_ids.add(observation_uuid)
    return observation_ids


def _validate_method_policy(
    body: Mapping[str, Any], *, allowed_observation_methods: Set[str] | None
) -> None:
    if allowed_observation_methods is None:
        return
    for result in body.get("results", []):
        for observation in result.get("observations", []):
            for method in observation.get("methods", []):
                if method not in allowed_observation_methods:
                    allowed = ", ".join(sorted(allowed_observation_methods))
                    raise AssessmentResultValidationError(
                        f"Observation method {method!r} is not allowed by application policy ({allowed})."
                    )


def _validate_findings(
    body: Mapping[str, Any],
    *,
    observations: set[UUID],
    allowed_statement_ids: set[str] | None,
    allowed_objective_ids: set[str] | None,
) -> None:
    finding_ids: set[UUID] = set()
    for result in body.get("results", []):
        for finding in result.get("findings", []):
            finding_uuid = UUID(finding["uuid"])
            if finding_uuid in finding_ids:
                raise AssessmentResultValidationError(
                    f"Finding UUID {finding['uuid']!r} must be unique."
                )
            finding_ids.add(finding_uuid)

            target = finding["target"]
            target_type = target["type"]
            target_id = target["target-id"]
            if target_type == "statement-id":
                if (
                    allowed_statement_ids is not None
                    and target_id not in allowed_statement_ids
                ):
                    raise AssessmentResultValidationError(
                        f"Finding target statement-id {target_id!r} is not in the pinned historical context."
                    )
            elif target_type == "objective-id":
                if (
                    allowed_objective_ids is not None
                    and target_id not in allowed_objective_ids
                ):
                    raise AssessmentResultValidationError(
                        f"Finding target objective-id {target_id!r} is not in the pinned Assessment Plan context."
                    )
            else:
                raise AssessmentResultValidationError(
                    "Finding target type must be statement-id or objective-id."
                )

            for related in finding.get("related-observations", []):
                observation_uuid = UUID(related["observation-uuid"])
                if observation_uuid not in observations:
                    raise AssessmentResultValidationError(
                        "Finding references an observation UUID that does not exist in this Assessment Results document."
                    )


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


