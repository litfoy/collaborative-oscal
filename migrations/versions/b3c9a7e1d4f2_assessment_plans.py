"""Add tenant-scoped Assessment Plans and immutable versions.

Revision ID: b3c9a7e1d4f2
Revises: ed72a1c94b30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3c9a7e1d4f2"
down_revision: str | Sequence[str] | None = "ed72a1c94b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assessment_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("system_security_plan_id", sa.Uuid(), nullable=False),
        sa.Column("system_security_plan_version_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("working_data", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_assessment_plans_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "system_id",
            "system_security_plan_id",
            "system_security_plan_version_id",
            name="uq_assessment_plans_context",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["information_systems.tenant_id", "information_systems.id"],
            name="fk_assessment_plans_system",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_security_plan_id"],
            ["system_security_plans.tenant_id", "system_security_plans.id"],
            name="fk_assessment_plans_ssp",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_security_plan_version_id"],
            ["system_security_plan_versions.tenant_id", "system_security_plan_versions.id"],
            name="fk_assessment_plans_ssp_version",
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
        "ix_assessment_plans_system_updated",
        "assessment_plans",
        ["tenant_id", "system_id", "updated_at"],
    )

    op.create_table(
        "assessment_plan_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_plan_id", sa.Uuid(), nullable=False),
        sa.Column("system_security_plan_version_id", sa.Uuid(), nullable=False),
        sa.Column("oscal_document_uuid", sa.Uuid(), nullable=False),
        sa.Column("oscal_version", sa.String(length=32), nullable=False),
        sa.Column("document_version", sa.String(length=64), nullable=False),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("diagnostics", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_assessment_plan_versions_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "assessment_plan_id",
            name="uq_assessment_plan_versions_identity",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "assessment_plan_id",
            "content_sha256",
            name="uq_assessment_plan_versions_digest",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assessment_plan_id"],
            ["assessment_plans.tenant_id", "assessment_plans.id"],
            name="fk_assessment_plan_versions_plan",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_security_plan_version_id"],
            ["system_security_plan_versions.tenant_id", "system_security_plan_versions.id"],
            name="fk_assessment_plan_versions_ssp_version",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_assessment_plan_versions_sha256_format",
        ),
    )
    op.create_index(
        "ix_assessment_plan_versions_plan_created",
        "assessment_plan_versions",
        ["tenant_id", "assessment_plan_id", "created_at"],
    )

    op.execute("""
        CREATE FUNCTION protect_assessment_plan_context() RETURNS trigger AS $$
        BEGIN
            IF (
                NEW.system_id,
                NEW.system_security_plan_id,
                NEW.system_security_plan_version_id
            ) IS DISTINCT FROM (
                OLD.system_id,
                OLD.system_security_plan_id,
                OLD.system_security_plan_version_id
            ) THEN
                RAISE EXCEPTION 'Pinned SSP references on Assessment Plans are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_assessment_plan_context_immutable
        BEFORE UPDATE ON assessment_plans
        FOR EACH ROW EXECUTE FUNCTION protect_assessment_plan_context()
    """)

    op.execute("""
        CREATE FUNCTION protect_assessment_plan_versions_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% records are immutable', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_assessment_plan_version_immutable
        BEFORE UPDATE OR DELETE ON assessment_plan_versions
        FOR EACH ROW EXECUTE FUNCTION protect_assessment_plan_versions_immutable()
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER trg_assessment_plan_version_immutable ON assessment_plan_versions"
    )
    op.execute("DROP FUNCTION protect_assessment_plan_versions_immutable()")
    op.execute(
        "DROP TRIGGER trg_assessment_plan_context_immutable ON assessment_plans"
    )
    op.execute("DROP FUNCTION protect_assessment_plan_context()")
    op.drop_index(
        "ix_assessment_plan_versions_plan_created", table_name="assessment_plan_versions"
    )
    op.drop_table("assessment_plan_versions")
    op.drop_index("ix_assessment_plans_system_updated", table_name="assessment_plans")
    op.drop_table("assessment_plans")


