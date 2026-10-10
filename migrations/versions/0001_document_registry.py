from pathlib import Path

from alembic import op

revision = "0001_registry"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).parents[1] / "registry.sql").read_text(encoding="utf-8")
    for statement in sql.split("-- next statement"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError("Registry downgrade loses records; restore a backup instead")
