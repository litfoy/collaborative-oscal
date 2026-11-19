from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

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
    "MG-2.2-006",
    "MP-1.1-008",
    "GV-1.2-003",
    "GV-4.1-003",
    "MS-2.7-016",
)

MODEL_VERSION_CONTROL_ID = "MG-2.2-006"
MODEL_VERSION_OBJECTIVE_ID = "local-model-version-traceability"

# Fixed fictional assessment timeline. The demo documents are recorded retrospectively
# when the seed runs, so these dates precede the publication timestamps of the generated
# documents and the observation is collected inside the assessed period.
MODEL_VERSION_TASK_START = "2026-11-10T09:00:00+00:00"
MODEL_VERSION_OBSERVATION_COLLECTED = "2026-11-10T10:30:00+00:00"
MODEL_VERSION_TASK_END = "2026-11-10T12:00:00+00:00"
GOVERNANCE_TASK_START = "2026-11-11T09:00:00+00:00"
GOVERNANCE_TASK_END = "2026-11-11T12:00:00+00:00"
RED_TEAM_TASK_START = "2026-11-12T09:00:00+00:00"
RED_TEAM_TASK_END = "2026-11-12T12:00:00+00:00"


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

        definitions = ComponentDefinitionService(begin_scope)
        implementations = ImplementationService(begin_scope)
        ssp = SystemSecurityPlanService(begin_scope)
        assessment_plans = AssessmentPlanService(begin_scope)
        assessment_results = AssessmentResultService(begin_scope)

        # Reusable safeguards. Each Component Definition describes a contribution to the
        # referenced requirements; none of them claims that a requirement is met.
        version_definition = definitions.create(
            tenant_id,
            actor_id,
            "Model and dataset version management (fictional demo)",
            "service",
            (
                "Fictional demonstration data only. Reusable safeguard: a registry that "
                "versions models and evaluation datasets and links approved versions to "
                "release records. Not an actual compliance claim."
            ),
            [
                ComponentRequirementInput(
                    catalog.id,
                    revision.id,
                    "MG-2.2-006",
                    (
                        "Fictional demo safeguard: register every model and evaluation "
                        "dataset version under a unique identifier, record the changes "
                        "between versions, and reference the exact approved model version "
                        "in each release record so that a release can be traced and rolled "
                        "back. Contributes to this requirement; adopting the safeguard does "
                        "not by itself establish that the requirement is met."
                    ),
                ),
            ],
        )
        oversight_definition = definitions.create(
            tenant_id,
            actor_id,
            "Human oversight of agent actions (fictional demo)",
            "process-procedure",
            (
                "Fictional demonstration data only. Reusable safeguard: documented ownership "
                "and human approval responsibilities for security-sensitive agent actions "
                "and production releases. Not an actual compliance claim."
            ),
            [
                ComponentRequirementInput(
                    catalog.id,
                    revision.id,
                    "MP-1.1-008",
                    (
                        "Fictional demo safeguard: document the system requirements, the "
                        "system owner, and the AI actor roles and responsibilities for human "
                        "approval of security-sensitive agent actions and production "
                        "releases. Contributes documentation only; it does not show that "
                        "oversight is effective."
                    ),
                ),
            ],
        )
        policy_definition = definitions.create(
            tenant_id,
            actor_id,
            "AI governance policies (fictional demo)",
            "policy",
            (
                "Fictional demonstration data only. Reusable safeguard: an acceptable use "
                "policy and a risk measurement procedure for generative AI systems. Not an "
                "actual compliance claim."
            ),
            [
                ComponentRequirementInput(
                    catalog.id,
                    revision.id,
                    "GV-1.2-003",
                    (
                        "Fictional demo safeguard: define an acceptable use policy stating "
                        "permitted and prohibited uses of generative AI systems. Partial "
                        "contribution: the policy covers only the systems it names, not "
                        "every GAI system deployed or used within an organization."
                    ),
                ),
                ComponentRequirementInput(
                    catalog.id,
                    revision.id,
                    "GV-4.1-003",
                    (
                        "Fictional demo safeguard: maintain a documented risk measurement "
                        "procedure that defines standardized measurement protocols in the "
                        "context of use and structured feedback exercises such as AI "
                        "red-teaming. Partial contribution: independent external audits and "
                        "public feedback exercises are not part of this safeguard."
                    ),
                ),
            ],
        )
        red_team_definition = definitions.create(
            tenant_id,
            actor_id,
            "AI security testing (fictional demo)",
            "service",
            (
                "Fictional demonstration data only. Reusable safeguard: AI red-teaming of "
                "generative AI agents. Not an actual compliance claim."
            ),
            [
                ComponentRequirementInput(
                    catalog.id,
                    revision.id,
                    "MS-2.7-016",
                    (
                        "Fictional demo safeguard: perform AI red-teaming of coding agents "
                        "against prompt injection and malicious code generation. Partial "
                        "contribution: adversarial examples, data poisoning and model "
                        "extraction, which the requirement also names, are not covered."
                    ),
                ),
            ],
        )

        system = ssp.create_system(
            tenant_id,
            actor_id,
            name=SYSTEM_NAME,
            organization_id=None,
            description=(
                "Fictional demonstration data only. Internal AI-assisted software "
                "development platform of a fictional organization. Coding agents use "
                "approved development tools to generate code and execute tests in isolated "
                "workspaces. Security-sensitive agent actions and production releases "
                "require documented human approval."
            ),
            system_boundary=(
                "Fictional demonstration data only. Includes the agent orchestration "
                "platform with its tool-execution workspaces, the model registry and "
                "release records, the human approval workflow, the AI governance policy "
                "set, and the AI red-teaming service. Excludes developer workstations and "
                "the production environments that run released software."
            ),
            system_ids=[
                {
                    "id": "agentic-ai-platform.demo.internal",
                    "identifier_type": "https://example.demo/system-id",
                }
            ],
            information_types=[
                {
                    "title": "Model registry and release records",
                    "description": (
                        "Fictional demo records of approved model and evaluation dataset "
                        "versions and of the releases that reference them."
                    ),
                },
                {
                    "title": "Agent activity and approval records",
                    "description": (
                        "Fictional demo logs of agent tool use, test executions and human "
                        "approval decisions."
                    ),
                },
                {
                    "title": "AI security test results",
                    "description": "Fictional demo plans and reports of AI red-teaming exercises.",
                },
            ],
            operational_status="operational",
            status_remarks=None,
            security_sensitivity_level="moderate",
        )
        ssp.create_component(
            tenant_id,
            actor_id,
            system["id"],
            component_type="this-system",
            title="Agent orchestration platform",
            description=(
                "Fictional demonstration data only. Runs coding agents that use approved "
                "development tools to generate code and execute tests in isolated "
                "workspaces, and routes security-sensitive actions and production releases "
                "to the human approval workflow."
            ),
            purpose="Provide AI-assisted software development with human-approved releases.",
            status="operational",
            status_remarks=None,
            is_system_component=True,
        )
        registry_component = ssp.adopt_component_definition(
            tenant_id,
            actor_id,
            system["id"],
            version_definition.id,
            version_definition.components[0].id,
            title="Model registry and release records",
            description=(
                "Fictional demonstration data only. Registry of the approved model and "
                "evaluation dataset versions used by the coding agents, together with the "
                "release records that reference them."
            ),
            purpose="Trace each release to an exact approved model version and support rollback.",
            status="operational",
            status_remarks=None,
        )
        approval_component = ssp.adopt_component_definition(
            tenant_id,
            actor_id,
            system["id"],
            oversight_definition.id,
            oversight_definition.components[0].id,
            title="Human approval workflow",
            description=(
                "Fictional demonstration data only. Documented workflow in which named "
                "approvers decide on security-sensitive agent actions and production "
                "releases before they take effect."
            ),
            purpose="Keep accountable human decisions in front of sensitive agent actions.",
            status="operational",
            status_remarks=None,
        )
        policy_component = ssp.adopt_component_definition(
            tenant_id,
            actor_id,
            system["id"],
            policy_definition.id,
            policy_definition.components[0].id,
            title="AI governance policy set",
            description=(
                "Fictional demonstration data only. The platform's acceptable use policy "
                "for coding agents and its risk measurement procedure."
            ),
            purpose="Define permitted agent use and how platform risks are measured.",
            status="operational",
            status_remarks=None,
        )
        red_team_component = ssp.adopt_component_definition(
            tenant_id,
            actor_id,
            system["id"],
            red_team_definition.id,
            red_team_definition.components[0].id,
            title="AI red-teaming service",
            description=(
                "Fictional demonstration data only. Internal service that runs adversarial "
                "exercises against the coding agents and reports the results."
            ),
            purpose="Assess agent resilience against malicious behavior.",
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
                "Fictional demonstration data only. Each contribution describes how one "
                "system component, adopted from a reusable safeguard, contributes to one "
                "selected requirement. A contribution is not a claim that the requirement "
                "is met."
            ),
        )
        # (control, contributing component, register status, OSCAL status, description,
        #  status explanation, fictional evidence references)
        contributions = (
            (
                "MG-2.2-006",
                registry_component["id"],
                ImplementationStatus.IN_PROGRESS,
                OscalImplementationStatus.PARTIAL,
                (
                    "Fictional demo: the model registry assigns a unique identifier to every "
                    "approved model version and evaluation dataset version used by the "
                    "coding agents and records the changes between versions. Release "
                    "records are expected to cite the exact approved model version so that "
                    "a release can be traced to its registry record and rolled back."
                ),
                (
                    "Fictional demo: version registration is in place; mandatory "
                    "model-version references in release records are still being introduced."
                ),
                [
                    "https://example.demo/fictional/model-registry/approved-versions",
                    "https://example.demo/fictional/release-records",
                ],
            ),
            (
                "MP-1.1-008",
                approval_component["id"],
                ImplementationStatus.IMPLEMENTED,
                OscalImplementationStatus.IMPLEMENTED,
                (
                    "Fictional demo: the platform's system requirements document names the "
                    "platform owner and the approver roles responsible for "
                    "security-sensitive agent actions, such as dependency changes and "
                    "credential use, and for production releases."
                ),
                (
                    "Fictional demo: the documentation is described as complete for this "
                    "system; whether human oversight operates effectively has not been "
                    "assessed."
                ),
                ["https://example.demo/fictional/platform-requirements-and-oversight-roles"],
            ),
            (
                "GV-1.2-003",
                policy_component["id"],
                ImplementationStatus.IN_PROGRESS,
                OscalImplementationStatus.PARTIAL,
                (
                    "Fictional demo: the acceptable use policy permits coding agents to "
                    "generate code and execute tests in isolated workspaces and prohibits "
                    "unapproved production changes and handling of production credentials."
                ),
                (
                    "Fictional demo: the policy covers this platform only; other GAI "
                    "systems used within the fictional organization are not yet covered."
                ),
                ["https://example.demo/fictional/acceptable-use-policy-coding-agents"],
            ),
            (
                "GV-4.1-003",
                policy_component["id"],
                ImplementationStatus.IN_PROGRESS,
                OscalImplementationStatus.PARTIAL,
                (
                    "Fictional demo: the risk measurement procedure defines standardized "
                    "measurement protocols for agent-generated changes, such as test "
                    "results and security review findings, and names developer feedback "
                    "sessions and AI red-teaming as structured feedback exercises."
                ),
                (
                    "Fictional demo: the procedure is in draft; structured feedback "
                    "exercises are defined but not yet scheduled, and independent external "
                    "audits are not included."
                ),
                ["https://example.demo/fictional/risk-measurement-procedure-draft"],
            ),
            (
                "MS-2.7-016",
                red_team_component["id"],
                ImplementationStatus.IN_PROGRESS,
                OscalImplementationStatus.PARTIAL,
                (
                    "Fictional demo: the red-teaming service runs exercises against the "
                    "coding agents that cover prompt injection through repository content "
                    "and tool output, and generation of malicious code."
                ),
                (
                    "Fictional demo: adversarial examples, data poisoning and model "
                    "extraction are not yet part of the exercises."
                ),
                ["https://example.demo/fictional/red-team/exercise-reports"],
            ),
        )
        for (
            control_id,
            component_id,
            register_status,
            oscal_status,
            description,
            status_explanation,
            evidence_references,
        ) in contributions:
            record = implementations.create(
                tenant_id,
                actor_id,
                catalog.id,
                revision.id,
                control_id,
                None,
                None,
                ImplementationInformation(
                    description=description,
                    status=register_status,
                    evidence_references=evidence_references,
                    responsibilities=[],
                    oscal_implementation_status=oscal_status,
                    oscal_status_explanation=status_explanation,
                ),
            )
            included = ssp.associate_implementation(
                tenant_id,
                actor_id,
                ssp_plan["id"],
                record.id,
                component_id,
                expected_version=ssp_plan["concurrency_version"],
            )
            ssp_plan["concurrency_version"] = included["concurrency_version"]

        if not ssp.validate_plan(tenant_id, ssp_plan["id"])["valid"]:
            raise RuntimeError("Generated SSP draft did not pass validation.")
        ssp_version = ssp.create_version(
            tenant_id,
            actor_id,
            ssp_plan["id"],
            expected_version=ssp_plan["concurrency_version"],
        )

        assessment_plan = assessment_plans.create_plan(
            tenant_id,
            actor_id,
            system["id"],
            ssp_version_id=ssp_version["id"],
            title="Agentic AI Governance Assessment Plan (fictional demo)",
            description=(
                "Fictional demonstration data only. Plans the examination of five selected "
                "requirements for the fictional platform. Dates are fictional and the plan "
                "is recorded retrospectively when the demo is seeded."
            ),
        )
        registry_subject = str(registry_component["oscal_component_uuid"])
        approval_subject = str(approval_component["oscal_component_uuid"])
        policy_subject = str(policy_component["oscal_component_uuid"])
        red_team_subject = str(red_team_component["oscal_component_uuid"])
        model_version_activity_id = str(uuid4())
        governance_activity_id = str(uuid4())
        red_team_activity_id = str(uuid4())
        assessor_party_uuid = str(uuid4())
        assessment_plan = assessment_plans.update_plan(
            tenant_id,
            actor_id,
            assessment_plan["id"],
            expected_version=assessment_plan["concurrency_version"],
            title=assessment_plan["title"],
            description=assessment_plan["description"],
            working_data={
                "control_ids": list(PRIORITIZED_CONTROL_IDS),
                "source_objectives": [],
                "local_objectives": [
                    {
                        "objective_id": MODEL_VERSION_OBJECTIVE_ID,
                        "control_id": MODEL_VERSION_CONTROL_ID,
                        "description": (
                            "Fictional demo objective: for each of three fictional sampled "
                            "releases, the release record identifies the exact approved "
                            "model version and can be matched to the corresponding model "
                            "registry record."
                        ),
                        "methods": ["EXAMINE"],
                    },
                    {
                        "objective_id": "local-oversight-roles-documented",
                        "control_id": "MP-1.1-008",
                        "description": (
                            "Fictional demo objective: the system requirements document "
                            "names the platform owner and the roles responsible for "
                            "approving security-sensitive agent actions and production "
                            "releases."
                        ),
                        "methods": ["EXAMINE", "INTERVIEW"],
                    },
                    {
                        "objective_id": "local-acceptable-use-policy-defined",
                        "control_id": "GV-1.2-003",
                        "description": (
                            "Fictional demo objective: an approved acceptable use policy "
                            "states the permitted and prohibited uses of the platform's "
                            "coding agents."
                        ),
                        "methods": ["EXAMINE"],
                    },
                    {
                        "objective_id": "local-risk-measurement-procedure-documented",
                        "control_id": "GV-4.1-003",
                        "description": (
                            "Fictional demo objective: the risk measurement procedure "
                            "defines standardized measurement protocols and at least one "
                            "structured feedback exercise for the platform."
                        ),
                        "methods": ["EXAMINE"],
                    },
                    {
                        "objective_id": "local-red-team-coverage-recorded",
                        "control_id": "MS-2.7-016",
                        "description": (
                            "Fictional demo objective: the records of the most recent AI "
                            "red-teaming exercise show test cases for prompt injection and "
                            "for malicious code generation against the coding agents."
                        ),
                        "methods": ["EXAMINE"],
                    },
                ],
                "subject_uuids": [
                    registry_subject,
                    approval_subject,
                    policy_subject,
                    red_team_subject,
                ],
                "activities": [
                    {
                        "id": model_version_activity_id,
                        "title": "Examine sampled release records for model-version traceability",
                        "description": (
                            "Fictional demonstration data only. Examine three sampled "
                            "release records against the model registry."
                        ),
                        "methods": ["EXAMINE"],
                        "steps": [
                            {
                                "title": "Select the sample",
                                "description": (
                                    "Select three fictional release records from the "
                                    "release records of the platform."
                                ),
                            },
                            {
                                "title": "Examine the release records",
                                "description": (
                                    "Check whether each sampled release record identifies "
                                    "an exact approved model version."
                                ),
                            },
                            {
                                "title": "Match to the model registry",
                                "description": (
                                    "Match each model-version identifier to the "
                                    "corresponding record in the model registry export."
                                ),
                            },
                        ],
                        "control_ids": [MODEL_VERSION_CONTROL_ID],
                        "objective_ids": [MODEL_VERSION_OBJECTIVE_ID],
                        "planned_evidence": (
                            "Fictional model registry export and three fictional sampled "
                            "release records."
                        ),
                    },
                    {
                        "id": governance_activity_id,
                        "title": "Examine oversight and governance documentation",
                        "description": (
                            "Fictional demonstration data only. Examine the documented "
                            "oversight responsibilities, the acceptable use policy and the "
                            "risk measurement procedure, and interview the platform owner "
                            "about the oversight roles."
                        ),
                        "methods": ["EXAMINE", "INTERVIEW"],
                        "steps": [],
                        "control_ids": ["MP-1.1-008", "GV-1.2-003", "GV-4.1-003"],
                        "objective_ids": [
                            "local-oversight-roles-documented",
                            "local-acceptable-use-policy-defined",
                            "local-risk-measurement-procedure-documented",
                        ],
                        "planned_evidence": (
                            "Fictional system requirements document, acceptable use policy "
                            "and risk measurement procedure."
                        ),
                    },
                    {
                        "id": red_team_activity_id,
                        "title": "Examine AI red-teaming records",
                        "description": (
                            "Fictional demonstration data only. Examine the plan and report "
                            "of the most recent AI red-teaming exercise. The assessor "
                            "reviews records and does not perform the red-teaming."
                        ),
                        "methods": ["EXAMINE"],
                        "steps": [],
                        "control_ids": ["MS-2.7-016"],
                        "objective_ids": ["local-red-team-coverage-recorded"],
                        "planned_evidence": "Fictional AI red-teaming exercise plan and report.",
                    },
                ],
                "tasks": [
                    {
                        "title": "Assess model-version traceability of sampled releases",
                        "description": "Fictional demonstration data only.",
                        "activity_ids": [model_version_activity_id],
                        "subject_uuids": [registry_subject],
                        "role_ids": ["lead-assessor"],
                        "on_date": None,
                        "start": MODEL_VERSION_TASK_START,
                        "end": MODEL_VERSION_TASK_END,
                    },
                    {
                        "title": "Assess oversight and governance documentation",
                        "description": "Fictional demonstration data only.",
                        "activity_ids": [governance_activity_id],
                        "subject_uuids": [approval_subject, policy_subject],
                        "role_ids": ["lead-assessor"],
                        "on_date": None,
                        "start": GOVERNANCE_TASK_START,
                        "end": GOVERNANCE_TASK_END,
                    },
                    {
                        "title": "Assess AI red-teaming records",
                        "description": "Fictional demonstration data only.",
                        "activity_ids": [red_team_activity_id],
                        "subject_uuids": [red_team_subject],
                        "role_ids": ["lead-assessor"],
                        "on_date": None,
                        "start": RED_TEAM_TASK_START,
                        "end": RED_TEAM_TASK_END,
                    },
                ],
                "roles": [
                    {
                        "role_id": "lead-assessor",
                        "title": "Lead Assessor",
                        "description": "Fictional demonstration data only.",
                        "party_uuids": [assessor_party_uuid],
                    }
                ],
                "parties": [
                    {
                        "uuid": assessor_party_uuid,
                        "party_type": "person",
                        "name": "Jordan Demo Assessor",
                    }
                ],
                "terms": "Fictional demonstration data only. Not evidence of real compliance.",
            },
        )
        if not assessment_plans.validate_plan(tenant_id, assessment_plan["id"])["valid"]:
            raise RuntimeError("Generated Assessment Plan draft did not pass validation.")
        assessment_plan_version = assessment_plans.create_version(
            tenant_id,
            actor_id,
            assessment_plan["id"],
            expected_version=assessment_plan["concurrency_version"],
        )

        assessment_result = assessment_results.create_result(
            tenant_id,
            actor_id,
            system["id"],
            assessment_plan_id=assessment_plan["id"],
            assessment_plan_version_id=assessment_plan_version["id"],
            title="Agentic AI Governance Assessment Results (fictional demo)",
            description=(
                "Fictional demonstration data only. Illustrative result that evaluates only "
                f"the local objective {MODEL_VERSION_OBJECTIVE_ID} for control "
                f"{MODEL_VERSION_CONTROL_ID}. The other planned controls were not assessed "
                "in this result, and no conclusion about them is implied."
            ),
        )
        observation_id = str(uuid4())
        assessment_result = assessment_results.update_result(
            tenant_id,
            actor_id,
            assessment_result["id"],
            expected_version=assessment_result["concurrency_version"],
            title=assessment_result["title"],
            description=assessment_result["description"],
            working_data={
                "reviewed_control_ids": [MODEL_VERSION_CONTROL_ID],
                "start": MODEL_VERSION_TASK_START,
                "end": MODEL_VERSION_TASK_END,
                "observations": [
                    {
                        "id": observation_id,
                        "title": "Model-version identifiers in three sampled release records",
                        "description": (
                            "Fictional demonstration data only. Three fictional release "
                            "records (REL-2026-041, REL-2026-042 and REL-2026-043) were "
                            "examined against the fictional model registry export. "
                            "REL-2026-041 and REL-2026-042 each contained an exact approved "
                            "model-version identifier that matched the corresponding "
                            "registry record. REL-2026-043 lacked the exact model-version "
                            "identifier, so it could not be matched to a registry record."
                        ),
                        "methods": ["EXAMINE"],
                        "collected_at": MODEL_VERSION_OBSERVATION_COLLECTED,
                        "subject_uuids": [registry_subject],
                        "evidence": [
                            {
                                "title": "Fictional model registry export",
                                "description": (
                                    "Fictional demonstration reference only; not real or "
                                    "verified evidence. Export of the approved model "
                                    "versions used for matching."
                                ),
                                "href": (
                                    "https://example.demo/fictional/model-registry/"
                                    "export-2026-11-10"
                                ),
                            },
                            {
                                "title": "Fictional sampled release records",
                                "description": (
                                    "Fictional demonstration reference only; not real or "
                                    "verified evidence. Release records REL-2026-041, "
                                    "REL-2026-042 and REL-2026-043."
                                ),
                                "href": (
                                    "https://example.demo/fictional/release-records/"
                                    "sample-2026-11-10"
                                ),
                            },
                        ],
                    }
                ],
                "findings": [
                    {
                        "title": (
                            "Local objective not satisfied: model-version traceability of "
                            "sampled releases"
                        ),
                        "description": (
                            "Fictional demonstration finding. The local objective requires "
                            "each of the three sampled release records to identify the "
                            "exact approved model version and to be matchable to its model "
                            "registry record. The related observation shows that two "
                            "records met this and one, REL-2026-043, lacked the exact "
                            "identifier, so the objective is not satisfied. This finding "
                            "evaluates the local objective only; it does not conclude that "
                            f"control {MODEL_VERSION_CONTROL_ID} as a whole is satisfied or "
                            "not satisfied."
                        ),
                        "target_type": "objective-id",
                        "target_id": MODEL_VERSION_OBJECTIVE_ID,
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
            expected_version=assessment_result["concurrency_version"],
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
