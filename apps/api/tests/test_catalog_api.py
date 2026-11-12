import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, update
from sqlalchemy.exc import DBAPIError

from app.api import dependencies
from app.application.authorization import ROLE_PERMISSIONS
from app.application.catalog_import import CatalogImportService
from app.config import get_settings
from app.domain.identity.models import Permission, TenantRole
from app.persistence.database import create_session_factory
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import CatalogRevisionRecord
from app.persistence.repositories import SQLAlchemyUnitOfWork

pytestmark = pytest.mark.integration

ISSUER = "https://identity.example.test/realms/test"
EXAMPLES = Path(__file__).parents[3] / "examples" / "catalogs"
FIXTURE = Path(__file__).parent / "fixtures" / "oscal_catalog.json"


class _StubValidator:
    """Maps opaque test tokens to claims; the real dependency chain still runs."""

    def validate(self, token: str) -> dict:
        from app.authentication.tokens import InvalidAccessToken

        if not token.startswith("token-"):
            raise InvalidAccessToken("unknown")
        return {"iss": ISSUER, "sub": token.removeprefix("token-")}


class World:
    def __init__(self, session_factory, grc_service) -> None:
        self.session_factory = session_factory
        suffix = uuid4().hex[:8]
        self.tenant_a = grc_service.create_tenant("Alpha Tenant", f"alpha-{suffix}")
        self.tenant_b = grc_service.create_tenant("Beta Tenant", f"beta-{suffix}")
        importer = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory))
        self.security = importer.import_catalog(
            self.tenant_a.id, (EXAMPLES / "sample-security-practices.json").read_bytes()
        )
        self.data = importer.import_catalog(
            self.tenant_a.id, (EXAMPLES / "sample-data-handling.json").read_bytes()
        )
        other = json.loads(FIXTURE.read_text())
        other["catalog"]["metadata"]["oscal-version"] = "1.2.1"
        self.foreign = importer.import_catalog(
            self.tenant_b.id, json.dumps(other).encode(), metadata=None or _meta()
        )
        self.subjects = {
            name: f"{name}-{suffix}" for name in ("alice", "bob", "carol", "dave", "editor")
        }
        self._membership("alice", self.tenant_a.id, "viewer", "active")
        self._membership("bob", self.tenant_b.id, "tenant_admin", "active")
        self._membership("carol", self.tenant_a.id, "viewer", "inactive")
        self._membership("alice", self.tenant_b.id, "viewer", "inactive")
        self._membership("editor", self.tenant_a.id, "catalog_editor", "active")
        self.identity_ids = {}
        with session_factory.begin() as session:
            for name, subject in self.subjects.items():
                self.identity_ids[name] = (
                    SQLIdentityRepository(session)
                    .get_or_create(issuer=ISSUER, subject=subject, display_name=None, email=None)
                    .id
                )

    def _membership(self, name: str, tenant_id: UUID, role: str, status: str) -> None:
        with self.session_factory.begin() as session:
            identity = SQLIdentityRepository(session).get_or_create(
                issuer=ISSUER, subject=self.subjects[name], display_name=None, email=None
            )
            SQLMembershipRepository(session).assign(
                tenant_id=tenant_id, user_id=identity.id, role=role, status=status
            )

    def headers(self, name: str) -> dict[str, str]:
        return {"Authorization": f"Bearer token-{self.subjects[name]}"}


def _meta():
    from app.application.catalog_import import CatalogImportMetadata

    return CatalogImportMetadata()


@pytest.fixture
def world(monkeypatch, postgres_url, session_factory, grc_service):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    get_settings.cache_clear()
    create_session_factory.cache_clear()
    monkeypatch.setattr(dependencies, "get_access_token_validator", lambda: _StubValidator())
    yield World(session_factory, grc_service)
    get_settings.cache_clear()
    create_session_factory.cache_clear()


@pytest.fixture
def client(world):
    from app.main import app

    return TestClient(app)


def _base(tenant_id, catalog_id=None) -> str:
    path = f"/api/v1/tenants/{tenant_id}/catalogs"
    return path if catalog_id is None else f"{path}/{catalog_id}"


