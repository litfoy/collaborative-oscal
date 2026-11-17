from app.api.assessment_result_routes import _handle_invalid
from app.application.assessment_results import InvalidAssessmentResult


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

