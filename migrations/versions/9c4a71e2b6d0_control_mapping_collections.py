"""Add OSCAL Control Mapping collections and revision-pinned members.

Revision ID: 9c4a71e2b6d0
Revises: 71bc92de4a10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9c4a71e2b6d0"
down_revision: str | Sequence[str] | None = "71bc92de4a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mapping_collections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_mapping_collections_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["user_identities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["user_identities.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mapping_collections_tenant_id"),
    )
    op.create_index(
        "ix_mapping_collections_tenant_updated",
        "mapping_collections",
        ["tenant_id", "updated_at"],
    )
    op.create_table(
        "mapping_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_uuid", sa.Uuid(), nullable=False),
        sa.Column("entry_uuid", sa.Uuid(), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("member_type", sa.String(length=16), nullable=False),
        sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("oscal_member_id", sa.String(length=255), nullable=False),
        sa.Column("control_id", sa.String(length=255)),
        sa.CheckConstraint(
            "side IN ('source', 'target')", name="ck_mapping_members_side"
        ),
        sa.CheckConstraint(
            "(member_type = 'control' AND control_id = oscal_member_id) OR "
            "(member_type = 'statement' AND control_id IS NULL)",
            name="ck_mapping_members_member_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "collection_id"],
            ["mapping_collections.tenant_id", "mapping_collections.id"],
            name="fk_mapping_members_collection",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            [
                "catalog_revisions.tenant_id",
                "catalog_revisions.catalog_id",
                "catalog_revisions.id",
            ],
            name="fk_mapping_members_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "revision_id", "control_id"],
            [
                "catalog_control_indexes.tenant_id",
                "catalog_control_indexes.catalog_revision_id",
                "catalog_control_indexes.oscal_control_id",
            ],
            name="fk_mapping_members_control",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mapping_members_related_control",
        "mapping_members",
        ["tenant_id", "revision_id", "member_type", "oscal_member_id"],
    )
    op.create_index(
        "ix_mapping_members_entry",
        "mapping_members",
        ["tenant_id", "collection_id", "mapping_uuid", "entry_uuid"],
    )
    op.execute("""
        CREATE FUNCTION lock_mapping_member_revision() RETURNS trigger AS $$
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
        CREATE TRIGGER trg_mapping_member_revision_lock
        BEFORE INSERT OR UPDATE OR DELETE ON mapping_members
        FOR EACH ROW EXECUTE FUNCTION lock_mapping_member_revision()
    """)
    op.execute("""
        CREATE FUNCTION protect_mapping_source_revision() RETURNS trigger AS $$
        BEGIN
            IF (NEW.content, NEW.content_sha256, NEW.oscal_document_uuid, NEW.oscal_version,
                NEW.catalog_id, NEW.tenant_id, NEW.id, NEW.revision_number)
               IS DISTINCT FROM
               (OLD.content, OLD.content_sha256, OLD.oscal_document_uuid, OLD.oscal_version,
                OLD.catalog_id, OLD.tenant_id, OLD.id, OLD.revision_number)
               AND EXISTS (
                   SELECT 1 FROM mapping_members
                   WHERE tenant_id = OLD.tenant_id AND revision_id = OLD.id
               ) THEN
                RAISE EXCEPTION 'Catalog revisions referenced by control mappings are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_mapping_source_immutable
        BEFORE UPDATE ON catalog_revisions
        FOR EACH ROW EXECUTE FUNCTION protect_mapping_source_revision()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_mapping_source_immutable ON catalog_revisions")
    op.execute("DROP FUNCTION protect_mapping_source_revision()")
    op.execute("DROP TRIGGER trg_mapping_member_revision_lock ON mapping_members")
    op.execute("DROP FUNCTION lock_mapping_member_revision()")
    op.drop_index("ix_mapping_members_entry", table_name="mapping_members")
    op.drop_index("ix_mapping_members_related_control", table_name="mapping_members")
    op.drop_table("mapping_members")
    op.drop_index(
        "ix_mapping_collections_tenant_updated", table_name="mapping_collections"
    )
    op.drop_table("mapping_collections")
