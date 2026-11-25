"""Credenciais opacas; permissões vêm do servidor, nunca do conteúdo do modelo."""

import hashlib
import logging
import os
import time
from collections.abc import Iterable
from contextlib import contextmanager
from typing import Literal, TypedDict
from uuid import uuid4

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from contracts.execution import Executor
from services.backend.errors import fail
from services.backend.schema import administrative_events, permissions, principals

Role = Literal["operator", "worker"]
logger = logging.getLogger(__name__)


class Principal(TypedDict):
    principal_id: str
    token_sha256: str
    role: Role
    executor: Executor | None
    can_write: bool


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def identity_transaction(engine: Engine, principal_id: str):
    """Serialize alterações da mesma identidade até o commit ou rollback."""
    with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            conn.begin()
        try:
            if engine.dialect.name == "postgresql":
                # Serialize creation as well as updates of this identity across processes.
                key = int.from_bytes(
                    hashlib.sha256(("principal:" + principal_id).encode()).digest()[:8], signed=True
                )
                conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def identity_state(conn: Connection, row) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in ("role", "executor", "can_write")} | {
        "grants": [
            dict(item)
            for item in conn.execute(
                select(permissions.c.process_id, permissions.c.corpus_version)
                .where(permissions.c.principal_id == row["principal_id"])
                .order_by(permissions.c.process_id, permissions.c.corpus_version)
            ).mappings()
        ]
    }


def audit_identity(conn, principal_id, operation, source, before, after, credential_changed):
    conn.execute(
        insert(administrative_events).values(
            event_id=str(uuid4()),
            principal_id=principal_id,
            operation=operation,
            source=source,
            recorded_at=time.time(),
            before_state=before,
            after_state=after,
            credential_changed=credential_changed,
        )
    )


def check_profile(token, role, executor, can_write) -> None:
    """Regras de perfil de ``provision``, também usadas na conferência prévia do lote."""
    if (
        not isinstance(token, str)
        or len(token) < 32
        or role not in {"operator", "worker"}
        or type(can_write) is not bool
        or (role == "worker" and executor not in {"simulation", "hermes", "langgraph"})
        or (role == "operator" and executor is not None)
    ):
        raise ValueError("Credencial, perfil ou executor inválido.")


def provision(
    engine: Engine,
    principal_id: str,
    token: str,
    role: Role,
    grants: Iterable[tuple[str, str]],
    *,
    can_write: bool = False,
    executor: Executor | None = None,
    create_only: bool = False,
    update_only: bool = False,
    source: Literal["admin", "bootstrap"] = "admin",
) -> bool:
    """Crie ou atualize perfil e concessões em transação serializada por identidade."""
    with identity_transaction(engine, principal_id) as conn:
        existing = (
            conn.execute(
                select(principals)
                .where(principals.c.principal_id == principal_id)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if existing and create_only:
            return False
        if not existing and update_only:
            raise ValueError("Identidade ausente; crie o perfil explicitamente.")
        check_profile(token, role, executor, can_write)
        if source not in {"admin", "bootstrap"}:
            raise ValueError("Credencial, perfil ou executor inválido.")
        values = dict(
            token_sha256=token_hash(token), role=role, executor=executor, can_write=can_write
        )
        before = identity_state(conn, existing)
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
        current = (
            conn.execute(select(principals).where(principals.c.principal_id == principal_id))
            .mappings()
            .one()
        )
        audit_identity(
            conn,
            principal_id,
            "update" if existing else "create",
            source,
            before,
            identity_state(conn, current),
            existing is None or existing["token_sha256"] != values["token_sha256"],
        )
    return True


def rotate_token(engine: Engine, principal_id: str, token: str) -> None:
    """Rotate only the credential; preserve current role, executor, grants and write flag."""
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("Credencial inválida.")
    with identity_transaction(engine, principal_id) as conn:
        row = (
            conn.execute(
                select(principals)
                .where(principals.c.principal_id == principal_id)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ValueError("Identidade ausente; crie o perfil explicitamente.")
        state = identity_state(conn, row)
        hashed = token_hash(token)
        conn.execute(
            update(principals)
            .where(principals.c.principal_id == principal_id)
            .values(token_sha256=hashed)
        )
        audit_identity(
            conn, principal_id, "rotate", "admin", state, state, row["token_sha256"] != hashed
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
            try:
                created = provision(
                    engine,
                    name,
                    token,
                    role,
                    grants,
                    can_write=True,
                    executor="simulation" if role == "worker" else None,
                    create_only=True,
                    source="bootstrap",
                )
                if not created:
                    with engine.connect() as conn:
                        stored = conn.execute(
                            select(principals.c.token_sha256).where(
                                principals.c.principal_id == name
                            )
                        ).scalar_one_or_none()
                    # Perfil existente é preservado (I2); só avisa que o token do ambiente não
                    # autentica, sem registrar token nem hash.
                    if stored is not None and stored != token_hash(token):
                        logger.warning(
                            "bootstrap_token_mismatch principal_id=%s action=provision_rotate",
                            name,
                        )
            except SQLAlchemyError:
                raise RuntimeError("Falha ao preparar identidades locais.") from None


def authenticate(engine: Engine, authorization: str | None) -> Principal:
    """Resolva o bearer para um perfil do servidor; não derive permissões do modelo."""
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
