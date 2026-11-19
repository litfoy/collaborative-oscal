from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.assessment_plan_routes import _handle_stale
from app.api.assessment_plan_schemas import (
    AssessmentPlanPublishInput,
    AssessmentPlanWorkingInput,
)
from app.application.assessment_plans import StaleAssessmentPlanUpdate


def test_stale_assessment_plan_update_http_payload_is_stable() -> None:
    error = StaleAssessmentPlanUpdate(uuid4(), expected_version=3, current_version=5)

    response = _handle_stale(error)

    assert response.status_code == 409
    assert response.detail == {
        "code": "stale_update",
        "plan_id": str(error.plan_id),
        "expected_version": 3,
        "current_version": 5,
    }


def test_assessment_plan_working_input_requires_expected_version() -> None:
    with pytest.raises(ValidationError):
        AssessmentPlanWorkingInput(
            title="Assessment",
            description=None,
            control_ids=[],
            source_objectives=[],
            local_objectives=[],
            subject_uuids=[],
            activities=[],
            tasks=[],
            roles=[],
            parties=[],
            terms=None,
        )


def test_assessment_plan_publish_input_requires_expected_version() -> None:
    with pytest.raises(ValidationError):
        AssessmentPlanPublishInput()

