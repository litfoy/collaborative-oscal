# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""Add tenant-scoped OSCAL Component Definitions.

Revision ID: ab41d08f2e93
Revises: 9c4a71e2b6d0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ab41d08f2e93"
down_revision: str | Sequence[str] | None = "9c4a71e2b6d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "component_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_component_definitions_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["user_identities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["user_identities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_component_definitions_tenant_id"),
    )
    op.create_index(
        "ix_component_definitions_tenant_updated",
        "component_definitions",
        ["tenant_id", "updated_at"],
    )
    op.create_table(
        "component_definition_components",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("oscal_component_uuid", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["component_definitions.tenant_id", "component_definitions.id"],
            name="fk_component_definition_component_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "document_id", "id",
            name="uq_component_definition_component_identity",
        ),
        sa.UniqueConstraint(
            "tenant_id", "document_id", "oscal_component_uuid",
            name="uq_component_definition_component_oscal_uuid",
        ),
    )
    op.create_index(
        "ix_component_definition_components_document",
        "component_definition_components",
        ["tenant_id", "document_id"],
    )
    op.create_table(
        "component_definition_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("component_id", sa.Uuid(), nullable=False),
        sa.Column("control_implementation_uuid", sa.Uuid(), nullable=False),
        sa.Column("implemented_requirement_uuid", sa.Uuid(), nullable=False),
        sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("oscal_control_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id", "component_id"],
            [
                "component_definition_components.tenant_id",
                "component_definition_components.document_id",
                "component_definition_components.id",
            ],
            name="fk_component_definition_source_component",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            [
                "catalog_revisions.tenant_id",
                "catalog_revisions.catalog_id",
                "catalog_revisions.id",
            ],
            name="fk_component_definition_source_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "revision_id", "oscal_control_id"],
            [
                "catalog_control_indexes.tenant_id",
                "catalog_control_indexes.catalog_revision_id",
                "catalog_control_indexes.oscal_control_id",
            ],
            name="fk_component_definition_source_control",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "component_id",
            "control_implementation_uuid",
            "implemented_requirement_uuid",
            name="uq_component_definition_source_requirement",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "component_id",
            "catalog_id",
            "revision_id",
            "oscal_control_id",
            name="uq_component_definition_source_control",
        ),
    )
    op.create_index(
        "ix_component_definition_sources_control",
        "component_definition_sources",
        ["tenant_id", "catalog_id", "revision_id", "oscal_control_id"],
    )
    op.execute("""
        CREATE FUNCTION lock_component_definition_source_revision() RETURNS trigger AS $$
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
        CREATE TRIGGER trg_component_definition_source_revision_lock
        BEFORE INSERT OR UPDATE OR DELETE ON component_definition_sources
        FOR EACH ROW EXECUTE FUNCTION lock_component_definition_source_revision()
    """)
    op.execute("""
        CREATE FUNCTION protect_component_definition_source_revision() RETURNS trigger AS $$
        BEGIN
            IF (NEW.content, NEW.content_sha256, NEW.oscal_document_uuid, NEW.oscal_version,
                NEW.catalog_id, NEW.tenant_id, NEW.id, NEW.revision_number)
               IS DISTINCT FROM
               (OLD.content, OLD.content_sha256, OLD.oscal_document_uuid, OLD.oscal_version,
                OLD.catalog_id, OLD.tenant_id, OLD.id, OLD.revision_number)
               AND EXISTS (
                   SELECT 1 FROM component_definition_sources
                   WHERE tenant_id = OLD.tenant_id AND revision_id = OLD.id
               ) THEN
                RAISE EXCEPTION
                    'Catalog revisions referenced by Component Definitions are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_component_definition_source_immutable
        BEFORE UPDATE ON catalog_revisions
        FOR EACH ROW EXECUTE FUNCTION protect_component_definition_source_revision()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_component_definition_source_immutable ON catalog_revisions")
    op.execute("DROP FUNCTION protect_component_definition_source_revision()")
    op.execute(
        "DROP TRIGGER trg_component_definition_source_revision_lock "
        "ON component_definition_sources"
    )
    op.execute("DROP FUNCTION lock_component_definition_source_revision()")
    op.drop_index(
        "ix_component_definition_sources_control",
        table_name="component_definition_sources",
    )
    op.drop_table("component_definition_sources")
    op.drop_index(
        "ix_component_definition_components_document",
        table_name="component_definition_components",
    )
    op.drop_table("component_definition_components")
    op.drop_index(
        "ix_component_definitions_tenant_updated",
        table_name="component_definitions",
    )
    op.drop_table("component_definitions")
