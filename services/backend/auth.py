"""Credenciais opacas; permissões vêm do servidor, nunca do conteúdo do modelo."""

import hashlib
import os

from sqlalchemy import delete, insert, select, update

from services.backend.errors import fail
from services.backend.schema import permissions, principals


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def provision(engine, principal_id, token, role, grants, *, can_write=False, executor=None):
    if len(token) < 32 or role not in {"operator", "worker"}:
        raise ValueError("Credencial deve ter 32 caracteres e perfil conhecido.")
    values = dict(token_sha256=token_hash(token), role=role, executor=executor, can_write=can_write)
    with engine.begin() as conn:
        existing = conn.execute(
            select(principals).where(principals.c.principal_id == principal_id)
        ).first()
        if existing:
            conn.execute(
                update(principals).where(principals.c.principal_id == principal_id).values(**values)
            )
        else:
            conn.execute(insert(principals).values(principal_id=principal_id, **values))
        conn.execute(delete(permissions).where(permissions.c.principal_id == principal_id))
        for process_id, corpus_version in grants:
            conn.execute(
                insert(permissions).values(
                    principal_id=principal_id, process_id=process_id, corpus_version=corpus_version
                )
            )


def bootstrap(engine):
    # Configuração inicial local é limitada ao corpus fictício, sem curingas de acesso.
    grants = [("PROC-DEMO-001", "synthetic-v1")]
    for env, name, role in [
        ("BACKEND_OPERATOR_TOKEN", "local-operator", "operator"),
        ("BACKEND_WORKER_TOKEN", "simulation-worker", "worker"),
    ]:
        token = os.getenv(env)
        if token:
            provision(
                engine,
                name,
                token,
                role,
                grants,
                can_write=True,
                executor="simulation" if role == "worker" else None,
            )


def authenticate(engine, authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        fail(401, "unauthorized", "Credencial necessária.")
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(principals).where(principals.c.token_sha256 == token_hash(authorization[7:]))
            )
            .mappings()
            .first()
        )
    if row is None:
        fail(401, "unauthorized", "Credencial inválida.")
    return dict(row)


def authorize(conn, principal_id, process_id, corpus_version):
    found = conn.execute(
        select(permissions).where(
            permissions.c.principal_id == principal_id,
            permissions.c.process_id == process_id,
            permissions.c.corpus_version == corpus_version,
        )
    ).first()
    if not found:
        fail(403, "forbidden", "Processo/corpus fora das permissões do perfil.")
