"""Create local credentials without printing them or overwriting an existing .env."""

import secrets
from pathlib import Path
from urllib.parse import quote

root = Path(__file__).resolve().parent.parent
target = root / ".env"
if target.exists():
    raise SystemExit(".env already exists; retained unchanged")
password = secrets.token_urlsafe(32)
content = (root / ".env.example").read_text(encoding="utf-8")
content = content.replace("POSTGRES_PASSWORD=\n", f"POSTGRES_PASSWORD={password}\n")
content = content.replace(
    "POSTGRES_URL=\n", f"POSTGRES_URL=postgresql://pinui:{quote(password)}@postgres:5432/pinui\n"
)
with target.open("x", encoding="utf-8", newline="\n") as output:
    output.write(content)
print("Created local .env; credentials are not displayed. OPENAI_API_KEY remains empty.")