def test_catalog_endpoints_require_authentication(client, world) -> None:
    for path in (
        "/api/v1/tenants",
        _base(world.tenant_a.id),
        _base(world.tenant_a.id, world.security.catalog.id),
    ):
        response = client.get(path)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json() == {"detail": "Authentication required."}
    invalid = client.get(_base(world.tenant_a.id), headers={"Authorization": "Bearer junk"})
    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "Invalid access token."}


def test_tenant_list_contains_only_active_memberships(client, world) -> None:
    alice = client.get("/api/v1/tenants", headers=world.headers("alice")).json()
    assert [item["id"] for item in alice["items"]] == [str(world.tenant_a.id)]
    assert alice["items"][0]["role"] == "viewer"
    assert "catalog:read" in alice["items"][0]["permissions"]
    assert "issuer" not in json.dumps(alice)

    bob = client.get("/api/v1/tenants", headers=world.headers("bob")).json()
    assert [item["id"] for item in bob["items"]] == [str(world.tenant_b.id)]
    assert client.get("/api/v1/tenants", headers=world.headers("carol")).json() == {"items": []}
    assert client.get("/api/v1/tenants", headers=world.headers("dave")).json() == {"items": []}


def test_membership_and_tenant_boundaries_are_enforced(client, world) -> None:
    denied = {"detail": "Tenant access denied."}
    for user, tenant in (
        ("bob", world.tenant_a),
        ("alice", world.tenant_b),  # inactive membership
        ("carol", world.tenant_a),  # inactive membership
        ("dave", world.tenant_a),  # no membership
    ):
        response = client.get(_base(tenant.id), headers=world.headers(user))
        assert response.status_code == 403
        assert response.json() == denied
    unknown = client.get(_base(uuid4()), headers=world.headers("alice"))
    assert unknown.status_code == 403
    assert unknown.json() == denied


def test_catalog_read_permission_is_required(client, world, monkeypatch) -> None:
    monkeypatch.setitem(ROLE_PERMISSIONS, TenantRole.VIEWER, frozenset({Permission.TENANT_READ}))
    response = client.get(_base(world.tenant_a.id), headers=world.headers("alice"))
    assert response.status_code == 403
    assert client.get("/api/v1/tenants", headers=world.headers("alice")).status_code == 200


def test_catalog_import_http_authorization_and_revisions(client, world) -> None:
    base = _base(world.tenant_a.id)
    content = (EXAMPLES / "sample-security-practices.json").read_bytes()
    headers = {**world.headers("editor"), "Content-Type": "application/json"}
    assert client.post(f"{base}/import", content=content).status_code == 401
    assert client.post(
        f"{base}/import", content=content, headers=world.headers("alice")
    ).status_code == 403
    foreign = client.post(
        f"{base}/{world.foreign.catalog.id}/import", content=content, headers=headers
    )
    assert foreign.status_code == 404

    created = client.post(f"{base}/import", content=content, headers=headers)
    assert created.status_code == 200
    result = created.json()
    assert result["created"] is True
    assert result["catalog_name"] == "Collaborative OSCAL Sample Security Practices"
    duplicate = client.post(
        f"{base}/{result['catalog_id']}/import", content=content, headers=headers
    )
    assert duplicate.json()["created"] is False
    assert duplicate.json()["revision_id"] == result["revision_id"]
    assert client.get(f"{base}/{result['catalog_id']}", headers=headers).status_code == 200
    modified = json.loads(content)
    modified["catalog"]["metadata"]["version"] = "new-source-version"
    revision = client.post(
        f"{base}/{result['catalog_id']}/import", json=modified, headers=headers
    )
    assert revision.status_code == 200
    assert revision.json()["created"] is True
    assert revision.json()["revision_number"] == 2
    assert revision.json()["revision_id"] != result["revision_id"]
    listing = client.get(base, headers=headers).json()
    assert any(item["id"] == result["catalog_id"] for item in listing["items"])

    invalid = client.post(f"{base}/import", content=b"{", headers=headers)
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["errors"]
    assert client.post(
        f"{base}/import", content=content, headers=world.headers("editor")
    ).status_code == 415


