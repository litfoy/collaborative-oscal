import json
from uuid import uuid4

import pytest
from collaborative_oscal_oscal.profile import (
    ProfileDocumentValidationError,
    build_profile_document,
    validate_profile_document,
)
from pydantic import ValidationError
from trestle.oscal.profile import Model

from app.api.profile_schemas import ProfileCreateRequest


@pytest.mark.parametrize("oscal_version", ["1.1.3", "1.2.1"])
def test_profile_document_is_valid_for_supported_oscal_versions(oscal_version: str) -> None:
    document = build_profile_document(
        profile_uuid=uuid4(),
        title="Selected controls",
        oscal_version=oscal_version,
        catalog_href="/api/v1/tenants/tenant/catalogs/catalog/revisions/revision/export",
        control_ids=["ac-1", "ac-2"],
        description="Annual review scope",
    )

    validated = Model.model_validate_json(json.dumps(document), strict=True)
    assert validated.profile.imports[0].include_controls[0].with_ids == ["ac-1", "ac-2"]
    assert document["profile"]["metadata"]["oscal-version"] == oscal_version
    assert document["profile"]["metadata"]["remarks"] == "Annual review scope"
    assert document["profile"]["imports"][0]["include-controls"] == [{"with-ids": ["ac-1", "ac-2"]}]


def test_profile_document_rejects_unsupported_oscal_versions() -> None:
    with pytest.raises(ProfileDocumentValidationError, match="Unsupported OSCAL version"):
        build_profile_document(
            profile_uuid=uuid4(),
            title="Selected controls",
            oscal_version="9.9.9",
            catalog_href="/api/v1/catalogs/catalog/export",
            control_ids=["ac-1"],
        )


@pytest.mark.parametrize("selection", [["parent"], ["parent.child"], ["parent", "parent.child"]])
def test_parent_and_child_inclusion_is_explicit(selection: list[str]) -> None:
    document = build_profile_document(
        profile_uuid=uuid4(),
        title="Explicit scope",
        oscal_version="1.2.1",
        catalog_href="/pinned-revision/export",
        control_ids=selection,
    )
    imported = document["profile"]["imports"][0]
    assert imported == {
        "href": "/pinned-revision/export",
        "include-controls": [{"with-ids": selection}],
    }


def test_large_profile_selection_contract_has_an_explicit_bound() -> None:
    request = {
        "catalog_id": uuid4(),
        "revision_id": uuid4(),
        "title": "Large scope",
        "control_ids": [f"control-{index}" for index in range(10_000)],
    }
    assert len(ProfileCreateRequest.model_validate(request).control_ids) == 10_000
    with pytest.raises(ValidationError, match="at most 10000"):
        ProfileCreateRequest.model_validate(
            {
                **request,
                "control_ids": [*request["control_ids"], "one-too-many"],
            }
        )
    with pytest.raises(ValidationError, match="must be unique"):
        ProfileCreateRequest.model_validate({**request, "control_ids": ["same", "same"]})


@pytest.mark.parametrize("oscal_version", ["1.1.3", "1.2.1"])
def test_multiple_imports_preserve_colliding_ids(oscal_version: str) -> None:
    document = build_profile_document(
        profile_uuid=uuid4(),
        title="Multiple sources",
        oscal_version=oscal_version,
        imports=[("/first", ["ac-1", "ac-1.1"]), ("/second", ["ac-1"])],
    )
    assert document["profile"]["imports"] == [
        {"href": "/first", "include-controls": [{"with-ids": ["ac-1", "ac-1.1"]}]},
        {"href": "/second", "include-controls": [{"with-ids": ["ac-1"]}]},
    ]


@pytest.mark.parametrize("oscal_version", ["1.1.3", "1.2.1"])
def test_export_validation_rejects_fields_outside_declared_model(oscal_version: str) -> None:
    document = build_profile_document(
        profile_uuid=uuid4(),
        title="Scope",
        oscal_version=oscal_version,
        catalog_href="/catalog",
        control_ids=["ac-1"],
    )
    document["profile"]["invalid-field"] = "not in OSCAL"
    with pytest.raises(ProfileDocumentValidationError):
        validate_profile_document(document)
