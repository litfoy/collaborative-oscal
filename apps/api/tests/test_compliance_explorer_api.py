# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.application.catalog_import import CatalogImportService
from app.application.compliance_explorer import ComplianceExplorerService
from app.application.profiles import ProfileService
from app.application.system_security_plans import SystemSecurityPlanService
from app.config import get_settings
from app.domain.profiles.models import ProfileImport
from app.persistence.database import create_session_factory
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import ControlImplementationRecord
from app.persistence.repositories import SQLAlchemyUnitOfWork

pytestmark = pytest.mark.integration

ISSUER = "https://identity.example.test/realms/test"
EXAMPLES = Path(__file__).parents[3] / "examples" / "catalogs"


class _StubValidator:
    def validate(self, token: str) -> dict:
        from app.authentication.tokens import InvalidAccessToken

        if not token.startswith("token-"):
            raise InvalidAccessToken("unknown")
        return {"iss": ISSUER, "sub": token.removeprefix("token-")}


@dataclass(slots=True)
class ExplorerWorld:
    tenant_id: UUID
    other_tenant_id: UUID
    catalog_id: UUID
    system_id: UUID
    other_system_id: UUID
    editor_user_id: UUID
    profile_one_id: UUID
    profile_two_id: UUID
    profile_three_id: UUID
    profile_other_tenant_id: UUID
    revision_one_id: UUID
    revision_two_id: UUID
    impl_ids: dict[str, UUID]
    subjects: dict[str, str]

    def headers(self, name: str) -> dict[str, str]:
        return {"Authorization": f"Bearer token-{self.subjects[name]}"}


def _insert_implementation(
    session_factory,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    catalog_id: UUID,
    revision_id: UUID,
    oscal_control_id: str,
    status: str,
    profile_id: UUID | None,
    profile_import_id: UUID | None,
    system_id: UUID | None,
    system_component_id: UUID | None,
    organization_id: UUID | None = None,
    oscal_implementation_status: str | None = None,
) -> UUID:
    implementation_id = uuid4()
    now = datetime.now(UTC)
    with session_factory.begin() as session:
        session.add(
            ControlImplementationRecord(
                id=implementation_id,
                tenant_id=tenant_id,
                organization_id=organization_id,
                system_id=system_id,
                system_component_id=system_component_id,
                profile_id=profile_id,
                profile_import_id=profile_import_id,
                catalog_id=catalog_id,
                revision_id=revision_id,
                oscal_control_id=oscal_control_id,
                description=f"Implementation for {oscal_control_id}",
                status=status,
                oscal_implementation_status=oscal_implementation_status,
                oscal_status_explanation=None,
                evidence_references=[],
                created_by=actor_id,
                updated_by=actor_id,
                created_at=now,
                updated_at=now,
                concurrency_version=1,
            )
        )
    return implementation_id