def test_catalog_listing_pagination_and_search(client, world) -> None:
    headers = world.headers("alice")
    listing = client.get(_base(world.tenant_a.id), headers=headers).json()
    assert listing["total"] == 2
    assert [item["name"] for item in listing["items"]] == [
        "Collaborative OSCAL Sample Data Handling",
        "Collaborative OSCAL Sample Security Practices",
    ]
    security = listing["items"][1]
    assert security["origin_type"] == "imported"
    assert security["revision_count"] == 1
    assert security["latest_revision"]["control_count"] == 6
    assert security["latest_revision"]["oscal_version"] == "1.2.1"
    assert security["source_organization"] == "Collaborative OSCAL Project"
    assert "content" not in json.dumps(listing)

    first = client.get(_base(world.tenant_a.id) + "?limit=1", headers=headers).json()
    second = client.get(_base(world.tenant_a.id) + "?limit=1&offset=1", headers=headers).json()
    assert first["total"] == second["total"] == 2
    assert len(first["items"]) == len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]

    found = client.get(_base(world.tenant_a.id) + "?q=data%20handling", headers=headers).json()
    assert [item["id"] for item in found["items"]] == [str(world.data.catalog.id)]
    assert client.get(_base(world.tenant_a.id) + "?q=%25", headers=headers).json()["total"] == 0

    assert client.get(_base(world.tenant_a.id) + "?limit=0", headers=headers).status_code == 422
    too_large = client.get(_base(world.tenant_a.id) + "?limit=100000", headers=headers)
    assert too_large.status_code == 422
    assert client.get(_base(world.tenant_a.id) + "?offset=-1", headers=headers).status_code == 422


def test_cross_tenant_resources_are_not_found_or_forbidden(client, world) -> None:
    headers = world.headers("alice")
    foreign_catalog = world.foreign.catalog.id
    foreign_revision = world.foreign.revision.id
    for path in (
        _base(world.tenant_a.id, foreign_catalog),
        _base(world.tenant_a.id, foreign_catalog) + "/revisions",
        _base(world.tenant_a.id, foreign_catalog) + f"/revisions/{foreign_revision}",
        _base(world.tenant_a.id, world.security.catalog.id)
        + f"/revisions/{foreign_revision}/controls",
        _base(world.tenant_a.id, foreign_catalog) + f"/revisions/{foreign_revision}/controls/ac-1",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 404, path
        assert "Alpha" not in response.text and "Beta" not in response.text
    # Same IDs addressed through the foreign tenant are denied outright.
    assert client.get(_base(world.tenant_b.id, foreign_catalog), headers=headers).status_code == 403
    # A revision of another catalog in the same tenant is not addressable either.
    mismatched = _base(world.tenant_a.id, world.data.catalog.id) + (
        f"/revisions/{world.security.revision.id}"
    )
    assert client.get(mismatched, headers=headers).status_code == 404


def test_catalog_detail_and_revisions(client, world, session_factory) -> None:
    headers = world.headers("alice")
    catalog_path = _base(world.tenant_a.id, world.security.catalog.id)
    detail = client.get(catalog_path, headers=headers).json()
    assert detail["id"] == str(world.security.catalog.id)
    assert detail["latest_revision"]["id"] == str(world.security.revision.id)

    importer = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory))
    changed = json.loads((EXAMPLES / "sample-security-practices.json").read_text())
    changed["catalog"]["metadata"]["version"] = "1.1.0"
    second = importer.import_catalog(
        world.tenant_a.id,
        json.dumps(changed).encode(),
        target_catalog_id=world.security.catalog.id,
    )
    with session_factory.begin() as session:
        session.execute(
            update(CatalogRevisionRecord)
            .where(CatalogRevisionRecord.id == world.security.revision.id)
            .values(lifecycle_status="published", published_at=world.security.revision.created_at)
        )

    revisions = client.get(catalog_path + "/revisions", headers=headers).json()
    assert revisions["total"] == 2
    assert [item["revision_number"] for item in revisions["items"]] == [2, 1]
    assert revisions["items"][0]["id"] == str(second.revision.id)
    assert revisions["items"][0]["source_version"] == "1.1.0"
    assert revisions["items"][0]["control_count"] == 6

    published = client.get(
        catalog_path + "/revisions?lifecycle_status=published", headers=headers
    ).json()
    assert [item["id"] for item in published["items"]] == [str(world.security.revision.id)]
    bad_filter = client.get(catalog_path + "?", headers=headers)
    assert bad_filter.status_code == 200
    assert (
        client.get(catalog_path + "/revisions?lifecycle_status=nope", headers=headers).status_code
        == 422
    )

    one = client.get(
        catalog_path + f"/revisions/{world.security.revision.id}", headers=headers
    ).json()
    assert one["group_count"] == 3
    assert one["source_document"]["title"] == "Collaborative OSCAL Sample Security Practices"
    assert one["source_document"]["version"] == "1.0.0"
    assert client.get(catalog_path + "/revisions?limit=1", headers=headers).json()["total"] == 2
    latest = client.get(catalog_path, headers=headers).json()
    assert latest["revision_count"] == 2
    assert latest["latest_revision"]["id"] == str(second.revision.id)

    missing = client.get(_base(world.tenant_a.id, uuid4()), headers=headers)
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Catalog not found."}
    assert client.get(catalog_path + f"/revisions/{uuid4()}", headers=headers).status_code == 404
    assert client.get(catalog_path + "/revisions/not-a-uuid", headers=headers).status_code == 422


