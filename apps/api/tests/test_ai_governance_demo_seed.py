# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from collaborative_oscal_oscal.assessment_plan import validate_assessment_plan_document
from collaborative_oscal_oscal.assessment_result import validate_assessment_result_document
from collaborative_oscal_oscal.component_definition import (
    validate_component_definition_document,
)
from collaborative_oscal_oscal.system_security_plan import (
    validate_system_security_plan_document,
)
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.application import ai_governance_demo as ai_demo_module
from app.application.ai_governance_demo import (
    EU_AI_ACT_CATALOG_UUID,
    GOVERNANCE_COVERAGE_MAPPING_COUNT,
    GOVERNANCE_COVERAGE_MAPPING_TITLE,
    GOVERNANCE_COVERAGE_SEED_NAME,
    GOVERNANCE_COVERAGE_SYSTEM_NAME,
    MODEL_VERSION_CONTROL_ID,
    MODEL_VERSION_OBJECTIVE_ID,
    SEED_NAME,
    SYSTEM_NAME,
    UPSTREAM_CATALOG_UUID,
    seed_ai_governance_demo,
)
from app.application.catalog_import import CatalogImportService
from app.application.system_security_plans import SystemSecurityPlanService
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import (
    AssessmentPlanRecord,
    AssessmentPlanVersionRecord,
    AssessmentResultRecord,
    AssessmentResultVersionRecord,
    CatalogControlIndexRecord,
    CatalogRecord,
    CatalogRevisionRecord,
    ComponentDefinitionComponentRecord,
    ComponentDefinitionRecord,
    ComponentDefinitionSnapshotRecord,
    ControlImplementationRecord,
    DemoSeedRunRecord,
    InformationSystemRecord,
    MappingCollectionRecord,
    MappingMemberRecord,
    SystemComponentRecord,
    SystemSecurityPlanImplementationRecord,
    SystemSecurityPlanRecord,
    SystemSecurityPlanVersionRecord,
    TenantMembershipRecord,
    UserIdentityRecord,
)
from app.persistence.repositories import SQLAlchemyUnitOfWork

pytestmark = pytest.mark.integration
CATALOG_PATH = (
    Path(__file__).parents[3]
    / "examples"
    / "catalogs"
    / "nist-ai-rmf-gen-ai-1.0.0-catalog.json"
)
CATALOG_PROVENANCE_PATH = (
    Path(__file__).parents[3]
    / "examples"
    / "catalogs"
    / "nist-ai-rmf-gen-ai-1.0.0-catalog.provenance.json"
)
EU_AI_ACT_CATALOG_PATH = (
    Path(__file__).parents[3] / "examples" / "catalogs" / "eu_ai_act_catalog.json"
)
MAPPING_DRAFT_PATH = (
    Path(__file__).parents[3]
    / "examples"
    / "mappings"
    / "eu-ai-act_to_nist-genai_mapping-draft.json"
)


def _seed_demo(session_factory, tenant_id: UUID, actor_id: UUID):
    return seed_ai_governance_demo(
        session_factory=session_factory,
        tenant_id=tenant_id,
        actor_id=actor_id,
        catalog_path=CATALOG_PATH,
        catalog_provenance_path=CATALOG_PROVENANCE_PATH,
        eu_ai_act_catalog_path=EU_AI_ACT_CATALOG_PATH,
        mapping_draft_path=MAPPING_DRAFT_PATH,
    )


def _actor(session_factory, tenant_id: UUID) -> UUID:
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=f"ai-governance-seed-{uuid4()}",
            display_name="AI Governance Seed Operator",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant_id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )
        return identity.id


def _count_versions(session_factory, tenant_id: UUID) -> tuple[int, int, int]:
    with session_factory() as session:
        ssp_count = session.scalar(
            select(func.count())
            .select_from(SystemSecurityPlanVersionRecord)
            .where(SystemSecurityPlanVersionRecord.tenant_id == tenant_id)
        )
        ap_count = session.scalar(
            select(func.count())
            .select_from(AssessmentPlanVersionRecord)
            .where(AssessmentPlanVersionRecord.tenant_id == tenant_id)
        )
        ar_count = session.scalar(
            select(func.count())
            .select_from(AssessmentResultVersionRecord)
            .where(AssessmentResultVersionRecord.tenant_id == tenant_id)
        )
    return int(ssp_count or 0), int(ap_count or 0), int(ar_count or 0)


