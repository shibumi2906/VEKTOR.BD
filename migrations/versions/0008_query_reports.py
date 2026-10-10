"""Persist validated citations with request identity; access remains project-scoped."""

from alembic import op

revision = "0008_query_reports"
down_revision = "0007_provider_budget"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE registry.query_reports (
        request_id uuid PRIMARY KEY,actor_id uuid NOT NULL REFERENCES registry.actors,
        payload jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now())""")


def downgrade():
    raise RuntimeError("Restore backup instead of discarding citation evidence")