def _revision_path(world) -> str:
    return (
        _base(world.tenant_a.id, world.security.catalog.id)
        + f"/revisions/{world.security.revision.id}"
    )


def test_profiles_reference_catalogs_and_select_controls_without_mutating_sources(
    client, world
) -> None:
    source_path = _revision_path(world) + "/export"
    source_before = client.get(source_path, headers=world.headers("alice")).json()
    browser = client.get(_revision_path(world) + "/profile-browser", headers=world.headers("alice"))
    assert browser.status_code == 200
    nodes = browser.json()["nodes"]
    parent = next(node for node in nodes if node["id"] == "ac-1")
    child = next(node for node in nodes if node["id"] == "ac-1.1")
    assert child["parent_key"] == parent["key"]
    payload = {
        "catalog_id": str(world.security.catalog.id),
        "revision_id": str(world.security.revision.id),
        "title": "Access review profile",
        "description": "Annual review scope",
        "control_ids": ["ac-1", "ac-1.1"],
    }
    profiles_path = f"/api/v1/tenants/{world.tenant_a.id}/profiles"

    denied = client.post(profiles_path, headers=world.headers("alice"), json=payload)
    assert denied.status_code == 403

    created = client.post(profiles_path, headers=world.headers("editor"), json=payload)
    assert created.status_code == 201
    profile = created.json()
    assert profile["catalog_id"] == str(world.security.catalog.id)
    assert profile["revision_id"] == str(world.security.revision.id)
    assert profile["description"] == "Annual review scope"
    listed = client.get(profiles_path, headers=world.headers("alice"))
    assert listed.status_code == 200
    assert listed.json()["items"][0]["control_ids"] == ["ac-1", "ac-1.1"]

    export_path = profiles_path + f"/{profile['id']}/export"
    exported_response = client.get(export_path, headers=world.headers("alice"))
    assert exported_response.status_code == 200
    assert exported_response.headers["content-type"] == "application/json"
    exported = exported_response.json()
    from trestle.oscal.profile import Model

    Model.model_validate_json(exported_response.content, strict=True)
    assert exported["profile"]["metadata"]["title"] == "Access review profile"
    imported = exported["profile"]["imports"][0]
    assert imported["href"] == source_path
    assert imported["include-controls"] == [{"with-ids": ["ac-1", "ac-1.1"]}]

    updated = client.put(
        profiles_path + f"/{profile['id']}",
        headers=world.headers("editor"),
        json={"title": "Updated access profile", "control_ids": ["ac-2"]},
    )
    assert updated.status_code == 200
    updated_document = client.get(export_path, headers=world.headers("alice")).json()
    assert updated_document["profile"]["metadata"]["title"] == "Updated access profile"
    assert updated_document["profile"]["metadata"]["remarks"] == "Annual review scope"
    assert updated_document["profile"]["imports"][0]["include-controls"] == [{"with-ids": ["ac-2"]}]

    invalid_control = client.post(
        profiles_path,
        headers=world.headers("editor"),
        json={**payload, "control_ids": ["not-a-control"]},
    )
    assert invalid_control.status_code == 422
    assert (
        client.post(
            profiles_path,
            headers=world.headers("editor"),
            json={**payload, "catalog_id": str(uuid4())},
        ).status_code
        == 404
    )
    assert client.get(source_path, headers=world.headers("alice")).json() == source_before


