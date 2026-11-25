"""Provisiona perfis a partir de configuração privada e tokens em variáveis de ambiente."""

import argparse
import json
import os

from pydantic import BaseModel, Field, StrictBool, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from contracts.execution import Executor
from contracts.models import Identifier
from services.backend.auth import Role, check_profile, provision, rotate_token, token_hash
from services.backend.schema import principals
from services.backend.storage import initialize, make_engine


class GrantInput(BaseModel):
    model_config = {"extra": "forbid"}
    process_id: Identifier
    corpus_version: Identifier


class IdentityInput(BaseModel):
    model_config = {"extra": "forbid"}
    principal_id: Identifier
    token_env: str = Field(strict=True, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    role: Role | None = None
    grants: list[GrantInput] | None = None
    can_write: StrictBool | None = None
    executor: Executor | None = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="JSON privado; cada identidade referencia token_env.")
    parser.add_argument("--operation", choices=["create", "update", "rotate"], default="create")
    args = parser.parse_args()
    try:
        with open(args.file, encoding="utf-8") as stream:
            identities = TypeAdapter(list[IdentityInput]).validate_python(json.load(stream))
        prepared = []
        for identity in identities:
            token = os.environ[identity.token_env]
            if len(token) < 32:
                raise ValueError("Credencial inválida.")
            if args.operation == "rotate":
                if identity.model_fields_set - {"principal_id", "token_env"}:
                    raise ValueError("Rotação não modifica perfil ou concessões.")
            else:
                # can_write é explícito como role e grants: omitir não pode revogar escrita.
                if identity.role is None or identity.grants is None or identity.can_write is None:
                    raise ValueError("Criação/atualização exige perfil e concessões explícitos.")
                check_profile(token, identity.role, identity.executor, identity.can_write)
            prepared.append((identity, token))
        # Identidade ou credencial repetida falharia no meio do lote; recuse antes do banco.
        if len({identity.principal_id for identity, _ in prepared}) != len(prepared) or len(
            {token for _, token in prepared}
        ) != len(prepared):
            raise ValueError("Identidade ou credencial repetida no arquivo.")
    except (OSError, KeyError, ValueError, ValidationError):
        parser.exit(
            2, "Configuração administrativa inválida; confira operação e campos privados.\n"
        )
    engine = None
    applied = 0
    try:
        engine = make_engine()
        initialize(engine)
        # O lote inteiro é conferido antes da primeira escrita: perfil (acima), existência
        # (create exige ausentes; update/rotate, existentes) e credencial de outro perfil.
        # Resta só a corrida com outro processo entre esta leitura e a escrita; nesse caso a
        # mensagem informa quantos perfis foram aplicados.
        names = [identity.principal_id for identity, _ in prepared]
        hashes = {token_hash(token): identity.principal_id for identity, token in prepared}
        with engine.connect() as connection:
            existing = set(
                connection.execute(
                    select(principals.c.principal_id).where(principals.c.principal_id.in_(names))
                ).scalars()
            )
            owners = connection.execute(
                select(principals.c.token_sha256, principals.c.principal_id).where(
                    principals.c.token_sha256.in_(list(hashes))
                )
            ).all()
        expected = set() if args.operation == "create" else set(names)
        if existing != expected or any(hashes[h] != owner for h, owner in owners):
            raise ValueError("Lote incompatível com a operação administrativa.")
        for identity, token in prepared:
            if args.operation == "rotate":
                rotate_token(engine, identity.principal_id, token)
                applied += 1
                continue
            changed = provision(
                engine,
                identity.principal_id,
                token,
                identity.role,
                [(v.process_id, v.corpus_version) for v in identity.grants],
                can_write=identity.can_write,
                executor=identity.executor,
                create_only=args.operation == "create",
                update_only=args.operation == "update",
            )
            if not changed:
                raise ValueError("Identidade existente; escolha operação administrativa explícita.")
            applied += 1
    except (SQLAlchemyError, ValueError, OSError):
        # Só a contagem: sem principal_id, token ou payload na saída (I2).
        parser.exit(
            2,
            "Operação administrativa recusada; confira perfil, operação e banco. "
            f"Perfis aplicados: {applied} de {len(prepared)}.\n",
        )
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
