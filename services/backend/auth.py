"""Credenciais opacas; permissões vêm do servidor, nunca do conteúdo do modelo."""

import hashlib
import os
from collections.abc import Iterable
from typing import Literal, TypedDict

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection, Engine

from contracts.execution import Executor
from services.backend.errors import fail
from services.backend.schema import permissions, principals

Role = Literal["operator", "worker"]


class Principal(TypedDict):
    principal_id: str
    token_sha256: str
    role: Role
    executor: Executor | None
    can_write: bool


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def provision(
    engine: Engine,
    principal_id: str,
    token: str,
    role: Role,
    grants: Iterable[tuple[str, str]],
    *,
    can_write: bool = False,
    executor: Executor | None = None,
) -> None:
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


def bootstrap(engine: Engine) -> None:
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


def authenticate(engine: Engine, authorization: str | None) -> Principal:
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
    return Principal(
        principal_id=row["principal_id"],
        token_sha256=row["token_sha256"],
        role=row["role"],
        executor=row["executor"],
        can_write=row["can_write"],
    )


def authorize(conn: Connection, principal_id: str, process_id: str, corpus_version: str) -> None:
    found = conn.execute(
        select(permissions).where(
            permissions.c.principal_id == principal_id,
            permissions.c.process_id == process_id,
            permissions.c.corpus_version == corpus_version,
        )
    ).first()
    if not found:
        fail(403, "forbidden", "Processo/corpus fora das permissões do perfil.")