def test_outline_navigates_nested_groups_and_controls(client, world) -> None:
    headers = world.headers("alice")
    path = _revision_path(world) + "/outline"
    root = client.get(path, headers=headers).json()
    assert [(n["kind"], n["oscal_id"]) for n in root["items"]] == [
        ("group", "ac"),
        ("group", "ir"),
    ]
    assert root["items"][0]["child_count"] == 3  # ac-1, ac-2, and the ac-priv subgroup

    access = root["items"][0]["id"]
    children = client.get(path + f"?parent_kind=group&parent_id={access}", headers=headers).json()
    assert [(n["kind"], n["oscal_id"], n["child_count"]) for n in children["items"]] == [
        ("control", "ac-1", 1),
        ("control", "ac-2", 0),
        ("group", "ac-priv", 1),
    ]

    ac1 = children["items"][0]["id"]
    nested = client.get(path + f"?parent_kind=control&parent_id={ac1}", headers=headers).json()
    assert [(n["oscal_id"], n["title"]) for n in nested["items"]] == [
        ("ac-1.1", "Policy Exceptions")
    ]

    paged = client.get(
        path + f"?parent_kind=group&parent_id={access}&limit=2&offset=2", headers=headers
    ).json()
    assert paged["total"] == 3
    assert [n["oscal_id"] for n in paged["items"]] == ["ac-priv"]

    assert client.get(path + "?parent_kind=group", headers=headers).status_code == 422
    unknown = client.get(path + f"?parent_kind=group&parent_id={uuid4()}", headers=headers)
    assert unknown.status_code == 404


def test_control_search_and_listing(client, world) -> None:
    headers = world.headers("alice")
    path = _revision_path(world) + "/controls"
    everything = client.get(path, headers=headers).json()
    assert everything["total"] == 6
    assert [item["oscal_control_id"] for item in everything["items"]] == [
        "ac-1",
        "ac-1.1",
        "ac-2",
        "ac-6",
        "ir-1",
        "ir-2",
    ]

    by_id = client.get(path + "?q=AC-1", headers=headers).json()
    assert [item["oscal_control_id"] for item in by_id["items"]] == ["ac-1", "ac-1.1"]
    first = by_id["items"][0]
    assert first["reference"] == {
        "catalog_id": str(world.security.catalog.id),
        "revision_id": str(world.security.revision.id),
        "oscal_control_id": "ac-1",
    }
    assert first["group"]["oscal_group_id"] == "ac"

    by_title = client.get(path + "?q=incident", headers=headers).json()
    assert {item["oscal_control_id"] for item in by_title["items"]} == {"ir-1", "ir-2"}
    assert client.get(path + "?q=nothing-matches", headers=headers).json()["items"] == []
    wildcard = client.get(path + "?q=_", headers=headers).json()
    assert wildcard["total"] == 0
    page = client.get(path + "?limit=2&offset=2", headers=headers).json()
    assert page["total"] == 6 and len(page["items"]) == 2


