from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.assessment_result_routes import _handle_invalid, _handle_stale
from app.api.assessment_result_schemas import (
    AssessmentResultPublishInput,
    AssessmentResultWorkingInput,
)
from app.application.assessment_results import (
    InvalidAssessmentResult,
    StaleAssessmentResultUpdate,
)


def test_invalid_assessment_result_http_payload_preserves_diagnostic_paths() -> None:
    error = InvalidAssessmentResult(
        [
            {
                "severity": "error",
                "category": "application_integrity",
                "code": "invalid_evidence_href",
                "message": "Evidence href cannot contain malformed percent-encoding.",
                "path": "$.observations[0].evidence[0].href",
            }
        ]
    )

    response = _handle_invalid(error)

    assert response.status_code == 422
    assert response.detail == {
        "diagnostics": [
            {
                "severity": "error",
                "category": "application_integrity",
                "code": "invalid_evidence_href",
                "message": "Evidence href cannot contain malformed percent-encoding.",
                "path": "$.observations[0].evidence[0].href",
            }
        ]
    }


def test_stale_assessment_result_update_http_payload_is_stable() -> None:
    error = StaleAssessmentResultUpdate(uuid4(), expected_version=2, current_version=5)

    response = _handle_stale(error)

    assert response.status_code == 409
    assert response.detail == {
        "code": "stale_update",
        "result_id": str(error.result_id),
        "expected_version": 2,
        "current_version": 5,
    }


def test_assessment_result_working_input_requires_expected_version() -> None:
    with pytest.raises(ValidationError):
        AssessmentResultWorkingInput(
            title="Assessment Results",
            description=None,
            reviewed_control_ids=[],
            observations=[],
            findings=[],
            start=None,
            end=None,
        )


def test_assessment_result_publish_input_requires_expected_version() -> None:
    with pytest.raises(ValidationError):
        AssessmentResultPublishInput()

