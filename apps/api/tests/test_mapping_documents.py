from datetime import UTC, datetime
from uuid import uuid4

import pytest
from collaborative_oscal_oscal.mapping import (
    MappingDocumentValidationError,
    relationship_from_opposite_direction,
    validate_mapping_document,
)
from collaborative_oscal_oscal.versions import (
    OscalDocumentModel,
    is_supported_oscal_version,
    uses_json_schema,
    uses_trestle_model,
)

from app.application.mappings import MappingService
from app.domain.identity.models import UserIdentity
from app.domain.mappings import MappingEntrySpec, MappingPairSpec


def _mapping_document(oscal_version: str) -> dict:
    return {
        "mapping-collection": {
            "uuid": str(uuid4()),
            "metadata": {
                "title": "Synthetic control mapping",
                "last-modified": "2026-01-01T00:00:00Z",
                "version": "1.0.0",
                "oscal-version": oscal_version,
            },
            "provenance": {
                "method": "human",
                "matching-rationale": "semantic",
                "status": "draft",
                "mapping-description": "Synthetic test mapping.",
            },
            "mappings": [
                {
                    "uuid": str(uuid4()),
                    "method": "human",
                    "status": "draft",
                    "source-resource": {
                        "type": "catalog",
                        "href": "/api/v1/tenants/example/catalogs/source/revisions/one/export",
                    },
                    "target-resource": {
                        "type": "catalog",
                        "href": "/api/v1/tenants/example/catalogs/target/revisions/two/export",
                    },
                    "maps": [
                        {
                            "uuid": str(uuid4()),
                            "relationship": "equivalent-to",
                            "matching-rationale": "semantic",
                            "sources": [{"type": "control", "id-ref": "ac-1"}],
                            "targets": [{"type": "control", "id-ref": "ac-1"}],
                        }
                    ],
                }
            ],
        }
    }


@pytest.mark.parametrize("version", ["1.2.0", "1.2.1", "1.2.2", "1.2.3"])
def test_mapping_validation_uses_the_registered_model_path(version: str) -> None:
    document = _mapping_document(version)

    validate_mapping_document(document)

    assert is_supported_oscal_version(OscalDocumentModel.MAPPING, version)
    if version in {"1.2.0", "1.2.1"}:
        assert uses_trestle_model(OscalDocumentModel.MAPPING, version)
    else:
        assert uses_json_schema(OscalDocumentModel.MAPPING, version)


def test_generated_mapping_document_uses_official_root_and_stable_member_sets() -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    source_catalog_id, source_revision_id = uuid4(), uuid4()
    target_catalog_id, target_revision_id = uuid4(), uuid4()
    actor = UserIdentity(
        actor_id,
        "https://identity.example.test",
        "mapper",
        "Mapping author",
        None,
        datetime.now(UTC),
        datetime.now(UTC),
    )
    pair = MappingPairSpec(
        None,
        source_catalog_id,
        source_revision_id,
        target_catalog_id,
        target_revision_id,
        (
            MappingEntrySpec(
                None,
                ("AC-1", "AC-2"),
                ("POL-1", "POL-2"),
                "subset-of",
                "functional",
                "Synthetic many-to-many fixture.",
            ),
        ),
    )

    document, members = MappingService._build_document(
        tenant_id,
        uuid4(),
        actor,
        "Synthetic collection",
        "Synthetic test data",
        [pair],
        datetime.now(UTC),
    )

    validate_mapping_document(document)
    collection = document["mapping-collection"]
    assert set(document) == {"mapping-collection"}
    assert collection["metadata"]["oscal-version"] == "1.2.3"
    assert collection["provenance"]["method"] == "human"
    assert collection["mappings"][0]["source-resource"]["href"].endswith(
        f"{source_revision_id}/export"
    )
    entry = collection["mappings"][0]["maps"][0]
    assert [member["id-ref"] for member in entry["sources"]] == ["AC-1", "AC-2"]
    assert [member["id-ref"] for member in entry["targets"]] == ["POL-1", "POL-2"]
    assert {member.side for member in members} == {"source", "target"}


@pytest.mark.parametrize("version", ["1.0.0", "1.1.3", "1.2.4"])
def test_mapping_validation_rejects_unsupported_versions(version: str) -> None:
    document = _mapping_document(version)

    with pytest.raises(MappingDocumentValidationError, match="Unsupported OSCAL Mapping version"):
        validate_mapping_document(document)


@pytest.mark.parametrize(
    ("relationship", "inverse"),
    [
        ("equal-to", "equal-to"),
        ("equivalent-to", "equivalent-to"),
        ("subset-of", "superset-of"),
        ("superset-of", "subset-of"),
        ("intersects-with", "intersects-with"),
        ("no-relationship", "no-relationship"),
    ],
)
def test_relationship_direction_is_inverted_only_when_required(
    relationship: str, inverse: str
) -> None:
    assert relationship_from_opposite_direction(relationship) == inverse