@pytest.fixture
def explorer_world(monkeypatch, postgres_url, session_factory, grc_service) -> ExplorerWorld:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    monkeypatch.setenv("AUTH_MODE", "keycloak")
    get_settings.cache_clear()
    create_session_factory.cache_clear()
    monkeypatch.setattr(dependencies, "get_access_token_validator", lambda: _StubValidator())

    suffix = uuid4().hex[:8]
    tenant = grc_service.create_tenant("Explorer Tenant", f"explorer-{suffix}")
    other_tenant = grc_service.create_tenant("Other Tenant", f"other-{suffix}")
    importer = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory))

    revision_one = importer.import_catalog(
        tenant.id,
        (EXAMPLES / "sample-security-practices.json").read_bytes(),
    )
    revision_two_doc = json.loads((EXAMPLES / "sample-security-practices.json").read_text())
    revision_two_doc["catalog"]["metadata"]["version"] = "2.0.0"
    for group in revision_two_doc["catalog"].get("groups", []):
        for control in group.get("controls", []):
            if control.get("id") == "ac-1":
                control["title"] = "Access Policy (Revised)"
                break
    revision_two = importer.import_catalog(
        tenant.id,
        json.dumps(revision_two_doc).encode("utf-8"),
        target_catalog_id=revision_one.catalog.id,
    )
    other_revision = importer.import_catalog(
        other_tenant.id,
        (EXAMPLES / "sample-security-practices.json").read_bytes(),
    )

    subjects = {
        "alice": f"alice-{suffix}",
        "editor": f"editor-{suffix}",
        "bob": f"bob-{suffix}",
    }
    identity_ids: dict[str, UUID] = {}
    with session_factory.begin() as session:
        for name, subject in subjects.items():
            identity_ids[name] = (
                SQLIdentityRepository(session)
                .get_or_create(issuer=ISSUER, subject=subject, display_name=None, email=None)
                .id
            )
        membership = SQLMembershipRepository(session)
        membership.assign(
            tenant_id=tenant.id,
            user_id=identity_ids["alice"],
            role="viewer",
            status="active",
        )
        membership.assign(
            tenant_id=tenant.id,
            user_id=identity_ids["editor"],
            role="catalog_editor",
            status="active",
        )
        membership.assign(
            tenant_id=other_tenant.id,
            user_id=identity_ids["bob"],
            role="viewer",
            status="active",
        )

    actor = identity_ids["editor"]
    ssp_service = SystemSecurityPlanService(lambda: session_factory.begin())
    profile_service = ProfileService(lambda: session_factory.begin())

    system = ssp_service.create_system(
        tenant.id,
        actor,
        name="Payments System",
        organization_id=None,
        description="Primary payments platform.",
        system_boundary="Boundary A",
        system_ids=[{"id": "payments", "identifier_type": "internal"}],
        information_types=[{"title": "PII", "description": "Customer data"}],
        operational_status="operational",
        status_remarks=None,
        security_sensitivity_level=None,
    )
    other_system = ssp_service.create_system(
        tenant.id,
        actor,
        name="Analytics System",
        organization_id=None,
        description="Analytics workloads.",
        system_boundary="Boundary B",
        system_ids=[{"id": "analytics", "identifier_type": "internal"}],
        information_types=[{"title": "Telemetry", "description": "Aggregated metrics"}],
        operational_status="operational",
        status_remarks=None,
        security_sensitivity_level=None,
    )
    system_component_one = ssp_service.create_component(
        tenant.id,
        actor,
        system["id"],
        component_type="service",
        title="Gateway",
        description="Gateway component",
        purpose=None,
        status="operational",
        status_remarks=None,
    )
    system_component_two = ssp_service.create_component(
        tenant.id,
        actor,
        system["id"],
        component_type="service",
        title="Identity Service",
        description="Identity component",
        purpose=None,
        status="operational",
        status_remarks=None,
    )
    other_system_component = ssp_service.create_component(
        tenant.id,
        actor,
        other_system["id"],
        component_type="service",
        title="Analytics Engine",
        description="Unrelated component",
        purpose=None,
        status="operational",
        status_remarks=None,
    )
    other_tenant_system = ssp_service.create_system(
        other_tenant.id,
        identity_ids["bob"],
        name="Other Tenant System",
        organization_id=None,
        description="Other tenant system.",
        system_boundary="Boundary C",
        system_ids=[{"id": "other", "identifier_type": "internal"}],
        information_types=[{"title": "Other", "description": "Other tenant data"}],
        operational_status="operational",
        status_remarks=None,
        security_sensitivity_level=None,
    )
    other_tenant_component = ssp_service.create_component(
        other_tenant.id,
        identity_ids["bob"],
        other_tenant_system["id"],
        component_type="service",
        title="Other Component",
        description="Other component",
        purpose=None,
        status="operational",
        status_remarks=None,
    )

    profile_one = profile_service.create(
        tenant.id,
        revision_one.catalog.id,
        revision_one.revision.id,
        "Baseline A",
        ["ac-1", "ac-2"],
    )
    profile_two = profile_service.create(
        tenant.id,
        revision_one.catalog.id,
        revision_one.revision.id,
        "Baseline B",
        ["ac-1", "ir-1"],
    )
    profile_three = profile_service.create(
        tenant.id,
        revision_two.catalog.id,
        revision_two.revision.id,
        "Baseline C",
        ["ac-1"],
    )
    profile_four = profile_service.create(
        tenant.id,
        revision_one.catalog.id,
        revision_one.revision.id,
        "Unselected Provenance",
        ["ac-2"],
    )
    profile_other_tenant = profile_service.create(
        other_tenant.id,
        other_revision.catalog.id,
        other_revision.revision.id,
        "Other Tenant Baseline",
        ["ac-1"],
    )

    organization = grc_service.create_organization(tenant.id, "Ops", f"ops-{suffix}")

    impl_ids = {
        "ac1_gateway": _insert_implementation(
            session_factory,
            tenant_id=tenant.id,
            actor_id=actor,
            catalog_id=revision_one.catalog.id,
            revision_id=revision_one.revision.id,
            oscal_control_id="ac-1",
            status="in_progress",
            profile_id=profile_one.id,
            profile_import_id=profile_one.imports[0].id,
            system_id=system["id"],
            system_component_id=system_component_one["id"],
            oscal_implementation_status="partial",
        ),
        "ac1_identity": _insert_implementation(
            session_factory,
            tenant_id=tenant.id,
            actor_id=actor,
            catalog_id=revision_one.catalog.id,
            revision_id=revision_one.revision.id,
            oscal_control_id="ac-1",
            status="implemented",
            profile_id=profile_two.id,
            profile_import_id=profile_two.imports[0].id,
            system_id=system["id"],
            system_component_id=system_component_two["id"],
            oscal_implementation_status="implemented",
        ),
        "ac2_unselected_profile": _insert_implementation(
            session_factory,
            tenant_id=tenant.id,
            actor_id=actor,
            catalog_id=revision_one.catalog.id,
            revision_id=revision_one.revision.id,
            oscal_control_id="ac-2",
            status="not_started",
            profile_id=profile_four.id,
            profile_import_id=profile_four.imports[0].id,
            system_id=system["id"],
            system_component_id=system_component_one["id"],
        ),
        "ac1_revised_revision": _insert_implementation(
            session_factory,
            tenant_id=tenant.id,
            actor_id=actor,
            catalog_id=revision_two.catalog.id,
            revision_id=revision_two.revision.id,
            oscal_control_id="ac-1",
            status="implemented",
            profile_id=profile_three.id,
            profile_import_id=profile_three.imports[0].id,
            system_id=system["id"],
            system_component_id=None,
            oscal_implementation_status="implemented",
        ),
        "ir1_without_system": _insert_implementation(
            session_factory,
            tenant_id=tenant.id,
            actor_id=actor,
            catalog_id=revision_one.catalog.id,
            revision_id=revision_one.revision.id,
            oscal_control_id="ir-1",
            status="implemented",
            profile_id=profile_two.id,
            profile_import_id=profile_two.imports[0].id,
            system_id=None,
            system_component_id=None,
        ),
        "ac1_other_system": _insert_implementation(
            session_factory,
            tenant_id=tenant.id,
            actor_id=actor,
            catalog_id=revision_one.catalog.id,
            revision_id=revision_one.revision.id,
            oscal_control_id="ac-1",
            status="implemented",
            profile_id=profile_one.id,
            profile_import_id=profile_one.imports[0].id,
            system_id=other_system["id"],
            system_component_id=other_system_component["id"],
        ),
        "ac1_org_scoped": _insert_implementation(
            session_factory,
            tenant_id=tenant.id,
            actor_id=actor,
            catalog_id=revision_one.catalog.id,
            revision_id=revision_one.revision.id,
            oscal_control_id="ac-1",
            status="not_started",
            profile_id=profile_one.id,
            profile_import_id=profile_one.imports[0].id,
            system_id=None,
            system_component_id=None,
            organization_id=organization.id,
        ),
        "ac1_other_tenant": _insert_implementation(
            session_factory,
            tenant_id=other_tenant.id,
            actor_id=identity_ids["bob"],
            catalog_id=other_revision.catalog.id,
            revision_id=other_revision.revision.id,
            oscal_control_id="ac-1",
            status="implemented",
            profile_id=profile_other_tenant.id,
            profile_import_id=profile_other_tenant.imports[0].id,
            system_id=other_tenant_system["id"],
            system_component_id=other_tenant_component["id"],
        ),
    }

    world = ExplorerWorld(
        tenant_id=tenant.id,
        other_tenant_id=other_tenant.id,
        catalog_id=revision_one.catalog.id,
        system_id=system["id"],
        other_system_id=other_system["id"],
        editor_user_id=actor,
        profile_one_id=profile_one.id,
        profile_two_id=profile_two.id,
        profile_three_id=profile_three.id,
        profile_other_tenant_id=profile_other_tenant.id,
        revision_one_id=revision_one.revision.id,
        revision_two_id=revision_two.revision.id,
        impl_ids=impl_ids,
        subjects=subjects,
    )
    yield world
    get_settings.cache_clear()
    create_session_factory.cache_clear()


