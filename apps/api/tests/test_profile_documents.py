import json
from uuid import uuid4

import pytest
from collaborative_oscal_oscal.profile import (
    ProfileDocumentValidationError,
    build_profile_document,
)
from trestle.oscal.profile import Model


@pytest.mark.parametrize("oscal_version", ["1.1.3", "1.2.1"])
def test_profile_document_is_valid_for_supported_oscal_versions(oscal_version: str) -> None:
    document = build_profile_document(
        profile_uuid=uuid4(),
        title="Selected controls",
        oscal_version=oscal_version,
        catalog_href="/api/v1/tenants/tenant/catalogs/catalog/revisions/revision/export",
        control_ids=["ac-1", "ac-2"],
    )

    validated = Model.model_validate_json(json.dumps(document), strict=True)
    assert validated.profile.imports[0].include_controls[0].with_ids == ["ac-1", "ac-2"]
    assert document["profile"]["metadata"]["oscal-version"] == oscal_version
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
