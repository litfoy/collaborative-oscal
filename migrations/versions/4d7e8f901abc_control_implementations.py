"""Add revision-pinned control implementations.

Revision ID: 4d7e8f901abc
Revises: 1a2b3c4d5e6f
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4d7e8f901abc"
down_revision: str | Sequence[str] | None = "1a2b3c4d5e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "control_implementations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid()),
        sa.Column("profile_id", sa.Uuid()),
        sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("oscal_control_id", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("evidence_references", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_implementations_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            [
                "catalog_revisions.tenant_id",
                "catalog_revisions.catalog_id",
                "catalog_revisions.id",
            ],
            name="fk_implementations_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "revision_id", "oscal_control_id"],
            [
                "catalog_control_indexes.tenant_id",
                "catalog_control_indexes.catalog_revision_id",
                "catalog_control_indexes.oscal_control_id",
            ],
            name="fk_implementations_control",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "organization_id"],
            ["organizations.tenant_id", "organizations.id"],
            name="fk_implementations_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "profile_id"],
            ["profiles.tenant_id", "profiles.id"],
            name="fk_implementations_profile",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["user_identities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["user_identities.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "status IN ('not_started', 'in_progress', 'implemented', 'not_applicable')",
            name="ck_implementations_status",
        ),
    )
    op.create_index(
        "ix_implementations_tenant_profile",
        "control_implementations",
        ["tenant_id", "profile_id"],
    )
    op.create_index(
        "ix_implementations_tenant_organization",
        "control_implementations",
        ["tenant_id", "organization_id"],
    )
    op.create_table(
        "implementation_responsibilities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("implementation_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("user_id", sa.Uuid()),
        sa.Column("role", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "implementation_id"],
            ["control_implementations.tenant_id", "control_implementations.id"],
            name="fk_responsibilities_implementation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_responsibilities_membership",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "kind IN ('accountable', 'responsible', 'participant')",
            name="ck_responsibilities_kind",
        ),
        sa.UniqueConstraint(
            "implementation_id",
            "kind",
            "user_id",
            "role",
            name="uq_implementation_responsibility",
        ),
    )
    op.execute("""
        CREATE FUNCTION protect_implementation_source_revision() RETURNS trigger AS $$
        BEGIN
            IF (NEW.content, NEW.content_sha256, NEW.oscal_document_uuid, NEW.oscal_version,
                NEW.catalog_id, NEW.tenant_id, NEW.id, NEW.revision_number)
               IS DISTINCT FROM
               (OLD.content, OLD.content_sha256, OLD.oscal_document_uuid, OLD.oscal_version,
                OLD.catalog_id, OLD.tenant_id, OLD.id, OLD.revision_number)
               AND EXISTS (
                   SELECT 1 FROM control_implementations
                   WHERE tenant_id = OLD.tenant_id AND revision_id = OLD.id
               ) THEN
                RAISE EXCEPTION 'Catalog revisions referenced by implementations are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_implementation_source_immutable
        BEFORE UPDATE ON catalog_revisions
        FOR EACH ROW EXECUTE FUNCTION protect_implementation_source_revision()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_implementation_source_immutable ON catalog_revisions")
    op.execute("DROP FUNCTION protect_implementation_source_revision()")
    op.drop_table("implementation_responsibilities")
    op.drop_index(
        "ix_implementations_tenant_organization", table_name="control_implementations"
    )
    op.drop_index(
        "ix_implementations_tenant_profile", table_name="control_implementations"
    )
    op.drop_table("control_implementations")
