# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import hashlib
from importlib.resources import files
from uuid import UUID

import pytest
from collaborative_oscal_oscal.assessment_plan import (
    AssessmentPlanValidationError,
    serialize_authored_assessment_plan,
    validate_assessment_plan_document,
)
from collaborative_oscal_oscal.versions import OscalDocumentModel, is_supported_oscal_version

SUBJECT_UUID = UUID("5982df36-a1d4-4c36-abd2-855adf953e00")
SSP_HREF = "https://example.test/systems/ssp-versions/1/export"


def _document() -> dict:
    return {
        "assessment-plan": {
            "uuid": "434d42c1-f134-468e-979c-988ee7e7b5ca",
            "metadata": {
                "title": "MFA assessment plan",
                "last-modified": "2026-01-02T03:04:05Z",
                "version": "1.0.0",
                "oscal-version": "1.2.1",
            },
            "import-ssp": {"href": SSP_HREF},
            "reviewed-controls": {
                "control-selections": [
                    {"include-controls": [{"control-id": "ac-1"}]}
                ]
            },
            "assessment-subjects": [
                {
                    "type": "component",
                    "include-subjects": [
                        {
                            "subject-uuid": str(SUBJECT_UUID),
                            "type": "component",
                        }
                    ],
                }
            ],
        }
    }


def test_assessment_plan_121_validation_accepts_document() -> None:
    validate_assessment_plan_document(
        _document(),
        expected_ssp_href=SSP_HREF,
        baseline_control_ids={"ac-1"},
        allowed_subject_uuids={SUBJECT_UUID},
    )


def test_assessment_plan_validation_rejects_unknown_baseline_control() -> None:
    with pytest.raises(AssessmentPlanValidationError, match="not in the pinned baseline"):
        validate_assessment_plan_document(
            _document(),
            expected_ssp_href=SSP_HREF,
            baseline_control_ids={"ac-2"},
            allowed_subject_uuids={SUBJECT_UUID},
        )


def test_assessment_plan_validation_rejects_subject_not_in_pinned_ssp() -> None:
    with pytest.raises(AssessmentPlanValidationError, match="not in the pinned SSP snapshot"):
        validate_assessment_plan_document(
            _document(),
            expected_ssp_href=SSP_HREF,
            baseline_control_ids={"ac-1"},
            allowed_subject_uuids={UUID("7ca6d00c-c42c-4a90-9383-1d6fbbd288a8")},
        )


def test_assessment_plan_validation_reports_model_path_for_empty_version() -> None:
    document = _document()
    document["assessment-plan"]["metadata"]["version"] = ""
    with pytest.raises(
        AssessmentPlanValidationError,
        match="assessment-plan.metadata.version",
    ) as error:
        validate_assessment_plan_document(document)
    assert error.value.category == "oscal_model"
    assert error.value.path == "assessment-plan.metadata.version"


def test_assessment_plan_local_objective_identity_uses_objective_part_id() -> None:
    document = _document()
    document["assessment-plan"]["reviewed-controls"][
        "control-objective-selections"
    ] = [{"include-objectives": [{"objective-id": "local-ac-1-1"}]}]
    document["assessment-plan"]["local-definitions"] = {
        "objectives-and-methods": [
            {
                "control-id": "ac-1",
                "description": "Assess local objective.",
                "parts": [
                    {
                        "id": "local-ac-1-1",
                        "name": "objective",
                        "prose": "Assess local objective.",
                    }
                ],
            }
        ]
    }
    validate_assessment_plan_document(
        document,
        expected_ssp_href=SSP_HREF,
        baseline_control_ids={"ac-1"},
        allowed_subject_uuids={SUBJECT_UUID},
    )


def test_assessment_plan_121_serialize_uses_trestle_path() -> None:
    serialized = serialize_authored_assessment_plan(_document())
    assert serialized["assessment-plan"]["metadata"]["oscal-version"] == "1.2.1"


def test_assessment_plan_support_matrix_includes_121() -> None:
    assert is_supported_oscal_version(OscalDocumentModel.ASSESSMENT_PLAN, "1.2.1")


def test_bundled_assessment_plan_schema_has_recorded_upstream_digest() -> None:
    schema = (
        files("collaborative_oscal_oscal")
        .joinpath("schemas", "oscal_assessment_plan_schema_v1.2.1.json")
        .read_bytes()
    )
    assert hashlib.sha256(schema).hexdigest() == (
        "0153e4e0414903c51c13732d4158d955630e33a3ef009d2691cf3e07336136f4"
    )



