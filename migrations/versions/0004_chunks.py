from pathlib import Path

from alembic import op

revision = "0004_chunks"
down_revision = "0003_legal_gate"
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).parents[1] / "chunks.sql").read_text("utf-8")
    for statement in sql.split("-- next statement"):
        op.execute(statement)


def downgrade():
    raise RuntimeError("Removing parsed source spans loses citations; restore a backup")
