from __future__ import annotations

import hashlib
from importlib.resources import files
from uuid import UUID

import pytest
from collaborative_oscal_oscal.system_security_plan import (
    SystemSecurityPlanValidationError,
    serialize_authored_system_security_plan,
    validate_system_security_plan_document,
)
from collaborative_oscal_oscal.versions import (
    OscalDocumentModel,
    authoring_version_for_component_types,
    is_supported_oscal_version,
    uses_trestle_model,
)

SYSTEM_UUID = UUID("434d42c1-f134-468e-979c-988ee7e7b5ca")
COMPONENT_UUID = UUID("5982df36-a1d4-4c36-abd2-855adf953e00")
REQUIREMENT_UUID = UUID("b1cf7c58-f952-4c13-96a1-6e39d15912fc")
CONTRIBUTION_UUID = UUID("e4658924-68d8-4564-b3bc-b22972d74ab4")
INFORMATION_TYPE_UUID = UUID("d893f36f-66bb-4a43-827f-135a15553318")
UNKNOWN_COMPONENT_UUID = UUID("7ca6d00c-c42c-4a90-9383-1d6fbbd288a8")
PARTY_UUID = UUID("2adffec3-319a-41fa-8403-8dbdf6cbbd55")
UNKNOWN_PARTY_UUID = UUID("8e5fa085-149b-4931-90c9-091d3c014fb2")
CATALOG_HREF = "https://example.test/catalogs/security/revisions/1"


def _document() -> dict:
    return {
        "system-security-plan": {
            "uuid": str(SYSTEM_UUID),
            "metadata": {
                "title": "Enterprise identity",
                "last-modified": "2026-01-02T03:04:05Z",
                "version": "1.0.0",
                "oscal-version": "1.2.3",
            },
            "import-profile": {"href": CATALOG_HREF},
            "system-characteristics": {
                "system-ids": [
                    {
                        "id": "identity.example",
                        "identifier-type": "https://example.test/id-types/identity",
                    }
                ],
                "system-name": "Enterprise identity",
                "description": "Identity service for employees.",
                "system-information": {
                    "information-types": [
                        {
                            "uuid": str(INFORMATION_TYPE_UUID),
                            "title": "Employee identity data",
                            "description": "Identity data used to authenticate employees.",
                        }
                    ]
                },
                "status": {"state": "operational"},
                "authorization-boundary": {
                    "description": "The identity service and its managed infrastructure."
                },
            },
            "system-implementation": {
                "components": [
                    {
                        "uuid": str(COMPONENT_UUID),
                        "type": "service",
                        "title": "Identity service",
                        "description": "Identity service deployment.",
                        "status": {"state": "operational"},
                    }
                ]
            },
            "control-implementation": {
                "description": "Requirements are documented by contributing components.",
                "implemented-requirements": [
                    {
                        "uuid": str(REQUIREMENT_UUID),
                        "control-id": "ac-1",
                        "by-components": [
                            {
                                "component-uuid": str(COMPONENT_UUID),
                                "uuid": str(CONTRIBUTION_UUID),
                                "description": "The service enforces the approved policy.",
                                "implementation-status": {"state": "implemented"},
                            }
                        ],
                    }
                ],
            },
        }
    }


def test_official_123_ssp_schema_validates_document_and_baseline_references() -> None:
    validate_system_security_plan_document(
        _document(),
        baseline_control_ids={"ac-1"},
        expected_baseline_href=CATALOG_HREF,
    )


def test_ssp_validation_rejects_control_not_in_pinned_baseline() -> None:
    with pytest.raises(SystemSecurityPlanValidationError, match="not in the pinned baseline"):
        validate_system_security_plan_document(
            _document(),
            baseline_control_ids={"ac-2"},
            expected_baseline_href=CATALOG_HREF,
        )


def test_ssp_validation_rejects_component_reference_not_in_system() -> None:
    document = _document()
    document["system-security-plan"]["control-implementation"]["implemented-requirements"][0][
        "by-components"
    ][0]["component-uuid"] = str(UNKNOWN_COMPONENT_UUID)
    with pytest.raises(SystemSecurityPlanValidationError, match="unknown system component"):
        validate_system_security_plan_document(
            document,
            baseline_control_ids={"ac-1"},
            expected_baseline_href=CATALOG_HREF,
        )


def test_ssp_123_uses_official_schema_not_trestle_model() -> None:
    assert is_supported_oscal_version(OscalDocumentModel.SYSTEM_SECURITY_PLAN, "1.2.3")
    assert not uses_trestle_model(OscalDocumentModel.SYSTEM_SECURITY_PLAN, "1.2.3")


def test_ssp_authoring_policy_selects_version_from_component_types() -> None:
    assert authoring_version_for_component_types(
        OscalDocumentModel.SYSTEM_SECURITY_PLAN, ["service", "network"]
    ) == "1.2.1"
    assert authoring_version_for_component_types(
        OscalDocumentModel.SYSTEM_SECURITY_PLAN, ["resource-container"]
    ) == "1.2.3"


def test_authored_121_ssp_uses_trestle_and_official_schema() -> None:
    document = _document()
    document["system-security-plan"]["metadata"]["oscal-version"] = "1.2.1"

    serialized = serialize_authored_system_security_plan(document)

    assert serialized["system-security-plan"]["metadata"]["oscal-version"] == "1.2.1"
    validate_system_security_plan_document(
        serialized,
        baseline_control_ids={"ac-1"},
        expected_baseline_href=CATALOG_HREF,
    )


def test_ssp_121_network_system_component_stays_on_trestle_authoring_path() -> None:
    document = _document()
    body = document["system-security-plan"]
    body["metadata"]["oscal-version"] = "1.2.1"
    body["system-implementation"]["components"][0]["type"] = "network"

    serialized = serialize_authored_system_security_plan(document)

    component_type = serialized["system-security-plan"]["system-implementation"][
        "components"
    ][0]["type"]
    assert component_type == "network"
    validate_system_security_plan_document(serialized)


def test_ssp_validation_rejects_responsible_party_without_metadata_party() -> None:
    document = _document()
    body = document["system-security-plan"]
    body["metadata"]["oscal-version"] = "1.2.1"
    body["metadata"]["parties"] = [
        {"uuid": str(PARTY_UUID), "type": "organization", "name": "Example"}
    ]
    body["system-characteristics"]["responsible-parties"] = [
        {"role-id": "system-owner", "party-uuids": [str(UNKNOWN_PARTY_UUID)]}
    ]

    with pytest.raises(SystemSecurityPlanValidationError, match="metadata parties"):
        validate_system_security_plan_document(document)


def test_ssp_validation_rejects_internal_validation_link_to_unknown_component() -> None:
    document = _document()
    body = document["system-security-plan"]
    body["metadata"]["oscal-version"] = "1.2.1"
    body["system-implementation"]["components"][0]["links"] = [
        {"href": f"#{UNKNOWN_COMPONENT_UUID}", "rel": "validation"}
    ]

    with pytest.raises(SystemSecurityPlanValidationError, match="validation links"):
        validate_system_security_plan_document(document)


def test_bundled_ssp_schema_has_recorded_upstream_digest() -> None:
    schema = (
        files("collaborative_oscal_oscal")
        .joinpath("schemas", "oscal_ssp_schema_v1.2.3.json")
        .read_bytes()
    )
    assert hashlib.sha256(schema).hexdigest() == (
        "99b1bee2df5604a7d4f1faeab43148e0bd4c4a1f513cd0d2d0c7896aa216a1e7"
    )
