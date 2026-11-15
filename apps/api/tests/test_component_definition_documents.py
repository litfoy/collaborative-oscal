from uuid import uuid4

import pytest
from collaborative_oscal_oscal.component_definition import (
    ComponentDefinitionValidationError,
    build_component_definition_document,
    validate_component_definition_document,
)
from collaborative_oscal_oscal.versions import (
    OscalDocumentModel,
    is_supported_oscal_version,
    uses_json_schema,
    uses_trestle_model,
)


def test_component_definition_123_uses_the_official_schema_path() -> None:
    assert is_supported_oscal_version(OscalDocumentModel.COMPONENT_DEFINITION, "1.2.3")
    assert uses_json_schema(OscalDocumentModel.COMPONENT_DEFINITION, "1.2.3")
    assert not uses_trestle_model(OscalDocumentModel.COMPONENT_DEFINITION, "1.2.3")
    assert not is_supported_oscal_version(OscalDocumentModel.COMPONENT_DEFINITION, "1.2.2")
    assert uses_trestle_model(OscalDocumentModel.CATALOG, "1.2.1")
    assert uses_trestle_model(OscalDocumentModel.PROFILE, "1.2.1")


def test_build_and_validate_component_definition_with_multiple_catalog_sources() -> None:
    document = build_component_definition_document(
        document_uuid=uuid4(),
        title="Multifactor authentication",
        components=[
            {
                "uuid": str(uuid4()),
                "type": "policy",
                "title": "Multifactor authentication",
                "description": "A reusable measure.",
                "control-implementations": [
                    {
                        "uuid": str(uuid4()),
                        "source": (
                            "/api/v1/tenants/11111111-1111-4111-8111-111111111111/"
                            "catalogs/22222222-2222-4222-8222-222222222222/revisions/"
                            "33333333-3333-4333-8333-333333333333/export"
                        ),
                        "description": "Guidance for the explicitly listed requirements.",
                        "implemented-requirements": [
                            {
                                "uuid": str(uuid4()),
                                "control-id": "ac-1",
                                "description": "Require MFA for privileged access.",
                            }
                        ],
                    },
                    {
                        "uuid": str(uuid4()),
                        "source": (
                            "/api/v1/tenants/11111111-1111-4111-8111-111111111111/"
                            "catalogs/44444444-4444-4444-8444-444444444444/revisions/"
                            "55555555-5555-4555-8555-555555555555/export"
                        ),
                        "description": "Guidance for the explicitly listed requirements.",
                        "implemented-requirements": [
                            {
                                "uuid": str(uuid4()),
                                "control-id": "ac-1",
                                "description": "Require MFA before processing sensitive data.",
                            }
                        ],
                    },
                ],
            }
        ],
    )
    validate_component_definition_document(document)


def test_component_definition_rejects_invalid_oscal_document() -> None:
    with pytest.raises(ComponentDefinitionValidationError):
        validate_component_definition_document({"component-definition": {"uuid": "invalid"}})