def test_implementation_register_preserves_original_revision_and_scope(
    client, world, session_factory, grc_service
) -> None:
    tenant = world.tenant_a.id
    organization = grc_service.create_organization(tenant, "Operations", f"ops-{uuid4().hex}")
    path = f"/api/v1/tenants/{tenant}/implementations"
    profiles = f"/api/v1/tenants/{tenant}/profiles"
    editor = world.headers("editor")
    reader = world.headers("alice")
    source_path = _revision_path(world) + "/export"
    original = client.get(source_path, headers=reader).json()
    profile = client.post(
        profiles,
        headers=editor,
        json={
            "catalog_id": str(world.security.catalog.id),
            "revision_id": str(world.security.revision.id),
            "title": "Implementation baseline",
            "control_ids": ["ac-1", "ac-2"],
        },
    ).json()
    payload = {
        "catalog_id": str(world.security.catalog.id),
        "revision_id": str(world.security.revision.id),
        "oscal_control_id": "ac-1",
        "profile_id": profile["id"],
        "description": "Original implementation",
        "status": "in_progress",
        "evidence_references": ["document:policy"],
        "responsibilities": [
            {
                "kind": "accountable",
                "user_id": str(world.identity_ids["editor"]),
                "role": "Owner",
            }
        ],
    }
    assert client.post(path, headers=reader, json=payload).status_code == 403
    first_response = client.post(path, headers=editor, json=payload)
    assert first_response.status_code == 201, first_response.text
    first = first_response.json()
    assert client.put(f"{path}/{first['id']}", headers=editor, json={}).status_code == 422
    second_response = client.post(
        path,
        headers=editor,
        json={
            **payload,
            "organization_id": str(organization.id),
            "description": "Organization-specific",
        },
    )
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()
    assert first["id"] != second["id"]
    assert (
        client.get(path, headers=reader, params={"organization_id": str(organization.id)}).json()[
            "items"
        ][0]["id"]
        == second["id"]
    )
    assert (
        client.get(path, headers=reader, params={"tenant_scope": "true"}).json()["items"][0]["id"]
        == first["id"]
    )
    changed = {
        "description": "Updated implementation",
        "status": "implemented",
        "evidence_references": ["document:policy", "document:review"],
        "responsibilities": [
            {"kind": "responsible", "user_id": str(world.identity_ids["alice"]), "role": ""},
            {"kind": "participant", "user_id": None, "role": "Security team"},
        ],
    }
    updated = client.put(f"{path}/{first['id']}", headers=editor, json=changed)
    assert updated.status_code == 200, updated.text
    assert updated.json()["responsibilities"] == changed["responsibilities"]
    assert client.get(f"{path}/{second['id']}", headers=reader).json()["description"] == (
        "Organization-specific"
    )
    assert client.get(source_path, headers=reader).json() == original
    with pytest.raises(DBAPIError, match="referenced by implementations are immutable"):
        with session_factory.begin() as session:
            session.execute(
                update(CatalogRevisionRecord)
                .where(CatalogRevisionRecord.id == world.security.revision.id)
                .values(content_sha256="0" * 64)
            )

    document = json.loads((EXAMPLES / "sample-security-practices.json").read_text())
    document["catalog"]["metadata"]["version"] = "2.0.0"
    document["catalog"]["groups"][0]["controls"][0]["title"] = "Changed requirement"
    new_revision = CatalogImportService(
        lambda: SQLAlchemyUnitOfWork(session_factory)
    ).import_catalog(
        tenant, json.dumps(document).encode(), target_catalog_id=world.security.catalog.id
    )
    new_profile = client.post(
        profiles,
        headers=editor,
        json={
            "catalog_id": str(world.security.catalog.id),
            "revision_id": str(new_revision.revision.id),
            "title": "Updated baseline",
            "control_ids": ["ac-1"],
        },
    ).json()
    assert (
        client.get(path, headers=reader, params={"profile_id": new_profile["id"]}).json()["items"]
        == []
    )
    after = client.get(f"{path}/{first['id']}", headers=reader).json()
    assert after["revision_id"] == str(world.security.revision.id)
    assert after["evidence_references"] == changed["evidence_references"]
    assert sorted(after["responsibilities"], key=lambda r: r["kind"]) == sorted(
        changed["responsibilities"], key=lambda r: r["kind"]
    )
    control = client.get(f"{path}/{first['id']}/control", headers=reader).json()
    assert control["title"] == "Access Policy"
    assert control["reference"]["revision_id"] == str(world.security.revision.id)
    assert (
        client.put(
            f"{profiles}/{profile['id']}",
            headers=editor,
            json={
                "title": "Changed selection",
                "control_ids": ["ac-2"],
            },
        ).status_code
        == 200
    )
    assert (
        client.get(path, headers=reader, params={"profile_id": profile["id"]}).json()["total"] == 2
    )
    assert client.get(source_path, headers=reader).json() == original
    world._membership("alice", tenant, "viewer", "inactive")
    retained = client.put(f"{path}/{first['id']}", headers=editor, json=changed)
    assert retained.status_code == 200
    reassigned = {
        **changed,
        "responsibilities": [
            {"kind": "accountable", "user_id": str(world.identity_ids["alice"]), "role": ""}
        ],
    }
    assert client.put(f"{path}/{first['id']}", headers=editor, json=reassigned).status_code == 422


