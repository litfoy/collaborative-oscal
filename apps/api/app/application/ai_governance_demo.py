from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.application.assessment_plans import AssessmentPlanService
from app.application.assessment_results import AssessmentResultService
from app.application.catalog_import import CatalogImportMetadata, CatalogImportService
from app.application.component_definitions import (
    ComponentDefinitionService,
    ComponentRequirementInput,
)
from app.application.implementations import ImplementationService
from app.application.system_security_plans import SystemSecurityPlanService
from app.domain.implementations import (
    ImplementationInformation,
    ImplementationStatus,
    OscalImplementationStatus,
)
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogRecord,
    CatalogRevisionRecord,
    DemoSeedRunRecord,
    InformationSystemRecord,
    TenantMembershipRecord,
    TenantRecord,
)
from app.persistence.repositories import SQLAlchemyUnitOfWork

SEED_NAME = "ai-governance-demo-v1"
SEED_LOCK_KEY = 8188815197680786
SYSTEM_NAME = "Agentic AI Development Platform"

UPSTREAM_CATALOG_UUID = UUID("1cead03a-d26a-400d-b16b-169816e2e592")
UPSTREAM_CATALOG_OSCAL_VERSION = "1.1.2"
UPSTREAM_CATALOG_SHA256 = "5d23b8f05ab5d8e96c552e2a9dcc1f0da9062fe9dcbe61b8de3136edf4cb703e"
UPSTREAM_CATALOG_SOURCE_URI = (
    "https://github.com/oscal-compass/oscal-content/blob/"
    "56b1adba350b11f200636b94a64615b29fae33ed/"
    "catalogs/nist_ai_rmf_gen_ai/1.0.0/catalog.json"
)
UPSTREAM_CATALOG_SOURCE_ORGANIZATION = "OSCAL Compass"
UPSTREAM_CATALOG_LICENSE = "Apache-2.0"

PRIORITIZED_CONTROL_IDS = (
    "MG-3.1-009",
    "MP-1.1-008",
    "MS-2.7-016",
    "GV-4.1-003",
    "GV-1.2-003",
)


@dataclass(frozen=True, slots=True)
class AIGovernanceDemoSeedResult:
    applied: bool
    catalog_id: UUID
    revision_id: UUID
    system_id: UUID | None
    ssp_version_id: UUID | None
    assessment_plan_version_id: UUID | None
    assessment_result_version_id: UUID | None


