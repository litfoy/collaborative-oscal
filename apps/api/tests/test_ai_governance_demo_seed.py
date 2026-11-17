from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text

from app.application import ai_governance_demo as ai_demo_module
from app.application.ai_governance_demo import (
    SEED_NAME,
    SYSTEM_NAME,
    seed_ai_governance_demo,
)
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
    SystemComponentRecord,
    SystemSecurityPlanImplementationRecord,
    SystemSecurityPlanRecord,
    SystemSecurityPlanVersionRecord,
    TenantMembershipRecord,
    UserIdentityRecord,
)

pytestmark = pytest.mark.integration
CATALOG_PATH = (
    Path(__file__).parents[3]
    / "examples"
    / "catalogs"
    / "nist-ai-rmf-gen-ai-1.0.0-catalog.json"
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

    first = seed_ai_governance_demo(
        session_factory=session_factory,
        tenant_id=tenant.id,
        actor_id=actor_id,
        catalog_path=CATALOG_PATH,
    )
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
        name=current["name"],
        description=updated_description,
        system_boundary=current["system_boundary"],
        system_ids=current["system_ids"],
        information_types=current["information_types"],
        operational_status=current["operational_status"],
        status_remarks=current["status_remarks"],
        security_sensitivity_level=current["security_sensitivity_level"],
    )
    second = seed_ai_governance_demo(
        session_factory=session_factory,
        tenant_id=tenant.id,
        actor_id=actor_id,
        catalog_path=CATALOG_PATH,
    )
    after = _count_versions(session_factory, tenant.id)

    assert second.applied is False
    assert second.catalog_id == first.catalog_id
    assert second.revision_id == first.revision_id
    assert before == after
    assert service.get_system(tenant.id, first.system_id)["description"] == updated_description


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
        seed_ai_governance_demo(
            session_factory=session_factory,
            tenant_id=tenant.id,
            actor_id=identity.id,
            catalog_path=CATALOG_PATH,
        )


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
        seed_ai_governance_demo(
            session_factory=session_factory,
            tenant_id=tenant.id,
            actor_id=actor_id,
            catalog_path=CATALOG_PATH,
        )

    # Read through a fresh session and assert the failed seed left no persistent resources.
    rolled_back = _seed_resource_counts(session_factory, tenant.id)
    assert all(count == 0 for count in rolled_back.values())
    assert _tenant_baseline_counts(session_factory, tenant.id) == baseline

    monkeypatch.undo()

    applied = seed_ai_governance_demo(
        session_factory=session_factory,
        tenant_id=tenant.id,
        actor_id=actor_id,
        catalog_path=CATALOG_PATH,
    )
    assert applied.applied is True

    no_op = seed_ai_governance_demo(
        session_factory=session_factory,
        tenant_id=tenant.id,
        actor_id=actor_id,
        catalog_path=CATALOG_PATH,
    )
    assert no_op.applied is False