@pytest.fixture
def client(explorer_world):
    from app.main import app

    return TestClient(app)


def _params(profile_ids: list[UUID], **extra: int) -> list[tuple[str, str]]:
    params = [("profile_id", str(profile_id)) for profile_id in profile_ids]
    for key, value in extra.items():
        params.append((key, str(value)))
    return params


def _reference(item: dict) -> tuple[str, str, str]:
    ref = item["reference"]
    return (ref["catalog_id"], ref["revision_id"], ref["oscal_control_id"])


def test_compliance_explorer_returns_deduplicated_projection_with_provenance(
    client, explorer_world
) -> None:
    path = (
        f"/api/v1/tenants/{explorer_world.tenant_id}/systems/"
        f"{explorer_world.system_id}/compliance-explorer"
    )
    response = client.get(
        path,
        headers=explorer_world.headers("alice"),
        params=_params(
            [
                explorer_world.profile_two_id,
                explorer_world.profile_one_id,
                explorer_world.profile_three_id,
            ]
        ),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["system"] == {
        "id": str(explorer_world.system_id),
        "name": "Payments System",
    }
    assert [item["id"] for item in body["profiles"]] == [
        str(explorer_world.profile_two_id),
        str(explorer_world.profile_one_id),
        str(explorer_world.profile_three_id),
    ]

    assert body["total"] == 4
    assert len(body["items"]) == 4
    ordered_references = [_reference(item) for item in body["items"]]
    assert ordered_references == sorted(ordered_references)

    by_reference = {
        _reference(item): item
        for item in body["items"]
    }
    ac1_rev1 = by_reference[
        next(
            ref
            for ref in by_reference
            if ref[1] == str(explorer_world.revision_one_id) and ref[2] == "ac-1"
        )
    ]
    ac1_rev2 = by_reference[
        next(
            ref
            for ref in by_reference
            if ref[1] == str(explorer_world.revision_two_id) and ref[2] == "ac-1"
        )
    ]
    ac2_rev1 = by_reference[
        next(
            ref
            for ref in by_reference
            if ref[1] == str(explorer_world.revision_one_id) and ref[2] == "ac-2"
        )
    ]
    ir1_rev1 = by_reference[
        next(
            ref
            for ref in by_reference
            if ref[1] == str(explorer_world.revision_one_id) and ref[2] == "ir-1"
        )
    ]

    assert ac1_rev1["title"] == "Access Policy"
    assert ac1_rev2["title"] == "Access Policy (Revised)"
    assert {membership["profile_id"] for membership in ac1_rev1["memberships"]} == {
        str(explorer_world.profile_one_id),
        str(explorer_world.profile_two_id),
    }
    assert all(membership["profile_import_id"] for membership in ac1_rev1["memberships"])
    assert {item["id"] for item in ac1_rev1["implementations"]} == {
        str(explorer_world.impl_ids["ac1_gateway"]),
        str(explorer_world.impl_ids["ac1_identity"]),
    }
    assert {item["status"] for item in ac1_rev1["implementations"]} == {
        "in_progress",
        "implemented",
    }
    assert {item["system_component"]["title"] for item in ac1_rev1["implementations"]} == {
        "Gateway",
        "Identity Service",
    }

    assert len(ac1_rev2["implementations"]) == 1
    assert ac1_rev2["implementations"][0]["id"] == str(
        explorer_world.impl_ids["ac1_revised_revision"]
    )
    assert ac1_rev2["implementations"][0]["system_component_id"] is None
    assert ac1_rev2["implementations"][0]["system_component"] is None

    assert [membership["profile_id"] for membership in ac2_rev1["memberships"]] == [
        str(explorer_world.profile_one_id)
    ]
    assert len(ac2_rev1["implementations"]) == 1
    assert ac2_rev1["implementations"][0]["id"] == str(
        explorer_world.impl_ids["ac2_unselected_profile"]
    )
    assert ac2_rev1["implementations"][0]["profile_id"] != str(explorer_world.profile_one_id)

    assert ir1_rev1["implementations"] == []

    flattened_impl_ids = {
        implementation["id"]
        for item in body["items"]
        for implementation in item["implementations"]
    }
    assert str(explorer_world.impl_ids["ir1_without_system"]) not in flattened_impl_ids
    assert str(explorer_world.impl_ids["ac1_other_system"]) not in flattened_impl_ids
    assert str(explorer_world.impl_ids["ac1_org_scoped"]) not in flattened_impl_ids
    assert str(explorer_world.impl_ids["ac1_other_tenant"]) not in flattened_impl_ids


def test_compliance_explorer_validates_queries_and_tenant_scope(client, explorer_world) -> None:
    path = (
        f"/api/v1/tenants/{explorer_world.tenant_id}/systems/"
        f"{explorer_world.system_id}/compliance-explorer"
    )
    headers = explorer_world.headers("alice")

    assert client.get(path, headers=headers).status_code == 422
    assert (
        client.get(
            path,
            headers=headers,
            params=_params([explorer_world.profile_one_id, explorer_world.profile_one_id]),
        ).status_code
        == 422
    )
    assert (
        client.get(
            path,
            headers=headers,
            params=_params(
                [
                    explorer_world.profile_one_id,
                    explorer_world.profile_two_id,
                    explorer_world.profile_three_id,
                    uuid4(),
                    uuid4(),
                    uuid4(),
                ]
            ),
        ).status_code
        == 422
    )
    assert (
        client.get(
            path,
            headers=headers,
            params=_params([explorer_world.profile_one_id], limit=0),
        ).status_code
        == 422
    )

    unknown_profile = client.get(path, headers=headers, params=_params([uuid4()]))
    assert unknown_profile.status_code == 404
    assert unknown_profile.json() == {"detail": "Profile not found."}

    cross_tenant_profile = client.get(
        path,
        headers=headers,
        params=_params([explorer_world.profile_other_tenant_id]),
    )
    assert cross_tenant_profile.status_code == 404

    missing_system = client.get(
        f"/api/v1/tenants/{explorer_world.tenant_id}/systems/{uuid4()}/compliance-explorer",
        headers=headers,
        params=_params([explorer_world.profile_one_id]),
    )
    assert missing_system.status_code == 404
    assert missing_system.json() == {"detail": "System not found."}

    denied = client.get(
        path,
        headers=explorer_world.headers("bob"),
        params=_params([explorer_world.profile_one_id]),
    )
    assert denied.status_code == 403


def test_compliance_explorer_pagination_is_stable_and_reports_total(client, explorer_world) -> None:
    path = (
        f"/api/v1/tenants/{explorer_world.tenant_id}/systems/"
        f"{explorer_world.system_id}/compliance-explorer"
    )
    headers = explorer_world.headers("alice")
    selected_profiles = [
        explorer_world.profile_one_id,
        explorer_world.profile_two_id,
        explorer_world.profile_three_id,
    ]

    full = client.get(path, headers=headers, params=_params(selected_profiles, limit=10, offset=0))
    assert full.status_code == 200, full.text
    full_body = full.json()
    assert full_body["total"] == 4

    first_page = client.get(
        path,
        headers=headers,
        params=_params(selected_profiles, limit=2, offset=0),
    )
    second_page = client.get(
        path,
        headers=headers,
        params=_params(selected_profiles, limit=2, offset=2),
    )
    assert first_page.status_code == 200
    assert second_page.status_code == 200

    first_body = first_page.json()
    second_body = second_page.json()
    assert first_body["total"] == second_body["total"] == full_body["total"]
    assert [_reference(item) for item in first_body["items"] + second_body["items"]] == [
        _reference(item) for item in full_body["items"]
    ]

    index_with_implementation = next(
        index
        for index, item in enumerate(full_body["items"])
        if item["implementations"]
    )
    paged_one = client.get(
        path,
        headers=headers,
        params=_params(selected_profiles, limit=1, offset=index_with_implementation),
    )
    assert paged_one.status_code == 200
    paged_item = paged_one.json()["items"][0]
    assert paged_item["implementations"] == full_body["items"][index_with_implementation][
        "implementations"
    ]

    empty_page = client.get(
        path,
        headers=headers,
        params=_params(selected_profiles, limit=2, offset=10),
    )
    assert empty_page.status_code == 200
    assert empty_page.json()["items"] == []
    assert empty_page.json()["total"] == full_body["total"]


def test_compliance_explorer_honors_multi_import_reorder_and_deactivation(
    client, explorer_world, session_factory
) -> None:
    profile_service = ProfileService(lambda: session_factory.begin())
    explorer_service = ComplianceExplorerService(lambda: session_factory.begin())

    first_import = ProfileImport(
        id=uuid4(),
        catalog_id=explorer_world.catalog_id,
        revision_id=explorer_world.revision_one_id,
        control_ids=["ac-2"],
    )
    second_import = ProfileImport(
        id=uuid4(),
        catalog_id=explorer_world.catalog_id,
        revision_id=explorer_world.revision_two_id,
        control_ids=["ac-1"],
    )
    profile = profile_service.create(
        explorer_world.tenant_id,
        None,
        None,
        "Multi import profile",
        None,
        imports=[first_import, second_import],
    )

    reordered = profile_service.update(
        explorer_world.tenant_id,
        profile.id,
        profile.concurrency_version,
        "Multi import profile",
        None,
        imports=[second_import, first_import],
    )
    reordered_payload = explorer_service.project(
        explorer_world.tenant_id,
        explorer_world.system_id,
        [reordered.id],
        limit=10,
        offset=0,
    )
    reordered_items = reordered_payload["items"]
    assert reordered_payload["total"] == 2
    assert {
        (
            item["reference"]["revision_id"],
            item["reference"]["oscal_control_id"],
            item["memberships"][0]["profile_import_id"],
        )
        for item in reordered_items
    } == {
        (explorer_world.revision_one_id, "ac-2", first_import.id),
        (explorer_world.revision_two_id, "ac-1", second_import.id),
    }

    deactivated = profile_service.update(
        explorer_world.tenant_id,
        reordered.id,
        reordered.concurrency_version,
        "Multi import profile",
        None,
        imports=[second_import],
    )
    endpoint = (
        f"/api/v1/tenants/{explorer_world.tenant_id}/systems/"
        f"{explorer_world.system_id}/compliance-explorer"
    )
    response = client.get(
        endpoint,
        headers=explorer_world.headers("alice"),
        params=_params([deactivated.id]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["reference"] == {
        "catalog_id": str(explorer_world.catalog_id),
        "revision_id": str(explorer_world.revision_two_id),
        "oscal_control_id": "ac-1",
    }
    assert body["items"][0]["memberships"] == [
        {
            "profile_id": str(deactivated.id),
            "profile_title": "Multi import profile",
            "profile_import_id": str(second_import.id),
        }
    ]




