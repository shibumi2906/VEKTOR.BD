from pathlib import Path

from alembic import op

revision = "0002_legal_chains"
down_revision = "0001_registry"
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).parents[1] / "legal_chains.sql").read_text("utf-8")
    for statement in sql.split("-- next statement"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError("Legal evidence/snapshots cannot be removed safely; restore a backup")
