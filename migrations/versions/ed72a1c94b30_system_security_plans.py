"""Add tenant-scoped information systems and immutable SSP versions.

Revision ID: ed72a1c94b30
Revises: ab41d08f2e93
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ed72a1c94b30"
down_revision: str | Sequence[str] | None = ("ab41d08f2e93", "4d7e8f901abc")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "information_systems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid()),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("system_boundary", sa.Text()),
        sa.Column("system_ids", postgresql.JSONB(), nullable=False),
        sa.Column("information_types", postgresql.JSONB(), nullable=False),
        sa.Column("operational_status", sa.String(32)),
        sa.Column("status_remarks", sa.Text()),
        sa.Column("security_sensitivity_level", sa.String(255)),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_information_systems_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_information_systems_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "organization_id"],
            ["organizations.tenant_id", "organizations.id"],
            name="fk_information_systems_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["user_identities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["user_identities.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "operational_status IS NULL OR operational_status IN "
            "('operational', 'under-development', 'under-major-modification', 'disposition', 'other')",
            name="ck_information_systems_status",
        ),
        sa.CheckConstraint(
            "operational_status != 'other' OR coalesce(length(trim(status_remarks)), 0) > 0",
            name="ck_information_systems_other_status_remarks",
        ),
    )
    op.create_index(
        "ix_information_systems_tenant_updated",
        "information_systems",
        ["tenant_id", "updated_at"],
    )

    op.create_table(
        "component_definition_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_uuid", sa.Uuid(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("diagnostics", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_component_definition_snapshots_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "content_sha256",
            name="uq_component_definition_snapshots_digest",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_component_definition_snapshots_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_component_definition_snapshots_sha256_format",
        ),
    )
    op.create_index(
        "ix_component_definition_snapshots_created",
        "component_definition_snapshots",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "system_components",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("oscal_component_uuid", sa.Uuid(), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid()),
        sa.Column("source_component_uuid", sa.Uuid()),
        sa.Column("is_system_component", sa.Boolean(), nullable=False),
        sa.Column("component", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "system_id", "id", name="uq_system_components_identity"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "system_id",
            "oscal_component_uuid",
            name="uq_system_components_oscal_uuid",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["information_systems.tenant_id", "information_systems.id"],
            name="fk_system_components_system",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_snapshot_id"],
            [
                "component_definition_snapshots.tenant_id",
                "component_definition_snapshots.id",
            ],
            name="fk_system_components_source_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["user_identities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["user_identities.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "(source_snapshot_id IS NULL AND source_component_uuid IS NULL) OR "
            "(source_snapshot_id IS NOT NULL AND source_component_uuid IS NOT NULL)",
            name="ck_system_components_source_identity",
        ),
    )
    op.create_index(
        "ix_system_components_system_created",
        "system_components",
        ["tenant_id", "system_id", "created_at"],
    )
    op.create_index(
        "uq_system_components_this_system",
        "system_components",
        ["tenant_id", "system_id"],
        unique=True,
        postgresql_where=sa.text("is_system_component"),
    )

    op.create_table(
        "system_security_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("control_implementation_description", sa.Text()),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_system_security_plans_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "system_id",
            "catalog_id",
            "revision_id",
            name="uq_system_security_plans_context",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["information_systems.tenant_id", "information_systems.id"],
            name="fk_system_security_plans_system",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            [
                "catalog_revisions.tenant_id",
                "catalog_revisions.catalog_id",
                "catalog_revisions.id",
            ],
            name="fk_system_security_plans_baseline",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["user_identities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["user_identities.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_system_security_plans_system_updated",
        "system_security_plans",
        ["tenant_id", "system_id", "updated_at"],
    )

    op.create_table(
        "system_security_plan_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("system_security_plan_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("oscal_document_uuid", sa.Uuid(), nullable=False),
        sa.Column("oscal_version", sa.String(32), nullable=False),
        sa.Column("document_version", sa.String(64), nullable=False),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("diagnostics", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_system_security_plan_versions_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "system_security_plan_id",
            name="uq_system_security_plan_versions_identity",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "system_security_plan_id",
            "content_sha256",
            name="uq_system_security_plan_versions_digest",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_security_plan_id"],
            ["system_security_plans.tenant_id", "system_security_plans.id"],
            name="fk_system_security_plan_versions_plan",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            [
                "catalog_revisions.tenant_id",
                "catalog_revisions.catalog_id",
                "catalog_revisions.id",
            ],
            name="fk_system_security_plan_versions_baseline",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_system_security_plan_versions_sha256_format",
        ),
    )
    op.create_index(
        "ix_system_security_plan_versions_plan_created",
        "system_security_plan_versions",
        ["tenant_id", "system_security_plan_id", "created_at"],
    )

    op.add_column(
        "control_implementations",
        sa.Column("system_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "control_implementations",
        sa.Column("system_component_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "control_implementations",
        sa.Column("oscal_implementation_status", sa.String(32), nullable=True),
    )
    op.add_column(
        "control_implementations",
        sa.Column("oscal_status_explanation", sa.Text(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_implementations_ssp_association",
        "control_implementations",
        [
            "tenant_id",
            "id",
            "system_id",
            "system_component_id",
            "catalog_id",
            "revision_id",
            "oscal_control_id",
        ],
    )
    op.create_foreign_key(
        "fk_implementations_system",
        "control_implementations",
        "information_systems",
        ["tenant_id", "system_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_implementations_system_component",
        "control_implementations",
        "system_components",
        ["tenant_id", "system_id", "system_component_id"],
        ["tenant_id", "system_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_implementation_component_requires_system",
        "control_implementations",
        "system_component_id IS NULL OR system_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_implementation_oscal_status",
        "control_implementations",
        "oscal_implementation_status IS NULL OR oscal_implementation_status IN "
        "('implemented', 'partial', 'planned', 'alternative', 'not-applicable')",
    )
    op.create_check_constraint(
        "ck_implementation_oscal_status_explanation",
        "control_implementations",
        "oscal_implementation_status NOT IN ('planned', 'alternative', 'not-applicable') "
        "OR coalesce(length(trim(oscal_status_explanation)), 0) > 0",
    )
    op.create_check_constraint(
        "ck_implementation_oscal_explanation_requires_status",
        "control_implementations",
        "oscal_implementation_status IS NOT NULL OR oscal_status_explanation IS NULL",
    )
    op.create_index(
        "ix_implementations_tenant_system",
        "control_implementations",
        ["tenant_id", "system_id"],
    )

    op.create_table(
        "system_security_plan_implementations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("system_security_plan_id", sa.Uuid(), nullable=False),
        sa.Column("implementation_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("system_component_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("oscal_control_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "system_security_plan_id",
            "implementation_id",
            name="uq_system_security_plan_implementation",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "system_security_plan_id",
            "oscal_control_id",
            "system_component_id",
            name="uq_system_security_plan_component_contribution",
        ),
        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "system_security_plan_id",
                "system_id",
                "catalog_id",
                "revision_id",
            ],
            [
                "system_security_plans.tenant_id",
                "system_security_plans.id",
                "system_security_plans.system_id",
                "system_security_plans.catalog_id",
                "system_security_plans.revision_id",
            ],
            name="fk_system_security_plan_implementations_plan_context",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "implementation_id",
                "system_id",
                "system_component_id",
                "catalog_id",
                "revision_id",
                "oscal_control_id",
            ],
            [
                "control_implementations.tenant_id",
                "control_implementations.id",
                "control_implementations.system_id",
                "control_implementations.system_component_id",
                "control_implementations.catalog_id",
                "control_implementations.revision_id",
                "control_implementations.oscal_control_id",
            ],
            name="fk_system_security_plan_implementations_record",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_id", "system_component_id"],
            [
                "system_components.tenant_id",
                "system_components.system_id",
                "system_components.id",
            ],
            name="fk_system_security_plan_implementations_component",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "revision_id", "oscal_control_id"],
            [
                "catalog_control_indexes.tenant_id",
                "catalog_control_indexes.catalog_revision_id",
                "catalog_control_indexes.oscal_control_id",
            ],
            name="fk_system_security_plan_implementations_control",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_system_security_plan_implementations_plan",
        "system_security_plan_implementations",
        ["tenant_id", "system_security_plan_id"],
    )

    op.execute("""
        CREATE FUNCTION lock_system_security_plan_revision() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' OR TG_OP = 'UPDATE' THEN
                PERFORM 1 FROM catalog_revisions
                WHERE tenant_id = OLD.tenant_id AND catalog_id = OLD.catalog_id
                  AND id = OLD.revision_id FOR UPDATE;
            END IF;
            IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
                PERFORM 1 FROM catalog_revisions
                WHERE tenant_id = NEW.tenant_id AND catalog_id = NEW.catalog_id
                  AND id = NEW.revision_id FOR UPDATE;
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_system_security_plan_revision_lock
        BEFORE INSERT OR UPDATE OR DELETE ON system_security_plans
        FOR EACH ROW EXECUTE FUNCTION lock_system_security_plan_revision()
    """)
    op.execute("""
        CREATE FUNCTION protect_ssp_catalog_revision() RETURNS trigger AS $$
        BEGIN
            IF (NEW.content, NEW.content_sha256, NEW.oscal_document_uuid, NEW.oscal_version,
                NEW.catalog_id, NEW.tenant_id, NEW.id, NEW.revision_number)
               IS DISTINCT FROM
               (OLD.content, OLD.content_sha256, OLD.oscal_document_uuid, OLD.oscal_version,
                OLD.catalog_id, OLD.tenant_id, OLD.id, OLD.revision_number)
               AND EXISTS (
                   SELECT 1 FROM system_security_plans
                   WHERE tenant_id = OLD.tenant_id AND revision_id = OLD.id
               ) THEN
                RAISE EXCEPTION
                    'Catalog revisions referenced by System Security Plans are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_ssp_catalog_revision_immutable
        BEFORE UPDATE ON catalog_revisions
        FOR EACH ROW EXECUTE FUNCTION protect_ssp_catalog_revision()
    """)
    op.execute("""
        CREATE FUNCTION protect_ssp_immutable_records() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% records are immutable', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_component_definition_snapshot_immutable
        BEFORE UPDATE OR DELETE ON component_definition_snapshots
        FOR EACH ROW EXECUTE FUNCTION protect_ssp_immutable_records()
    """)
    op.execute("""
        CREATE TRIGGER trg_system_security_plan_version_immutable
        BEFORE UPDATE OR DELETE ON system_security_plan_versions
        FOR EACH ROW EXECUTE FUNCTION protect_ssp_immutable_records()
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER trg_system_security_plan_version_immutable "
        "ON system_security_plan_versions"
    )
    op.execute(
        "DROP TRIGGER trg_component_definition_snapshot_immutable "
        "ON component_definition_snapshots"
    )
    op.execute("DROP FUNCTION protect_ssp_immutable_records()")
    op.execute("DROP TRIGGER trg_ssp_catalog_revision_immutable ON catalog_revisions")
    op.execute("DROP FUNCTION protect_ssp_catalog_revision()")
    op.execute(
        "DROP TRIGGER trg_system_security_plan_revision_lock ON system_security_plans"
    )
    op.execute("DROP FUNCTION lock_system_security_plan_revision()")
    op.drop_index(
        "ix_system_security_plan_implementations_plan",
        table_name="system_security_plan_implementations",
    )
    op.drop_table("system_security_plan_implementations")
    op.drop_index(
        "ix_implementations_tenant_system", table_name="control_implementations"
    )
    op.drop_constraint(
        "ck_implementation_oscal_status_explanation",
        "control_implementations",
        type_="check",
    )
    op.drop_constraint(
        "ck_implementation_oscal_explanation_requires_status",
        "control_implementations",
        type_="check",
    )
    op.drop_constraint(
        "ck_implementation_oscal_status", "control_implementations", type_="check"
    )
    op.drop_constraint(
        "ck_implementation_component_requires_system",
        "control_implementations",
        type_="check",
    )
    op.drop_constraint(
        "fk_implementations_system_component",
        "control_implementations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_implementations_system", "control_implementations", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_implementations_ssp_association", "control_implementations", type_="unique"
    )
    op.drop_column("control_implementations", "oscal_status_explanation")
    op.drop_column("control_implementations", "oscal_implementation_status")
    op.drop_column("control_implementations", "system_component_id")
    op.drop_column("control_implementations", "system_id")
    op.drop_index(
        "ix_system_security_plan_versions_plan_created",
        table_name="system_security_plan_versions",
    )
    op.drop_table("system_security_plan_versions")
    op.drop_index(
        "ix_system_security_plans_system_updated", table_name="system_security_plans"
    )
    op.drop_table("system_security_plans")
    op.drop_index("uq_system_components_this_system", table_name="system_components")
    op.drop_index("ix_system_components_system_created", table_name="system_components")
    op.drop_table("system_components")
    op.drop_index(
        "ix_component_definition_snapshots_created",
        table_name="component_definition_snapshots",
    )
    op.drop_table("component_definition_snapshots")
    op.drop_index(
        "ix_information_systems_tenant_updated", table_name="information_systems"
    )
    op.drop_table("information_systems")
