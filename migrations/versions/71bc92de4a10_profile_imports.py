"""Preserve profile import identities and their implementation provenance.

Revision ID: 71bc92de4a10
Revises: 4d7e8f901abc
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "71bc92de4a10"
down_revision = "4d7e8f901abc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "profile_id", "id", name="uq_profile_import_identity"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "profile_id",
            "id",
            "catalog_id",
            "revision_id",
            name="uq_profile_import_source",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "profile_id"],
            ["profiles.tenant_id", "profiles.id"],
            name="fk_profile_import_profile",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            [
                "catalog_revisions.tenant_id",
                "catalog_revisions.catalog_id",
                "catalog_revisions.id",
            ],
            name="fk_profile_import_revision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("position >= 0", name="ck_profile_import_position"),
    )
    op.create_index(
        "ix_profile_imports_profile", "profile_imports", ["tenant_id", "profile_id"]
    )
    op.create_index(
        "ix_profile_imports_revision", "profile_imports", ["tenant_id", "revision_id"]
    )
    op.add_column("control_implementations", sa.Column("profile_import_id", sa.Uuid()))
    connection = op.get_bind()
    profiles = connection.execute(
        sa.text("SELECT id, tenant_id, catalog_id, revision_id, document FROM profiles")
    ).mappings()
    for profile in profiles:
        imports = profile["document"].get("profile", {}).get("imports", [])
        expected = (
            f"/api/v1/tenants/{profile['tenant_id']}/catalogs/{profile['catalog_id']}"
            f"/revisions/{profile['revision_id']}/export"
        )
        if len(imports) != 1 or imports[0].get("href") != expected:
            raise RuntimeError(
                f"Profile {profile['id']} has an unexpected source document"
            )
        import_id = uuid4()
        connection.execute(
            sa.text(
                "INSERT INTO profile_imports "
                "(id, tenant_id, profile_id, catalog_id, revision_id, position, active) "
                "VALUES (:id, :tenant, :profile, :catalog, :revision, 0, true)"
            ),
            {
                "id": import_id,
                "tenant": profile["tenant_id"],
                "profile": profile["id"],
                "catalog": profile["catalog_id"],
                "revision": profile["revision_id"],
            },
        )
        mismatch = connection.execute(
            sa.text(
                "SELECT id FROM control_implementations WHERE tenant_id=:tenant "
                "AND profile_id=:profile AND (catalog_id<>:catalog OR revision_id<>:revision) "
                "LIMIT 1"
            ),
            {
                "tenant": profile["tenant_id"],
                "profile": profile["id"],
                "catalog": profile["catalog_id"],
                "revision": profile["revision_id"],
            },
        ).first()
        if mismatch:
            raise RuntimeError(
                f"Implementation {mismatch[0]} has inconsistent profile provenance"
            )
        connection.execute(
            sa.text(
                "UPDATE control_implementations SET profile_import_id=:import_id "
                "WHERE tenant_id=:tenant AND profile_id=:profile"
            ),
            {
                "import_id": import_id,
                "tenant": profile["tenant_id"],
                "profile": profile["id"],
            },
        )
    op.create_foreign_key(
        "fk_implementations_profile_import",
        "control_implementations",
        "profile_imports",
        ["tenant_id", "profile_id", "profile_import_id", "catalog_id", "revision_id"],
        ["tenant_id", "profile_id", "id", "catalog_id", "revision_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_implementation_import_profile",
        "control_implementations",
        "profile_import_id IS NULL OR profile_id IS NOT NULL",
    )
    op.drop_constraint(
        "fk_profiles_source_revision_same_tenant", "profiles", type_="foreignkey"
    )
    op.drop_column("profiles", "catalog_id")
    op.drop_column("profiles", "revision_id")
    op.execute("""
        CREATE FUNCTION lock_profile_import_revision() RETURNS trigger AS $$
        BEGIN
            PERFORM 1 FROM catalog_revisions
            WHERE tenant_id = NEW.tenant_id AND catalog_id = NEW.catalog_id
              AND id = NEW.revision_id FOR UPDATE;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_profile_import_revision_lock BEFORE INSERT ON profile_imports
        FOR EACH ROW EXECUTE FUNCTION lock_profile_import_revision()
    """)
    op.execute("""
        CREATE FUNCTION lock_implementation_revision() RETURNS trigger AS $$
        BEGIN
            PERFORM 1 FROM catalog_revisions
            WHERE tenant_id = NEW.tenant_id AND catalog_id = NEW.catalog_id
              AND id = NEW.revision_id FOR UPDATE;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_implementation_revision_lock BEFORE INSERT ON control_implementations
        FOR EACH ROW EXECUTE FUNCTION lock_implementation_revision()
    """)
    op.execute("""
        CREATE FUNCTION protect_implementation_identity() RETURNS trigger AS $$
        BEGIN
            IF (NEW.id, NEW.tenant_id, NEW.profile_id, NEW.profile_import_id, NEW.catalog_id,
                NEW.revision_id, NEW.oscal_control_id)
               IS DISTINCT FROM
               (OLD.id, OLD.tenant_id, OLD.profile_id, OLD.profile_import_id, OLD.catalog_id,
                OLD.revision_id, OLD.oscal_control_id) THEN
                RAISE EXCEPTION 'Implementation provenance is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_implementation_identity BEFORE UPDATE ON control_implementations
        FOR EACH ROW EXECUTE FUNCTION protect_implementation_identity()
    """)
    op.execute("""
        CREATE FUNCTION protect_profile_import_revision() RETURNS trigger AS $$
        BEGIN
            IF (NEW.content, NEW.content_sha256, NEW.oscal_document_uuid, NEW.oscal_version,
                NEW.catalog_id, NEW.tenant_id, NEW.id, NEW.revision_number)
               IS DISTINCT FROM
               (OLD.content, OLD.content_sha256, OLD.oscal_document_uuid, OLD.oscal_version,
                OLD.catalog_id, OLD.tenant_id, OLD.id, OLD.revision_number)
               AND EXISTS (SELECT 1 FROM profile_imports
                           WHERE tenant_id = OLD.tenant_id AND revision_id = OLD.id) THEN
                RAISE EXCEPTION 'Catalog revisions referenced by profile imports are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_profile_import_source_immutable BEFORE UPDATE ON catalog_revisions
        FOR EACH ROW EXECUTE FUNCTION protect_profile_import_revision()
    """)
    op.execute("""
        CREATE FUNCTION protect_profile_import_identity() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Profile import history cannot be deleted';
            END IF;
            IF (NEW.id, NEW.tenant_id, NEW.profile_id, NEW.catalog_id, NEW.revision_id)
               IS DISTINCT FROM (OLD.id, OLD.tenant_id, OLD.profile_id, OLD.catalog_id, OLD.revision_id)
            THEN RAISE EXCEPTION 'Profile import identity and source are immutable'; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_profile_import_identity BEFORE UPDATE OR DELETE ON profile_imports
        FOR EACH ROW EXECUTE FUNCTION protect_profile_import_identity()
    """)


def downgrade() -> None:
    connection = op.get_bind()
    incompatible = connection.execute(
        sa.text("""
        SELECT p.id FROM profiles p LEFT JOIN profile_imports i ON i.profile_id=p.id
        GROUP BY p.id HAVING count(i.id) <> 1 OR NOT bool_and(i.active) LIMIT 1
    """)
    ).first()
    if incompatible:
        raise RuntimeError(
            f"Profile {incompatible[0]} cannot be downgraded without data loss"
        )
    op.add_column("profiles", sa.Column("catalog_id", sa.Uuid(), nullable=True))
    op.add_column("profiles", sa.Column("revision_id", sa.Uuid(), nullable=True))
    op.execute("""
        UPDATE profiles p SET catalog_id=i.catalog_id, revision_id=i.revision_id
        FROM profile_imports i WHERE i.tenant_id=p.tenant_id AND i.profile_id=p.id
    """)
    op.alter_column("profiles", "catalog_id", nullable=False)
    op.alter_column("profiles", "revision_id", nullable=False)
    op.create_foreign_key(
        "fk_profiles_source_revision_same_tenant",
        "profiles",
        "catalog_revisions",
        ["tenant_id", "catalog_id", "revision_id"],
        ["tenant_id", "catalog_id", "id"],
        ondelete="RESTRICT",
    )
    op.execute("DROP TRIGGER trg_profile_import_identity ON profile_imports")
    op.execute("DROP FUNCTION protect_profile_import_identity()")
    op.execute("DROP TRIGGER trg_implementation_identity ON control_implementations")
    op.execute("DROP FUNCTION protect_implementation_identity()")
    op.execute(
        "DROP TRIGGER trg_implementation_revision_lock ON control_implementations"
    )
    op.execute("DROP FUNCTION lock_implementation_revision()")
    op.execute("DROP TRIGGER trg_profile_import_source_immutable ON catalog_revisions")
    op.execute("DROP FUNCTION protect_profile_import_revision()")
    op.execute("DROP TRIGGER trg_profile_import_revision_lock ON profile_imports")
    op.execute("DROP FUNCTION lock_profile_import_revision()")
    op.drop_constraint(
        "ck_implementation_import_profile", "control_implementations", type_="check"
    )
    op.drop_constraint(
        "fk_implementations_profile_import",
        "control_implementations",
        type_="foreignkey",
    )
    op.drop_column("control_implementations", "profile_import_id")
    op.drop_index("ix_profile_imports_profile", table_name="profile_imports")
    op.drop_index("ix_profile_imports_revision", table_name="profile_imports")
    op.drop_table("profile_imports")
