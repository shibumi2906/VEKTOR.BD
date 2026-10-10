from alembic import op

revision = "0003_legal_gate"
down_revision = "0002_legal_chains"
branch_labels = None
depends_on = None


def upgrade():
    # A raw PDF flag cannot bypass the compiler, even for an allegedly consolidated law.
    op.execute("""
    CREATE OR REPLACE VIEW registry.document_register AS
    SELECT d.document_id, f.slug AS document_alias, d.title, d.document_type,
    d.category,d.language,d.version_label,d.document_role,d.source_name,d.issuer,
    d.source_url,d.publication_date,d.effective_from,d.effective_to,
    d.version_status,d.legal_status,d.verification_status,d.ingestion_status,
    d.file_sha256,d.page_count,d.checked_at,d.indexed_at,
    COALESCE((d.document_role='official' AND d.version_status='current'
    AND d.legal_status='in_force' AND d.verification_status='verified'
    AND d.effective_from <= (now() AT TIME ZONE 'Asia/Jerusalem')::date
    AND (d.effective_to IS NULL OR d.effective_to >
    (now() AT TIME ZONE 'Asia/Jerusalem')::date)
    AND d.category NOT IN ('base_law','base_law_with_amendments','enacted_law',
    'temporary_law','amendment_gazette','gazette_erratum','consolidated_snapshot',
    'consolidated_law')),false) AS current_norms_eligible,
    (d.category IN ('base_law','base_law_with_amendments','enacted_law',
    'temporary_law','amendment_gazette','gazette_erratum','consolidated_snapshot',
    'consolidated_law')) AS legal_engine_required
    FROM registry.document_versions d JOIN registry.document_families f USING(family_id)
    """)


def downgrade():
    raise RuntimeError("Removing the legal gate can expose unverified laws; restore a backup")