def test_implementation_rejects_missing_foreign_and_unselected_references(
    client, world, grc_service
) -> None:
    tenant = world.tenant_a.id
    path = f"/api/v1/tenants/{tenant}/implementations"
    editor = world.headers("editor")
    profile = client.post(
        f"/api/v1/tenants/{tenant}/profiles",
        headers=editor,
        json={
            "catalog_id": str(world.security.catalog.id),
            "revision_id": str(world.security.revision.id),
            "title": "Baseline",
            "control_ids": ["ac-1"],
        },
    ).json()
    base = {
        "catalog_id": str(world.security.catalog.id),
        "revision_id": str(world.security.revision.id),
        "profile_id": profile["id"],
        "oscal_control_id": "ac-1",
    }
    assert (
        client.post(path, headers=editor, json={**base, "oscal_control_id": "missing"}).status_code
        == 404
    )
    assert (
        client.post(path, headers=editor, json={**base, "oscal_control_id": "ac-2"}).status_code
        == 422
    )
    assert (
        client.post(
            path,
            headers=editor,
            json={
                **base,
                "catalog_id": str(world.foreign.catalog.id),
                "revision_id": str(world.foreign.revision.id),
            },
        ).status_code
        == 404
    )
    foreign_org = grc_service.create_organization(
        world.tenant_b.id, "Foreign", f"org-{uuid4().hex}"
    )
    assert (
        client.post(
            path,
            headers=editor,
            json={
                **base,
                "organization_id": str(foreign_org.id),
            },
        ).status_code
        == 404
    )
    for user in ("bob", "carol"):
        assert (
            client.post(
                path,
                headers=editor,
                json={
                    **base,
                    "responsibilities": [
                        {"kind": "responsible", "user_id": str(world.identity_ids[user])}
                    ],
                },
            ).status_code
            == 422
        )
    assert client.get(path, headers=world.headers("bob")).status_code == 403


