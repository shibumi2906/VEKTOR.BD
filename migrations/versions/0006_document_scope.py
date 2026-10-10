from alembic import op

revision = "0006_document_scope"
down_revision = "0005_application"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE registry.document_families DROP CONSTRAINT document_families_slug_key")
    op.execute("CREATE UNIQUE INDEX shared_family_slug ON registry.document_families(slug) WHERE project_id IS NULL")
    op.execute("CREATE UNIQUE INDEX project_family_slug ON registry.document_families(project_id,slug) WHERE project_id IS NOT NULL")
    op.execute("ALTER TABLE registry.document_versions ALTER COLUMN page_count DROP NOT NULL")
    op.execute("ALTER TABLE registry.document_versions ADD COLUMN active_parsing_revision uuid")
    op.execute("""ALTER TABLE registry.document_versions ADD CONSTRAINT parsing_same_document
               FOREIGN KEY(document_id,active_parsing_revision)
               REFERENCES registry.parsing_revisions(document_id,parsing_revision)""")


def downgrade():
    raise RuntimeError("Restoring global aliases could merge project scopes; use backup restore")