def seed_ai_governance_demo(
    *,
    session_factory: sessionmaker[Session],
    tenant_id: UUID,
    actor_id: UUID,
    catalog_path: Path,
) -> AIGovernanceDemoSeedResult:
    with session_factory.begin() as session:
        connection = session.connection()
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SEED_LOCK_KEY})
        _validate_seed_context(session, tenant_id, actor_id)
        if session.scalar(
            select(DemoSeedRunRecord.seed_name).where(
                DemoSeedRunRecord.tenant_id == tenant_id,
                DemoSeedRunRecord.seed_name == SEED_NAME,
            )
        ):
            existing = _existing_catalog_revision(session, tenant_id)
            if existing is None:
                raise RuntimeError("Seed marker exists but upstream catalog revision is missing.")
            return AIGovernanceDemoSeedResult(
                applied=False,
                catalog_id=existing.catalog_id,
                revision_id=existing.id,
                system_id=None,
                ssp_version_id=None,
                assessment_plan_version_id=None,
                assessment_result_version_id=None,
            )

        if session.scalar(
            select(InformationSystemRecord.id).where(
                InformationSystemRecord.tenant_id == tenant_id,
                InformationSystemRecord.name == SYSTEM_NAME,
            )
        ):
            raise ValueError(
                "Seed marker is missing, but demo System name already exists. "
                "Refusing to create duplicate content."
            )

        scoped_factory = sessionmaker(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        def begin_scope():
            return scoped_factory.begin()

        def unit_of_work_factory() -> SQLAlchemyUnitOfWork:
            return SQLAlchemyUnitOfWork(scoped_factory)

        catalog, revision = _ensure_upstream_catalog(
            session,
            tenant_id=tenant_id,
            catalog_path=catalog_path,
            unit_of_work_factory=unit_of_work_factory,
        )
        _validate_prioritized_controls(session, tenant_id, revision.id)
        statement_target = _select_statement_target(_statement_ids_by_control(revision.content))

        definitions = ComponentDefinitionService(begin_scope)
        implementations = ImplementationService(begin_scope)
        ssp = SystemSecurityPlanService(begin_scope)
        assessment_plans = AssessmentPlanService(begin_scope)
        assessment_results = AssessmentResultService(begin_scope)

        transparency_definition = definitions.create(
            tenant_id,
            actor_id,
            "AI transparency safeguards (fictional demo)",
            "policy",
            "Fictional demonstration data only. Not an actual compliance claim.",
            [
                ComponentRequirementInput(
                    catalog.id,
                    revision.id,
                    "MG-3.1-009",
                    "Fictional demo: publish model cards and training provenance.",
                ),
                ComponentRequirementInput(
                    catalog.id,
                    revision.id,
                    "MP-1.1-008",
                    "Fictional demo: include acceptable-use checks in release approvals.",
                ),
            ],
        )
        oversight_definition = definitions.create(
            tenant_id,
            actor_id,
            "Human oversight safeguards (fictional demo)",
            "process-procedure",
            "Fictional demonstration data only. Not an actual compliance claim.",
            [
                ComponentRequirementInput(
                    catalog.id,
                    revision.id,
                    "GV-4.1-003",
                    "Fictional demo: require explicit human release approvals.",
                ),
                ComponentRequirementInput(
                    catalog.id,
                    revision.id,
                    "GV-1.2-003",
                    "Fictional demo: maintain accountable governance ownership.",
                ),
                ComponentRequirementInput(
                    catalog.id,
                    revision.id,
                    "MS-2.7-016",
                    "Fictional demo: execute AI security testing and red-teaming.",
                ),
            ],
        )

        system = ssp.create_system(
            tenant_id,
            actor_id,
            name=SYSTEM_NAME,
            organization_id=None,
            description=(
                "Fictional demonstration data only. Sample enterprise AI platform for "
                "authoring workflows."
            ),
            system_boundary=(
                "Fictional demonstration data only. Includes model training, registry, "
                "approval, and deployment flows."
            ),
            system_ids=[
                {
                    "id": "agentic-ai-platform.demo.internal",
                    "identifier_type": "https://example.demo/system-id",
                }
            ],
            information_types=[
                {
                    "title": "Model training metadata",
                    "description": "Fictional demo lineage and provenance records.",
                },
                {
                    "title": "Model evaluation artifacts",
                    "description": "Fictional demo quality and safety test results.",
                },
            ],
            operational_status="operational",
            status_remarks=None,
            security_sensitivity_level="moderate",
        )
        system_component = ssp.create_component(
            tenant_id,
            actor_id,
            system["id"],
            component_type="this-system",
            title="Platform governance core",
            description="Fictional demonstration data only.",
            purpose="Centralized governance guardrails.",
            status="operational",
            status_remarks=None,
            is_system_component=True,
        )
        red_team_component = ssp.create_component(
            tenant_id,
            actor_id,
            system["id"],
            component_type="service",
            title="AI security testing service",
            description="Fictional demonstration data only.",
            purpose="Run adversarial AI abuse simulations.",
            status="operational",
            status_remarks=None,
        )
        adopted_transparency = ssp.adopt_component_definition(
            tenant_id,
            actor_id,
            system["id"],
            transparency_definition.id,
            transparency_definition.components[0].id,
            title="Model transparency workflow",
            description="Fictional demonstration data only.",
            purpose="Maintain model documentation and traceability.",
            status="operational",
            status_remarks=None,
        )
        adopted_oversight = ssp.adopt_component_definition(
            tenant_id,
            actor_id,
            system["id"],
            oversight_definition.id,
            oversight_definition.components[0].id,
            title="Human oversight workflow",
            description="Fictional demonstration data only.",
            purpose="Ensure accountable human decisions before release.",
            status="operational",
            status_remarks=None,
        )

        ssp_plan = ssp.create_plan(
            tenant_id,
            actor_id,
            system["id"],
            catalog_id=catalog.id,
            revision_id=revision.id,
            title="Agentic AI Development Platform SSP (fictional demo)",
            control_implementation_description=(
                "Fictional demonstration data only. Illustrative implementation records."
            ),
        )
        for control_id, component_id, status in (
            ("MG-3.1-009", adopted_transparency["id"], OscalImplementationStatus.IMPLEMENTED),
            ("MP-1.1-008", adopted_transparency["id"], OscalImplementationStatus.IMPLEMENTED),
            ("GV-4.1-003", adopted_oversight["id"], OscalImplementationStatus.PARTIAL),
            ("GV-1.2-003", system_component["id"], OscalImplementationStatus.PARTIAL),
            ("MS-2.7-016", red_team_component["id"], OscalImplementationStatus.IMPLEMENTED),
        ):
            record = implementations.create(
                tenant_id,
                actor_id,
                catalog.id,
                revision.id,
                control_id,
                None,
                None,
                ImplementationInformation(
                    description=(
                        "Fictional demonstration data only. Not an actual compliance claim."
                    ),
                    status=ImplementationStatus.IN_PROGRESS,
                    evidence_references=["https://example.demo/evidence/fictional-ai-governance"],
                    responsibilities=[],
                    oscal_implementation_status=status,
                    oscal_status_explanation=(
                        "Fictional demonstration data only. Illustrative staged rollout."
                    ),
                ),
            )
            ssp.associate_implementation(
                tenant_id,
                actor_id,
                ssp_plan["id"],
                record.id,
                component_id,
            )

        if not ssp.validate_plan(tenant_id, ssp_plan["id"])["valid"]:
            raise RuntimeError("Generated SSP draft did not pass validation.")
        ssp_version = ssp.create_version(tenant_id, actor_id, ssp_plan["id"])

        assessment_plan = assessment_plans.create_plan(
            tenant_id,
            actor_id,
            system["id"],
            ssp_version_id=ssp_version["id"],
            title="Agentic AI Governance Assessment Plan (fictional demo)",
            description="Fictional demonstration data only.",
        )
        subject_uuids = [
            str(adopted_transparency["oscal_component_uuid"]),
            str(adopted_oversight["oscal_component_uuid"]),
            str(red_team_component["oscal_component_uuid"]),
        ]
        assessment_plans.update_plan(
            tenant_id,
            actor_id,
            assessment_plan["id"],
            title=assessment_plan["title"],
            description=assessment_plan["description"],
            working_data={
                "control_ids": list(PRIORITIZED_CONTROL_IDS),
                "source_objectives": [],
                "local_objectives": [
                    {
                        "objective_id": "local-model-version-traceability",
                        "control_id": "MG-3.1-009",
                        "description": "Fictional demo objective for version traceability.",
                        "methods": ["EXAMINE", "TEST"],
                    }
                ],
                "subject_uuids": subject_uuids,
                "activities": [
                    {
                        "title": "Review model documentation",
                        "description": "Fictional demonstration data only.",
                        "methods": ["EXAMINE"],
                        "steps": [],
                        "control_ids": ["MG-3.1-009", "MP-1.1-008"],
                        "objective_ids": ["local-model-version-traceability"],
                        "planned_evidence": "Fictional model registry exports.",
                    },
                    {
                        "title": "Execute adversarial testing",
                        "description": "Fictional demonstration data only.",
                        "methods": ["TEST"],
                        "steps": [],
                        "control_ids": ["MS-2.7-016", "GV-4.1-003", "GV-1.2-003"],
                        "objective_ids": ["local-model-version-traceability"],
                        "planned_evidence": "Fictional red-team report references.",
                    },
                ],
                "tasks": [
                    {
                        "title": "Coordinate governance assessment",
                        "description": "Fictional demonstration data only.",
                        "activity_ids": [],
                        "subject_uuids": subject_uuids,
                        "role_ids": ["lead-assessor"],
                        "on_date": "2026-11-17T10:00:00+00:00",
                        "start": None,
                        "end": None,
                    }
                ],
                "roles": [
                    {
                        "role_id": "lead-assessor",
                        "title": "Lead Assessor",
                        "description": "Fictional demonstration data only.",
                        "party_uuids": [],
                    }
                ],
                "parties": [{"party_type": "person", "name": "Jordan Demo Assessor"}],
                "terms": "Fictional demonstration data only. Not evidence of real compliance.",
            },
        )
        if not assessment_plans.validate_plan(tenant_id, assessment_plan["id"])["valid"]:
            raise RuntimeError("Generated Assessment Plan draft did not pass validation.")
        assessment_plan_version = assessment_plans.create_version(
            tenant_id,
            actor_id,
            assessment_plan["id"],
        )

        assessment_result = assessment_results.create_result(
            tenant_id,
            actor_id,
            system["id"],
            assessment_plan_id=assessment_plan["id"],
            assessment_plan_version_id=assessment_plan_version["id"],
            title="Agentic AI Governance Assessment Results (fictional demo)",
            description="Fictional demonstration data only.",
        )
        updated_result = assessment_results.update_result(
            tenant_id,
            actor_id,
            assessment_result["id"],
            title=assessment_result["title"],
            description=assessment_result["description"],
            working_data={
                "reviewed_control_ids": list(PRIORITIZED_CONTROL_IDS),
                "start": "2026-11-17T10:00:00+00:00",
                "end": "2026-11-17T12:00:00+00:00",
                "observations": [
                    {
                        "title": "Model registry traceability gap",
                        "description": "Fictional demonstration data only.",
                        "methods": ["EXAMINE", "TEST"],
                        "collected_at": "2026-11-17T11:00:00+00:00",
                        "subject_uuids": [str(adopted_transparency["oscal_component_uuid"])],
                        "evidence": [
                            {
                                "title": "Deployment pipeline execution log",
                                "description": "Fictional demonstration data only.",
                                "href": "https://example.demo/evidence/fictional-model-traceability-log",
                            }
                        ],
                    }
                ],
                "findings": [
                    {
                        "title": "Insufficient exact model-version traceability",
                        "description": (
                            "Fictional demonstration finding: one sampled release lacked "
                            "an exact approved model-version identifier."
                        ),
                        "target_type": "statement-id",
                        "target_id": statement_target,
                        "status": "not-satisfied",
                        "related_observation_ids": [],
                    }
                ],
            },
        )
        observation_id = str(updated_result["observations"][0]["id"])
        assessment_results.update_result(
            tenant_id,
            actor_id,
            assessment_result["id"],
            title=assessment_result["title"],
            description=assessment_result["description"],
            working_data={
                "reviewed_control_ids": list(PRIORITIZED_CONTROL_IDS),
                "start": "2026-11-17T10:00:00+00:00",
                "end": "2026-11-17T12:00:00+00:00",
                "observations": updated_result["observations"],
                "findings": [
                    {
                        "id": updated_result["findings"][0]["id"],
                        "title": "Insufficient exact model-version traceability",
                        "description": (
                            "Fictional demonstration finding: one sampled release lacked "
                            "an exact approved model-version identifier."
                        ),
                        "target_type": "statement-id",
                        "target_id": statement_target,
                        "status": "not-satisfied",
                        "related_observation_ids": [observation_id],
                    }
                ],
            },
        )
        if not assessment_results.validate_result(tenant_id, assessment_result["id"])["valid"]:
            raise RuntimeError("Generated Assessment Results draft did not pass validation.")
        assessment_result_version = assessment_results.create_version(
            tenant_id,
            actor_id,
            assessment_result["id"],
        )

        _validate_historical_chain(
            ssp,
            assessment_plans,
            assessment_results,
            tenant_id=tenant_id,
            ssp_plan_id=ssp_plan["id"],
            ssp_version_id=ssp_version["id"],
            assessment_plan_id=assessment_plan["id"],
            assessment_plan_version_id=assessment_plan_version["id"],
            assessment_result_id=assessment_result["id"],
            assessment_result_version_id=assessment_result_version["id"],
            revision_id=revision.id,
        )

        session.execute(
            insert(DemoSeedRunRecord)
            .values(tenant_id=tenant_id, seed_name=SEED_NAME)
            .on_conflict_do_nothing(index_elements=["tenant_id", "seed_name"])
        )

        return AIGovernanceDemoSeedResult(
            applied=True,
            catalog_id=catalog.id,
            revision_id=revision.id,
            system_id=system["id"],
            ssp_version_id=ssp_version["id"],
            assessment_plan_version_id=assessment_plan_version["id"],
            assessment_result_version_id=assessment_result_version["id"],
        )


def _existing_catalog_revision(session: Session, tenant_id: UUID) -> CatalogRevisionRecord | None:
    return session.scalar(
        select(CatalogRevisionRecord)
        .where(
            CatalogRevisionRecord.tenant_id == tenant_id,
            CatalogRevisionRecord.oscal_document_uuid == UPSTREAM_CATALOG_UUID,
        )
        .order_by(CatalogRevisionRecord.revision_number.desc(), CatalogRevisionRecord.id)
    )


def _ensure_upstream_catalog(
    session: Session,
    *,
    tenant_id: UUID,
    catalog_path: Path,
    unit_of_work_factory: Callable[[], SQLAlchemyUnitOfWork],
) -> tuple[CatalogRecord, CatalogRevisionRecord]:
    existing = _existing_catalog_revision(session, tenant_id)
    if existing is not None:
        catalog = session.get(CatalogRecord, existing.catalog_id)
        if catalog is None:
            raise RuntimeError("Catalog revision exists without catalog row.")
        return catalog, existing

    content = catalog_path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != UPSTREAM_CATALOG_SHA256:
        raise ValueError("Upstream AI RMF catalog checksum mismatch.")
    document = json.loads(content)
    if UUID(document["catalog"]["uuid"]) != UPSTREAM_CATALOG_UUID:
        raise ValueError("Upstream AI RMF catalog UUID mismatch.")
    if document["catalog"]["metadata"]["oscal-version"] != UPSTREAM_CATALOG_OSCAL_VERSION:
        raise ValueError("Upstream AI RMF catalog OSCAL version mismatch.")

    importer = CatalogImportService(unit_of_work_factory)
    result = importer.import_catalog(
        tenant_id,
        content,
        metadata=CatalogImportMetadata(
            source_uri=UPSTREAM_CATALOG_SOURCE_URI,
            source_organization=UPSTREAM_CATALOG_SOURCE_ORGANIZATION,
            license_identifier=UPSTREAM_CATALOG_LICENSE,
            catalog_name="NIST AI Risk Management Framework Generattive AI Profile",
        ),
    )
    catalog = session.get(CatalogRecord, result.catalog.id)
    revision = session.get(CatalogRevisionRecord, result.revision.id)
    if catalog is None or revision is None:
        raise RuntimeError("Catalog import completed without persisted records.")
    return catalog, revision


def _validate_seed_context(session: Session, tenant_id: UUID, actor_id: UUID) -> None:
    if session.get(TenantRecord, tenant_id) is None:
        raise ValueError("Tenant does not exist.")
    membership = session.scalar(
        select(TenantMembershipRecord.id).where(
            TenantMembershipRecord.tenant_id == tenant_id,
            TenantMembershipRecord.user_id == actor_id,
            TenantMembershipRecord.status == "active",
        )
    )
    if membership is None:
        raise ValueError("Actor must have active tenant membership.")


def _validate_prioritized_controls(session: Session, tenant_id: UUID, revision_id: UUID) -> None:
    available = set(
        session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id).where(
                CatalogControlIndexRecord.tenant_id == tenant_id,
                CatalogControlIndexRecord.catalog_revision_id == revision_id,
                CatalogControlIndexRecord.oscal_control_id.in_(PRIORITIZED_CONTROL_IDS),
            )
        )
    )
    missing = sorted(set(PRIORITIZED_CONTROL_IDS) - available)
    if missing:
        raise ValueError("Required controls missing from upstream catalog: " + ", ".join(missing))


