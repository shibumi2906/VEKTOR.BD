import hashlib
import hmac
from uuid import UUID

from app.registry.corpus import identity
from app.services.errors import DomainError


async def local_owner(connection):
    actor = identity("actor:local-owner")
    await connection.execute(
        "INSERT INTO registry.actors VALUES($1,'admin','local-owner',true) "
        "ON CONFLICT(actor_id) DO UPDATE SET enabled=true",
        actor,
    )
    # Existing schema uses admin/reader internally; local UI has no roles or login.
    return {"actor_id": actor, "role": "admin"}


async def authenticate(connection, settings, token):
    if not token:
        raise DomainError("UNAUTHORIZED", 401)
    for role, secret in (
        ("admin", settings.admin_api_token),
        ("reader", settings.reader_api_token),
    ):
        value = secret.get_secret_value()
        if value and hmac.compare_digest(value, token):
            actor = identity("actor:" + role)
            hashed = hashlib.sha256(token.encode()).hexdigest()
            await connection.execute(
                """INSERT INTO registry.actors VALUES($1,$2,$3,true)
                ON CONFLICT(actor_id) DO UPDATE SET token_hash=EXCLUDED.token_hash""",
                actor,
                role,
                hashed,
            )
            enabled = await connection.fetchval(
                "SELECT enabled FROM registry.actors WHERE actor_id=$1", actor
            )
            if enabled:
                return {"actor_id": actor, "role": role}
    raise DomainError("UNAUTHORIZED", 401)


async def documents(connection, actor):
    return await connection.fetch(
        """SELECT d.*,f.slug AS document_alias,f.project_id,r.current_norms_eligible,
        r.legal_engine_required FROM registry.document_versions d
        JOIN registry.document_families f USING(family_id)
        JOIN registry.document_register r USING(document_id)
        WHERE $1='admin' OR f.project_id IS NULL OR EXISTS
        (SELECT 1 FROM registry.project_grants g WHERE g.project_id=f.project_id AND g.actor_id=$2)
        ORDER BY d.created_at""",
        actor["role"],
        actor["actor_id"],
    )


async def document(connection, actor, document_id):
    for row in await documents(connection, actor):
        if row["document_id"] == UUID(str(document_id)):
            return row
    raise DomainError("NOT_FOUND", 404)


def require_admin(actor):
    if actor["role"] != "admin":
        raise DomainError("FORBIDDEN", 403)
