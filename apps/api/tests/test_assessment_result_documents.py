from __future__ import annotations

import hashlib
from importlib.resources import files
from uuid import UUID

import pytest
from collaborative_oscal_oscal.assessment_result import (
    AssessmentResultValidationError,
    serialize_authored_assessment_result,
    validate_assessment_result_document,
)
from collaborative_oscal_oscal.versions import OscalDocumentModel, is_supported_oscal_version

OBSERVATION_UUID = UUID("f38a0399-5dd6-4ca9-a18e-2fffcf54a17b")
ASSESSMENT_PLAN_HREF = "https://example.test/systems/ap-versions/1/export"


def _document() -> dict:
    return {
        "assessment-results": {
            "uuid": "5da67f0f-4b2f-4f8f-9328-ca6f460f7f77",
            "metadata": {
                "title": "MFA assessment results",
                "last-modified": "2026-01-02T03:04:05Z",
                "version": "1.0.0",
                "oscal-version": "1.2.1",
            },
            "import-ap": {"href": ASSESSMENT_PLAN_HREF},
            "results": [
                {
                    "uuid": "aa4fce06-4890-4a03-80aa-450c204f7fd8",
                    "title": "Sprint 1",
                    "description": "Initial execution result.",
                    "start": "2026-01-01T00:00:00Z",
                    "end": "2026-01-02T00:00:00Z",
                    "reviewed-controls": {
                        "control-selections": [
                            {"include-controls": [{"control-id": "ac-1"}]}
                        ]
                    },
                    "observations": [
                        {
                            "uuid": str(OBSERVATION_UUID),
                            "title": "MFA challenge observed",
                            "description": "MFA challenge is enforced for privileged login.",
                            "methods": ["EXAMINE"],
                            "collected": "2026-01-01T12:00:00Z",
                            "subjects": [
                                {
                                    "type": "component",
                                    "subject-uuid": "5982df36-a1d4-4c36-abd2-855adf953e00",
                                }
                            ],
                        }
                    ],
                    "findings": [
                        {
                            "uuid": "fb68f670-f7e7-41e8-9faf-6c5e5cae057e",
                            "title": "AC-1 statement coverage",
                            "description": "Statement is implemented and evidenced.",
                            "target": {
                                "type": "statement-id",
                                "target-id": "ac-1_smt",
                                "status": {"state": "satisfied"},
                            },
                            "related-observations": [
                                {"observation-uuid": str(OBSERVATION_UUID)}
                            ],
                        }
                    ],
                }
            ],
        }
    }


def test_assessment_result_121_validation_accepts_document() -> None:
    validate_assessment_result_document(
        _document(),
        expected_assessment_plan_href=ASSESSMENT_PLAN_HREF,
        allowed_statement_ids={"ac-1_smt"},
        allowed_observation_methods={"EXAMINE", "INTERVIEW", "TEST"},
    )


def test_assessment_result_validation_rejects_unknown_related_observation() -> None:
    document = _document()
    document["assessment-results"]["results"][0]["findings"][0]["related-observations"] = [
        {"observation-uuid": "85c44090-907c-49b9-bbc5-5a9f3374f032"}
    ]
    with pytest.raises(AssessmentResultValidationError, match="does not exist"):
        validate_assessment_result_document(document)


def test_assessment_result_validation_rejects_statement_outside_pinned_context() -> None:
    with pytest.raises(AssessmentResultValidationError, match="pinned historical context"):
        validate_assessment_result_document(
            _document(),
            allowed_statement_ids={"ac-2_smt"},
        )


def test_assessment_result_validation_rejects_disallowed_observation_method() -> None:
    document = _document()
    document["assessment-results"]["results"][0]["observations"][0]["methods"] = ["SCAN"]
    with pytest.raises(AssessmentResultValidationError, match="not allowed by application policy"):
        validate_assessment_result_document(
            document,
            allowed_observation_methods={"EXAMINE", "INTERVIEW", "TEST"},
        )


def test_assessment_result_validation_rejects_unknown_objective_in_pinned_plan() -> None:
    document = _document()
    document["assessment-results"]["results"][0]["findings"][0]["target"] = {
        "type": "objective-id",
        "target-id": "local-ac-1-1",
        "status": {"state": "satisfied"},
    }
    with pytest.raises(AssessmentResultValidationError, match="pinned Assessment Plan context"):
        validate_assessment_result_document(
            document,
            allowed_objective_ids={"local-ac-2-1"},
        )


def test_assessment_result_121_serialize_uses_trestle_path() -> None:
    serialized = serialize_authored_assessment_result(_document())
    assert serialized["assessment-results"]["metadata"]["oscal-version"] == "1.2.1"


def test_assessment_result_support_matrix_includes_121() -> None:
    assert is_supported_oscal_version(OscalDocumentModel.ASSESSMENT_RESULT, "1.2.1")


def test_bundled_assessment_result_schema_has_recorded_upstream_digest() -> None:
    schema = (
        files("collaborative_oscal_oscal")
        .joinpath("schemas", "oscal_assessment_result_schema_v1.2.1.json")
        .read_bytes()
    )
    assert hashlib.sha256(schema).hexdigest() == (
        "4f9e277a177adbcca9527612ce450a33dc6096773fa229d413d801d196c61985"
    )