def _statement_ids_by_control(content: dict) -> dict[str, list[str]]:
    by_control: dict[str, list[str]] = {}

    def walk_controls(controls: list[dict]) -> None:
        for control in controls:
            control_id = control.get("id")
            if isinstance(control_id, str):
                by_control[control_id] = [
                    part["id"]
                    for part in control.get("parts", [])
                    if part.get("name") == "statement" and isinstance(part.get("id"), str)
                ]
            walk_controls(control.get("controls", []))

    def walk_groups(groups: list[dict]) -> None:
        for group in groups:
            walk_controls(group.get("controls", []))
            walk_groups(group.get("groups", []))

    catalog = content.get("catalog", {})
    walk_controls(catalog.get("controls", []))
    walk_groups(catalog.get("groups", []))
    return by_control


def _select_statement_target(statement_ids: dict[str, list[str]]) -> str:
    primary = statement_ids.get("MG-3.1-009", [])
    if primary:
        return primary[0]
    for control_id in PRIORITIZED_CONTROL_IDS:
        matches = statement_ids.get(control_id, [])
        if matches:
            return matches[0]
    raise ValueError("No statement IDs found for prioritized controls.")


def _validate_historical_chain(
    ssp: SystemSecurityPlanService,
    assessment_plans: AssessmentPlanService,
    assessment_results: AssessmentResultService,
    *,
    tenant_id: UUID,
    ssp_plan_id: UUID,
    ssp_version_id: UUID,
    assessment_plan_id: UUID,
    assessment_plan_version_id: UUID,
    assessment_result_id: UUID,
    assessment_result_version_id: UUID,
    revision_id: UUID,
) -> None:
    ssp_doc = ssp.export_version(tenant_id, ssp_plan_id, ssp_version_id)
    ap_doc = assessment_plans.export_version(
        tenant_id,
        assessment_plan_id,
        assessment_plan_version_id,
    )
    ar_doc = assessment_results.export_version(
        tenant_id,
        assessment_result_id,
        assessment_result_version_id,
    )

    profile_href = ssp_doc["system-security-plan"]["import-profile"]["href"]
    ssp_href = ap_doc["assessment-plan"]["import-ssp"]["href"]
    ap_href = ar_doc["assessment-results"]["import-ap"]["href"]
    if not profile_href.endswith(f"/{revision_id}/export"):
        raise RuntimeError("SSP import-profile reference does not match pinned revision.")
    if not ssp_href.endswith(f"/{ssp_version_id}/export"):
        raise RuntimeError("Assessment Plan import-ssp reference does not match SSP version.")
    if not ap_href.endswith(f"/{assessment_plan_version_id}/export"):
        raise RuntimeError("Assessment Results import-ap reference does not match AP version.")





