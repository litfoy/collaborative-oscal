from uuid import UUID, uuid4

import pytest
from collaborative_oscal_oscal.catalog_index import (
    canonical_json_sha256,
    document_metadata,
    project_catalog_indexes,
)

from app.domain.errors import DomainInvariantError, EntityNotFoundError
from app.domain.organizations.invariants import validate_parent_chain


def test_parent_chain_accepts_nested_organizations() -> None:
    child_id, parent_id, root_id = uuid4(), uuid4(), uuid4()
    parents = {child_id: parent_id, parent_id: root_id, root_id: None}

    validate_parent_chain(child_id, parent_id, parents.__getitem__)


@pytest.mark.parametrize("parent_id", ["self", "cycle"])
def test_parent_chain_rejects_cycles(parent_id: str) -> None:
    organization_id, another_id = uuid4(), uuid4()
    parent = organization_id if parent_id == "self" else another_id
    parents = {another_id: organization_id}

    def get_parent_id(current_id):
        return parents[current_id]

    with pytest.raises(DomainInvariantError, match="cannot contain cycles"):
        validate_parent_chain(organization_id, parent, get_parent_id)


def test_parent_chain_rejects_parent_missing_from_tenant() -> None:
    with pytest.raises(DomainInvariantError, match="not in this tenant"):
        validate_parent_chain(uuid4(), uuid4(), lambda _: _raise_not_found())


def _raise_not_found():
    raise EntityNotFoundError


def test_catalog_projection_preserves_nested_structure_without_mutation() -> None:
    document = {
        "catalog": {
            "groups": [
                {
                    "title": "Outer",
                    "controls": [
                        {
                            "id": "ac-1",
                            "title": "Control",
                            "controls": [{"id": "ac-1.1", "title": "Enhancement"}],
                        }
                    ],
                    "groups": [{"title": "Inner", "controls": []}],
                }
            ]
        }
    }

    groups, controls = project_catalog_indexes(document)

    assert [group.oscal_group_id for group in groups] == [None, None]
    assert groups[1].parent_path == groups[0].structural_path
    assert [control.oscal_control_id for control in controls] == ["ac-1", "ac-1.1"]
    assert controls[1].parent_path == controls[0].structural_path
    assert controls[0].group_path == groups[0].structural_path
    assert "id" not in document["catalog"]["groups"][0]


def test_canonical_json_digest_is_stable_and_sensitive_to_content() -> None:
    first = {"catalog": {"uuid": "same", "metadata": {"title": "Example"}}}
    reordered = {"catalog": {"metadata": {"title": "Example"}, "uuid": "same"}}
    changed = {"catalog": {"uuid": "same", "metadata": {"title": "Changed"}}}

    assert canonical_json_sha256(first) == canonical_json_sha256(reordered)
    assert canonical_json_sha256(first) != canonical_json_sha256(changed)


def test_document_metadata_preserves_oscal_uuid_and_version() -> None:
    document_uuid = UUID("8b6a48cc-6a1e-4e16-a47b-c86be23302af")

    assert document_metadata(
        {
            "catalog": {
                "uuid": str(document_uuid),
                "metadata": {"oscal-version": "1.1.2"},
            }
        }
    ) == (document_uuid, "1.1.2")
