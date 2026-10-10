"""Global daily reservations survive retries and concurrent API requests."""

from alembic import op

revision = "0007_provider_budget"
down_revision = "0006_document_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE registry.provider_reservations (
        reservation_id uuid PRIMARY KEY,request_id uuid NOT NULL,model text NOT NULL,
        reserved_usd double precision NOT NULL CHECK(reserved_usd>0),
        created_at timestamptz NOT NULL DEFAULT now())""")


def downgrade():
    raise RuntimeError("Restore backup instead of discarding cost accounting")
