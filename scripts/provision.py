"""Provisiona perfis a partir de configuração privada e tokens em variáveis de ambiente."""

import argparse
import json
import os

from services.backend.auth import provision
from services.backend.storage import initialize, make_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="JSON privado; cada identidade referencia token_env.")
    args = parser.parse_args()
    with open(args.file, encoding="utf-8") as stream:
        identities = json.load(stream)
    engine = make_engine()
    try:
        initialize(engine)
        for identity in identities:
            provision(
                engine,
                identity["principal_id"],
                os.environ[identity["token_env"]],
                identity["role"],
                [(v["process_id"], v["corpus_version"]) for v in identity["grants"]],
                can_write=identity.get("can_write", False),
                executor=identity.get("executor"),
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