def test_control_detail_preserves_oscal_semantics(client, world) -> None:
    headers = world.headers("alice")
    response = client.get(_revision_path(world) + "/controls/ac-1", headers=headers)
    assert response.status_code == 200
    control = response.json()
    assert control["oscal_control_id"] == "ac-1"
    assert control["title"] == "Access Policy"
    assert control["class"] == "sample"
    assert control["oscal_version"] == "1.2.1"
    assert control["oscal_document_uuid"] == "5b1c0e3a-71d4-4d0f-9b0e-2f4d6a1c8e01"
    assert control["reference"] == {
        "catalog_id": str(world.security.catalog.id),
        "revision_id": str(world.security.revision.id),
        "oscal_control_id": "ac-1",
    }
    assert control["group"]["oscal_group_id"] == "ac"
    assert [(a["kind"], a["oscal_id"]) for a in control["ancestors"]] == [("group", "ac")]
    assert control["child_control_count"] == 1
    assert "controls" not in control

    statement = control["parts"][0]
    assert statement["name"] == "statement"
    assert "{{ insert: param, ac-1_prm_1 }}" in statement["prose"]
    assert [part["props"][0]["value"] for part in statement["parts"]] == ["a.", "b."]
    assert control["parts"][1]["name"] == "guidance"

    parameters = {item["id"]: item for item in control["parameters"]}
    assert parameters["ac-1_prm_1"]["values"] == ["annually"]
    assert parameters["ac-1_prm_2"]["select"]["how_many"] == "one-or-more"
    assert [item["name"] for item in control["properties"]] == ["label", "sort-id"]
    assert control["links"][0]["href"].startswith("#")
    assert [item["title"] for item in control["references"]] == ["Sample access policy template"]
    assert (
        control["references"][0]["rlinks"][0]["href"] == "https://example.com/sample-access-policy"
    )
    assert control["source_catalog"]["name"] == "Collaborative OSCAL Sample Security Practices"
    assert control["source_catalog"]["origin_type"] == "imported"
    assert control["source_revision"]["revision_number"] == 1

    nested = client.get(_revision_path(world) + "/controls/ac-1.1", headers=headers).json()
    assert [(a["kind"], a["oscal_id"]) for a in nested["ancestors"]] == [
        ("group", "ac"),
        ("control", "ac-1"),
    ]
    assert nested["parent_control_id"] == control["id"]

    deep = client.get(_revision_path(world) + "/controls/ac-6", headers=headers).json()
    assert [a["oscal_id"] for a in deep["ancestors"]] == ["ac", "ac-priv"]

    missing = client.get(_revision_path(world) + "/controls/nope", headers=headers)
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Control not found."}


def test_control_content_is_returned_as_inert_data(client, world, session_factory) -> None:
    document = json.loads((EXAMPLES / "sample-data-handling.json").read_text())
    control = document["catalog"]["groups"][0]["controls"][0]
    control["title"] = "<img src=x onerror=alert(1)>"
    control["parts"][0]["prose"] = '<script>alert("x")</script> [click](javascript:alert(1))'
    control["links"] = [{"href": "javascript:alert(1)", "text": "<b>bad</b>"}]
    imported = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory)).import_catalog(
        world.tenant_a.id, json.dumps(document).encode()
    )
    path = _base(world.tenant_a.id, imported.catalog.id) + f"/revisions/{imported.revision.id}"
    response = client.get(path + "/controls/dh-1", headers=world.headers("alice"))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert body["title"] == "<img src=x onerror=alert(1)>"
    assert body["links"][0]["href"] == "javascript:alert(1)"  # data fidelity; UI filters schemes


def test_responses_never_include_tokens_or_identity_secrets(client, world) -> None:
    headers = world.headers("alice")
    for path in ("/api/v1/tenants", _base(world.tenant_a.id), _revision_path(world) + "/controls"):
        text = client.get(path, headers=headers).text
        assert "token-" not in text
        assert world.subjects["alice"] not in text
        assert ISSUER not in text


def test_hierarchy_queries_use_a_bounded_number_of_statements(
    world, client, session_factory
) -> None:
    engine = create_session_factory().kw["bind"]
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        client.get(_base(world.tenant_a.id), headers=world.headers("alice"))
        listing_count = len(statements)
        statements.clear()
        client.get(_revision_path(world) + "/outline", headers=world.headers("alice"))
        outline_count = len(statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    # Authentication + membership lookups, plus a fixed number of catalog queries.
    assert listing_count <= 10
    assert outline_count <= 8


def test_openapi_documents_catalog_api() -> None:
    from app.main import app

    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/tenants" in paths
    assert "/api/v1/tenants/{tenant_id}/profiles" in paths
    assert "/api/v1/tenants/{tenant_id}/profiles/{profile_id}/export" in paths
    assert (
        "/api/v1/tenants/{tenant_id}/catalogs/{catalog_id}/revisions/{revision_id}/profile-browser"
        in paths
    )
    assert (
        "/api/v1/tenants/{tenant_id}/catalogs/{catalog_id}/revisions/{revision_id}"
        "/controls/{control_id}" in paths
    )
    operation = paths["/api/v1/tenants/{tenant_id}/catalogs"]["get"]
    assert {"401", "403"} <= set(operation["responses"])
    assert schema["components"]["schemas"]["ControlDetailResponse"]["properties"]["class"]