def _seed_resource_counts(session_factory, tenant_id: UUID) -> dict[str, int]:
    with session_factory() as session:
        return {
            "seed_runs": int(
                session.scalar(
                    select(func.count())
                    .select_from(DemoSeedRunRecord)
                    .where(
                        DemoSeedRunRecord.tenant_id == tenant_id,
                        DemoSeedRunRecord.seed_name == SEED_NAME,
                    )
                )
                or 0
            ),
            "catalogs": int(
                session.scalar(
                    select(func.count())
                    .select_from(CatalogRecord)
                    .where(CatalogRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "catalog_revisions": int(
                session.scalar(
                    select(func.count())
                    .select_from(CatalogRevisionRecord)
                    .where(CatalogRevisionRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "catalog_controls": int(
                session.scalar(
                    select(func.count())
                    .select_from(CatalogControlIndexRecord)
                    .where(CatalogControlIndexRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "systems": int(
                session.scalar(
                    select(func.count())
                    .select_from(InformationSystemRecord)
                    .where(InformationSystemRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "system_components": int(
                session.scalar(
                    select(func.count())
                    .select_from(SystemComponentRecord)
                    .where(SystemComponentRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "component_definitions": int(
                session.scalar(
                    select(func.count())
                    .select_from(ComponentDefinitionRecord)
                    .where(ComponentDefinitionRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "component_definition_components": int(
                session.scalar(
                    select(func.count())
                    .select_from(ComponentDefinitionComponentRecord)
                    .where(ComponentDefinitionComponentRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "component_definition_snapshots": int(
                session.scalar(
                    select(func.count())
                    .select_from(ComponentDefinitionSnapshotRecord)
                    .where(ComponentDefinitionSnapshotRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "implementations": int(
                session.scalar(
                    select(func.count())
                    .select_from(ControlImplementationRecord)
                    .where(ControlImplementationRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "ssp": int(
                session.scalar(
                    select(func.count())
                    .select_from(SystemSecurityPlanRecord)
                    .where(SystemSecurityPlanRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "ssp_versions": int(
                session.scalar(
                    select(func.count())
                    .select_from(SystemSecurityPlanVersionRecord)
                    .where(SystemSecurityPlanVersionRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "ssp_implementations": int(
                session.scalar(
                    select(func.count())
                    .select_from(SystemSecurityPlanImplementationRecord)
                    .where(SystemSecurityPlanImplementationRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "assessment_plans": int(
                session.scalar(
                    select(func.count())
                    .select_from(AssessmentPlanRecord)
                    .where(AssessmentPlanRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "assessment_plan_versions": int(
                session.scalar(
                    select(func.count())
                    .select_from(AssessmentPlanVersionRecord)
                    .where(AssessmentPlanVersionRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "assessment_results": int(
                session.scalar(
                    select(func.count())
                    .select_from(AssessmentResultRecord)
                    .where(AssessmentResultRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "assessment_result_versions": int(
                session.scalar(
                    select(func.count())
                    .select_from(AssessmentResultVersionRecord)
                    .where(AssessmentResultVersionRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "mapping_collections": int(
                session.scalar(
                    select(func.count())
                    .select_from(MappingCollectionRecord)
                    .where(MappingCollectionRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "mapping_members": int(
                session.scalar(
                    select(func.count())
                    .select_from(MappingMemberRecord)
                    .where(MappingMemberRecord.tenant_id == tenant_id)
                )
                or 0
            ),
        }


def _tenant_baseline_counts(session_factory, tenant_id: UUID) -> dict[str, int]:
    with session_factory() as session:
        return {
            "memberships": int(
                session.scalar(
                    select(func.count())
                    .select_from(TenantMembershipRecord)
                    .where(TenantMembershipRecord.tenant_id == tenant_id)
                )
                or 0
            ),
            "identities": int(
                session.scalar(select(func.count()).select_from(UserIdentityRecord)) or 0
            ),
        }


def test_ai_governance_demo_seed_is_idempotent(grc_service, session_factory) -> None:
    tenant = grc_service.create_tenant("AI Governance Seed Tenant", f"ai-demo-{uuid4().hex}")
    actor_id = _actor(session_factory, tenant.id)

    first = _seed_demo(session_factory, tenant.id, actor_id)
    assert first.applied is True
    assert first.system_id is not None
    assert first.ssp_version_id is not None
    assert first.assessment_plan_version_id is not None
    assert first.assessment_result_version_id is not None

    with session_factory() as session:
        system_count = session.scalar(
            select(func.count())
            .select_from(InformationSystemRecord)
            .where(
                InformationSystemRecord.tenant_id == tenant.id,
                InformationSystemRecord.name == SYSTEM_NAME,
            )
        )
        seed_marker = session.execute(
            text(
                "SELECT 1 FROM demo_seed_runs "
                "WHERE tenant_id = :tenant_id AND seed_name = :seed_name"
            ),
            {"tenant_id": tenant.id, "seed_name": SEED_NAME},
        ).first()
    assert int(system_count or 0) == 1
    assert seed_marker is not None

    before = _count_versions(session_factory, tenant.id)
    service = SystemSecurityPlanService(lambda: session_factory.begin())
    current = service.get_system(tenant.id, first.system_id)
    updated_description = "User-modified description retained after repeat seed run."
    service.update_system(
        tenant.id,
        actor_id,
        first.system_id,
        expected_version=current["concurrency_version"],
        name=current["name"],
        description=updated_description,
        system_boundary=current["system_boundary"],
        system_ids=current["system_ids"],
        information_types=current["information_types"],
        operational_status=current["operational_status"],
        status_remarks=current["status_remarks"],
        security_sensitivity_level=current["security_sensitivity_level"],
    )
    second = _seed_demo(session_factory, tenant.id, actor_id)
    after = _count_versions(session_factory, tenant.id)

    assert second.applied is False
    assert second.catalog_id == first.catalog_id
    assert second.revision_id == first.revision_id
    assert before == after
    assert service.get_system(tenant.id, first.system_id)["description"] == updated_description


def test_ai_governance_coverage_extension_seeds_expected_demo_data(
    grc_service, session_factory
) -> None:
    tenant = grc_service.create_tenant("AI Governance Coverage", f"ai-coverage-{uuid4().hex}")
    actor_id = _actor(session_factory, tenant.id)

    seeded = _seed_demo(session_factory, tenant.id, actor_id)
    assert seeded.applied is True
    assert seeded.governance_coverage_system_id is not None
    assert seeded.governance_coverage_mapping_collection_id is not None

    with session_factory() as session:
        eu_revision = session.scalar(
            select(CatalogRevisionRecord).where(
                CatalogRevisionRecord.tenant_id == tenant.id,
                CatalogRevisionRecord.oscal_document_uuid == EU_AI_ACT_CATALOG_UUID,
            )
        )
        assert eu_revision is not None
        eu_control_count = session.scalar(
            select(func.count())
            .select_from(CatalogControlIndexRecord)
            .where(
                CatalogControlIndexRecord.tenant_id == tenant.id,
                CatalogControlIndexRecord.catalog_revision_id == eu_revision.id,
            )
        )
        nist_revision = session.scalar(
            select(CatalogRevisionRecord).where(
                CatalogRevisionRecord.tenant_id == tenant.id,
                CatalogRevisionRecord.oscal_document_uuid == UPSTREAM_CATALOG_UUID,
            )
        )
        assert nist_revision is not None
        coverage_system = session.scalar(
            select(InformationSystemRecord).where(
                InformationSystemRecord.tenant_id == tenant.id,
                InformationSystemRecord.id == seeded.governance_coverage_system_id,
                InformationSystemRecord.name == GOVERNANCE_COVERAGE_SYSTEM_NAME,
            )
        )
        assert coverage_system is not None
        component_count = session.scalar(
            select(func.count())
            .select_from(SystemComponentRecord)
            .where(
                SystemComponentRecord.tenant_id == tenant.id,
                SystemComponentRecord.system_id == coverage_system.id,
            )
        )
        mapping_collection = session.scalar(
            select(MappingCollectionRecord).where(
                MappingCollectionRecord.tenant_id == tenant.id,
                MappingCollectionRecord.id == seeded.governance_coverage_mapping_collection_id,
            )
        )
        assert mapping_collection is not None
        member_count = session.scalar(
            select(func.count())
            .select_from(MappingMemberRecord)
            .where(
                MappingMemberRecord.tenant_id == tenant.id,
                MappingMemberRecord.collection_id == mapping_collection.id,
            )
        )
        extension_marker = session.scalar(
            select(func.count())
            .select_from(DemoSeedRunRecord)
            .where(
                DemoSeedRunRecord.tenant_id == tenant.id,
                DemoSeedRunRecord.seed_name == GOVERNANCE_COVERAGE_SEED_NAME,
            )
        )

    assert int(eu_control_count or 0) == 50
    assert int(component_count or 0) == 1
    assert int(member_count or 0) == GOVERNANCE_COVERAGE_MAPPING_COUNT * 2
    assert int(extension_marker or 0) == 1
    assert mapping_collection.document["mapping-collection"]["metadata"]["title"] == (
        GOVERNANCE_COVERAGE_MAPPING_TITLE
    )
    mappings = mapping_collection.document["mapping-collection"]["mappings"]
    assert isinstance(mappings, list)
    assert len(mappings) == 1
    assert len(mappings[0]["maps"]) == GOVERNANCE_COVERAGE_MAPPING_COUNT

    repeated = _seed_demo(session_factory, tenant.id, actor_id)
    assert repeated.applied is False
    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(MappingCollectionRecord)
                .where(MappingCollectionRecord.tenant_id == tenant.id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(InformationSystemRecord)
                .where(
                    InformationSystemRecord.tenant_id == tenant.id,
                    InformationSystemRecord.name == GOVERNANCE_COVERAGE_SYSTEM_NAME,
                )
            )
            == 1
        )


def test_governance_coverage_extension_applies_to_existing_demo_marker(
    grc_service, session_factory
) -> None:
    tenant = grc_service.create_tenant("AI Governance Existing Demo", f"ai-existing-{uuid4().hex}")
    actor_id = _actor(session_factory, tenant.id)

    importer = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory))
    importer.import_catalog(tenant.id, CATALOG_PATH.read_bytes())

    with session_factory.begin() as session:
        session.execute(
            insert(DemoSeedRunRecord)
            .values(tenant_id=tenant.id, seed_name=SEED_NAME)
            .on_conflict_do_nothing(index_elements=["tenant_id", "seed_name"])
        )

    result = _seed_demo(session_factory, tenant.id, actor_id)
    assert result.applied is True
    assert result.system_id is None
    assert result.governance_coverage_system_id is not None
    assert result.governance_coverage_mapping_collection_id is not None


def test_governance_coverage_extension_rolls_back_on_invalid_mapping_reference(
    grc_service, session_factory, tmp_path
) -> None:
    tenant = grc_service.create_tenant("AI Governance Bad Mapping", f"ai-bad-map-{uuid4().hex}")
    actor_id = _actor(session_factory, tenant.id)
    baseline = _tenant_baseline_counts(session_factory, tenant.id)

    draft = json.loads(MAPPING_DRAFT_PATH.read_text(encoding="utf-8"))
    draft["mappings"][0]["source_control_id"] = "aia-not-present"
    invalid_mapping_path = tmp_path / "invalid-eu-nist-draft.json"
    invalid_mapping_path.write_text(json.dumps(draft), encoding="utf-8")

    with pytest.raises(ValueError, match="Source controls do not exist"):
        seed_ai_governance_demo(
            session_factory=session_factory,
            tenant_id=tenant.id,
            actor_id=actor_id,
            catalog_path=CATALOG_PATH,
            catalog_provenance_path=CATALOG_PROVENANCE_PATH,
            eu_ai_act_catalog_path=EU_AI_ACT_CATALOG_PATH,
            mapping_draft_path=invalid_mapping_path,
        )

    rolled_back = _seed_resource_counts(session_factory, tenant.id)
    assert all(count == 0 for count in rolled_back.values())
    assert _tenant_baseline_counts(session_factory, tenant.id) == baseline


# Approved control -> (concrete system component, originating reusable safeguard).
APPROVED_ASSOCIATIONS = {
    "MG-2.2-006": (
        "Model registry and release records",
        "Model and dataset version management (fictional demo)",
    ),
    "MP-1.1-008": (
        "Human approval workflow",
        "Human oversight of agent actions (fictional demo)",
    ),
    "GV-1.2-003": ("AI governance policy set", "AI governance policies (fictional demo)"),
    "GV-4.1-003": ("AI governance policy set", "AI governance policies (fictional demo)"),
    "MS-2.7-016": ("AI red-teaming service", "AI security testing (fictional demo)"),
}
REGISTER_TO_OSCAL_STATUS = {"implemented": "implemented", "in_progress": "partial"}
SAMPLED_RELEASE_RECORDS = ("REL-2026-041", "REL-2026-042", "REL-2026-043")
FICTIONAL_EVIDENCE_PREFIX = "https://example.demo/fictional/"


def _published_chain(session_factory, tenant_id: UUID, seeded) -> dict[str, Any]:
    with session_factory() as session:
        ssp_version = session.scalar(
            select(SystemSecurityPlanVersionRecord).where(
                SystemSecurityPlanVersionRecord.tenant_id == tenant_id,
                SystemSecurityPlanVersionRecord.id == seeded.ssp_version_id,
            )
        )
        plan_version = session.scalar(
            select(AssessmentPlanVersionRecord).where(
                AssessmentPlanVersionRecord.tenant_id == tenant_id,
                AssessmentPlanVersionRecord.id == seeded.assessment_plan_version_id,
            )
        )
        result_version = session.scalar(
            select(AssessmentResultVersionRecord).where(
                AssessmentResultVersionRecord.tenant_id == tenant_id,
                AssessmentResultVersionRecord.id == seeded.assessment_result_version_id,
            )
        )
        components = session.scalars(
            select(SystemComponentRecord).where(
                SystemComponentRecord.tenant_id == tenant_id,
                SystemComponentRecord.system_id == seeded.system_id,
            )
        ).all()
        snapshots = {
            item.id: item.document
            for item in session.scalars(
                select(ComponentDefinitionSnapshotRecord).where(
                    ComponentDefinitionSnapshotRecord.tenant_id == tenant_id
                )
            )
        }
        implementations = {
            str(item.id): item
            for item in session.scalars(
                select(ControlImplementationRecord).where(
                    ControlImplementationRecord.tenant_id == tenant_id
                )
            )
        }
    assert ssp_version is not None
    assert plan_version is not None
    assert result_version is not None
    return {
        "ssp_version": ssp_version,
        "plan_version": plan_version,
        "result_version": result_version,
        "ssp": ssp_version.document["system-security-plan"],
        "plan": plan_version.document["assessment-plan"],
        "results": result_version.document["assessment-results"],
        "components": components,
        "snapshots": snapshots,
        "implementations": implementations,
    }


def _selected_controls(selection_owner: dict[str, Any]) -> list[str]:
    return [
        include["control-id"]
        for selection in selection_owner.get("control-selections", [])
        for include in selection.get("include-controls", [])
    ]


def _selected_objectives(selection_owner: dict[str, Any]) -> list[str]:
    return [
        include["objective-id"]
        for selection in selection_owner.get("control-objective-selections", [])
        for include in selection.get("include-objectives", [])
    ]


def _subject_uuids(subject_owner: dict[str, Any], key: str = "subjects") -> set[str]:
    return {
        include["subject-uuid"]
        for subject in subject_owner.get(key, [])
        for include in subject.get("include-subjects", [])
    }


def test_ai_governance_demo_seed_publishes_semantically_consistent_chain(
    grc_service, session_factory
) -> None:
    tenant = grc_service.create_tenant("AI Governance Semantics", f"ai-demo-{uuid4().hex}")
    actor_id = _actor(session_factory, tenant.id)
    seeded = _seed_demo(session_factory, tenant.id, actor_id)
    assert seeded.applied is True
    chain = _published_chain(session_factory, tenant.id, seeded)
    ssp, plan, results = chain["ssp"], chain["plan"], chain["results"]

    # Published documents conform to their Trestle models and official JSON Schemas.
    validate_system_security_plan_document(chain["ssp_version"].document)
    validate_assessment_plan_document(chain["plan_version"].document)
    validate_assessment_result_document(chain["result_version"].document)
    for snapshot_document in chain["snapshots"].values():
        validate_component_definition_document(snapshot_document)

    # Historical version references are pinned along the whole chain.
    assert ssp["import-profile"]["href"].endswith(f"/{seeded.revision_id}/export")
    assert plan["import-ssp"]["href"].endswith(f"/{seeded.ssp_version_id}/export")
    assert results["import-ap"]["href"].endswith(
        f"/{seeded.assessment_plan_version_id}/export"
    )
    assert chain["plan_version"].system_security_plan_version_id == seeded.ssp_version_id
    assert (
        chain["result_version"].assessment_plan_version_id
        == seeded.assessment_plan_version_id
    )

    # --- SSP: approved controls, safeguard/component associations, contributions ---
    assert ssp["system-characteristics"]["system-name"] == SYSTEM_NAME
    ssp_components = {item["uuid"]: item for item in ssp["system-implementation"]["components"]}
    component_records = {str(item.oscal_component_uuid): item for item in chain["components"]}
    component_descriptions = [item["description"] for item in ssp_components.values()]
    assert len(set(component_descriptions)) == len(component_descriptions)
    assert all("ictional" in description for description in component_descriptions)

    requirements = {
        item["control-id"]: item
        for item in ssp["control-implementation"]["implemented-requirements"]
    }
    assert set(requirements) == set(APPROVED_ASSOCIATIONS)

    contributing_component: dict[str, str] = {}
    safeguard_by_control: dict[str, str] = {}
    contribution_descriptions: list[str] = []
    contribution_links: list[str] = []
    for control_id, requirement in requirements.items():
        expected_component, expected_safeguard = APPROVED_ASSOCIATIONS[control_id]
        assert len(requirement["by-components"]) == 1
        contribution = requirement["by-components"][0]
        component_uuid = contribution["component-uuid"]
        contributing_component[control_id] = component_uuid
        assert ssp_components[component_uuid]["title"] == expected_component

        # The contributing component is adopted from the safeguard that addresses this
        # exact control.
        record = component_records[component_uuid]
        assert record.source_snapshot_id is not None
        definition = chain["snapshots"][record.source_snapshot_id]["component-definition"]
        safeguard = next(
            item
            for item in definition["components"]
            if UUID(item["uuid"]) == record.source_component_uuid
        )
        assert safeguard["title"] == expected_safeguard
        assert safeguard["type"] == ssp_components[component_uuid]["type"]
        safeguard_controls = {
            item["control-id"]
            for implementation in safeguard["control-implementations"]
            for item in implementation["implemented-requirements"]
        }
        assert control_id in safeguard_controls
        safeguard_by_control[control_id] = safeguard["title"]

        # Register status, OSCAL status and explanation are aligned.
        implementation = chain["implementations"][contribution["uuid"]]
        status = contribution["implementation-status"]
        assert REGISTER_TO_OSCAL_STATUS[implementation.status] == status["state"]
        assert status["remarks"].strip()
        assert "ictional" in contribution["description"]
        contribution_descriptions.append(contribution["description"])
        links = [link["href"] for link in contribution["links"]]
        assert links
        assert all(link.startswith(FICTIONAL_EVIDENCE_PREFIX) for link in links)
        contribution_links.extend(links)

    assert len(set(contribution_descriptions)) == len(contribution_descriptions)
    assert len(set(contribution_links)) == len(contribution_links)
    # Security testing is a separate safeguard from human oversight.
    assert safeguard_by_control["MS-2.7-016"] != safeguard_by_control["MP-1.1-008"]
    # Safeguards address exactly the approved controls.
    all_safeguard_controls = {
        item["control-id"]
        for snapshot_document in chain["snapshots"].values()
        for component in snapshot_document["component-definition"]["components"]
        for implementation in component["control-implementations"]
        for item in implementation["implemented-requirements"]
    }
    assert all_safeguard_controls == set(APPROVED_ASSOCIATIONS)

    # --- Assessment Plan: objectives, activities, tasks, subjects, roles ---
    assert set(_selected_controls(plan["reviewed-controls"])) == set(APPROVED_ASSOCIATIONS)
    objective_controls: dict[str, str] = {}
    objective_methods: dict[str, set[str]] = {}
    objective_prose: dict[str, str] = {}
    for local in plan["local-definitions"]["objectives-and-methods"]:
        objective_part = next(part for part in local["parts"] if part["name"] == "objective")
        objective_controls[objective_part["id"]] = local["control-id"]
        objective_prose[objective_part["id"]] = objective_part["prose"]
        objective_methods[objective_part["id"]] = {
            part["prose"] for part in local["parts"] if part["name"] == "assessment-method"
        }
    assert objective_controls[MODEL_VERSION_OBJECTIVE_ID] == MODEL_VERSION_CONTROL_ID
    assert MODEL_VERSION_CONTROL_ID == "MG-2.2-006"
    assert set(objective_controls.values()) == set(APPROVED_ASSOCIATIONS)
    assert set(_selected_objectives(plan["reviewed-controls"])) == set(objective_controls)
    model_objective_prose = objective_prose[MODEL_VERSION_OBJECTIVE_ID].lower()
    for expected_term in ("three", "exact approved model version", "registry record"):
        assert expected_term in model_objective_prose

    activities = {item["uuid"]: item for item in plan["local-definitions"]["activities"]}
    activity_methods: dict[str, set[str]] = {}
    for activity_uuid, activity in activities.items():
        activity_controls = set(_selected_controls(activity["related-controls"]))
        activity_objectives = _selected_objectives(activity["related-controls"])
        assert activity_objectives
        # Every referenced objective belongs to one of the activity's selected controls.
        assert {objective_controls[item] for item in activity_objectives} == activity_controls
        activity_methods[activity_uuid] = {
            prop["value"] for prop in activity["props"] if prop["name"] == "method"
        }
        for objective_id in activity_objectives:
            assert objective_methods[objective_id] <= activity_methods[activity_uuid]
        assert any(prop["name"] == "planned-evidence" for prop in activity["props"])
    activities_by_objective = {
        objective_id: [
            activity_uuid
            for activity_uuid, activity in activities.items()
            if objective_id in _selected_objectives(activity["related-controls"])
        ]
        for objective_id in objective_controls
    }
    assert all(len(items) == 1 for items in activities_by_objective.values())
    model_activity_uuid = activities_by_objective[MODEL_VERSION_OBJECTIVE_ID][0]
    model_activity = activities[model_activity_uuid]
    assert _selected_controls(model_activity["related-controls"]) == [MODEL_VERSION_CONTROL_ID]
    assert _selected_objectives(model_activity["related-controls"]) == [
        MODEL_VERSION_OBJECTIVE_ID
    ]
    assert len(model_activity["steps"]) >= 2

    adopted_component_uuids = {
        uuid for uuid, record in component_records.items() if record.source_snapshot_id
    }
    assert _subject_uuids(plan, "assessment-subjects") == adopted_component_uuids

    party_uuids = {party["uuid"] for party in plan["metadata"]["parties"]}
    role_ids = {role["id"] for role in plan["metadata"]["roles"]}
    task_by_activity: dict[str, dict[str, Any]] = {}
    for task in plan["tasks"]:
        associated = [item["activity-uuid"] for item in task["associated-activities"]]
        assert associated
        task_controls: set[str] = set()
        for activity_uuid in associated:
            assert activity_uuid not in task_by_activity
            task_by_activity[activity_uuid] = task
            task_controls.update(_selected_controls(activities[activity_uuid]["related-controls"]))
        # Task subjects are the components that contribute to the task's controls.
        assert _subject_uuids(task) == {contributing_component[item] for item in task_controls}
        assert task["responsible-roles"]
        for role in task["responsible-roles"]:
            assert role["role-id"] in role_ids
            assert role["party-uuids"]
            assert set(role["party-uuids"]) <= party_uuids
    assert set(task_by_activity) == set(activities)

    # --- Assessment Results: scope, observation, evidence, finding ---
    assert len(results["results"]) == 1
    result = results["results"][0]
    assert _selected_controls(result["reviewed-controls"]) == [MODEL_VERSION_CONTROL_ID]
    assert "not assessed" in result["description"]

    observations = {item["uuid"]: item for item in result["observations"]}
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    target = finding["target"]
    assert target["type"] == "objective-id"
    assert target["target-id"] == MODEL_VERSION_OBJECTIVE_ID
    assert target["status"]["state"] == "not-satisfied"
    # The targeted local objective exists in the pinned Assessment Plan and its control
    # is inside the actual reviewed scope.
    assert target["target-id"] in objective_controls
    assert objective_controls[target["target-id"]] in _selected_controls(
        result["reviewed-controls"]
    )
    related = [item["observation-uuid"] for item in finding["related-observations"]]
    assert related
    assert set(related) <= set(observations)

    model_task = task_by_activity[model_activity_uuid]
    resources = {item["uuid"]: item for item in results["back-matter"]["resources"]}
    task_window = model_task["timing"]["within-date-range"]
    result_start = datetime.fromisoformat(result["start"])
    result_end = datetime.fromisoformat(result["end"])
    assert datetime.fromisoformat(task_window["start"]) <= result_start
    assert result_end <= datetime.fromisoformat(task_window["end"])
    # The fictional assessment ends before the documents are published.
    assert result_end <= datetime.fromisoformat(results["metadata"]["last-modified"])
    for observation_uuid in related:
        observation = observations[observation_uuid]
        assert set(observation["methods"]) <= activity_methods[model_activity_uuid]
        assert {item["subject-uuid"] for item in observation["subjects"]} == _subject_uuids(
            model_task
        )
        assert (
            result_start <= datetime.fromisoformat(observation["collected"]) <= result_end
        )
        assert "ictional" in observation["description"]
        for release_record in SAMPLED_RELEASE_RECORDS:
            assert release_record in observation["description"]
        evidence_resources = [
            resources[item["href"].removeprefix("#")]
            for item in observation["relevant-evidence"]
        ]
        assert len(evidence_resources) == 2
        evidence_titles = " ".join(item["title"] for item in evidence_resources).lower()
        assert "model registry" in evidence_titles
        assert "release records" in evidence_titles
        for resource in evidence_resources:
            assert "ictional" in resource["title"]
            assert "not real or verified evidence" in resource["description"]
            assert all(
                link["href"].startswith(FICTIONAL_EVIDENCE_PREFIX)
                for link in resource["rlinks"]
            )

    # The finding explains the objective-level conclusion and does not judge the control.
    finding_description = finding["description"]
    assert "ictional" in finding_description
    assert SAMPLED_RELEASE_RECORDS[2] in finding_description
    assert "local objective only" in finding_description
    assert all(
        other_control not in finding_description
        for other_control in set(APPROVED_ASSOCIATIONS) - {MODEL_VERSION_CONTROL_ID}
    )

    # A repeated seed run leaves the published immutable versions untouched.
    repeated = _seed_demo(session_factory, tenant.id, actor_id)
    assert repeated.applied is False
    after = _published_chain(session_factory, tenant.id, seeded)
    for key in ("ssp_version", "plan_version", "result_version"):
        assert after[key].content_sha256 == chain[key].content_sha256
        assert after[key].document == chain[key].document
    assert _count_versions(session_factory, tenant.id) == (1, 1, 1)


def test_ai_governance_demo_seed_requires_active_actor_membership(
    grc_service, session_factory
) -> None:
    tenant = grc_service.create_tenant("AI Governance Seed Context", f"ai-demo-{uuid4().hex}")
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=f"ai-governance-no-membership-{uuid4()}",
            display_name="No Membership",
            email=None,
        )

    with pytest.raises(ValueError, match="active tenant membership"):
        _seed_demo(session_factory, tenant.id, identity.id)


def test_ai_governance_demo_seed_rolls_back_mid_lifecycle_failure(
    grc_service, session_factory, monkeypatch
) -> None:
    tenant = grc_service.create_tenant("AI Governance Rollback", f"ai-demo-{uuid4().hex}")
    actor_id = _actor(session_factory, tenant.id)
    baseline = _tenant_baseline_counts(session_factory, tenant.id)

    def fail_after_db_writes(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
        raise RuntimeError("Injected failure after seed resource writes.")

    monkeypatch.setattr(ai_demo_module, "_validate_historical_chain", fail_after_db_writes)

    with pytest.raises(RuntimeError, match="Injected failure"):
        _seed_demo(session_factory, tenant.id, actor_id)

    # Read through a fresh session and assert the failed seed left no persistent resources.
    rolled_back = _seed_resource_counts(session_factory, tenant.id)
    assert all(count == 0 for count in rolled_back.values())
    assert _tenant_baseline_counts(session_factory, tenant.id) == baseline

    monkeypatch.undo()

    applied = _seed_demo(session_factory, tenant.id, actor_id)
    assert applied.applied is True

    no_op = _seed_demo(session_factory, tenant.id, actor_id)
    assert no_op.applied is False


