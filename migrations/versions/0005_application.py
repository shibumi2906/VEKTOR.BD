from pathlib import Path

from alembic import op

revision = "0005_application"
down_revision = "0004_chunks"
branch_labels = None
depends_on = None


def upgrade():
    for statement in (
        (Path(__file__).parents[1] / "application.sql")
        .read_text("utf-8")
        .split("-- next statement")
    ):
        op.execute(statement)


def downgrade():
    raise RuntimeError("Removing access, jobs and generations requires backup restoration")
