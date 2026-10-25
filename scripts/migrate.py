"""Migra schema; downgrade remove dados das tabelas afetadas e exige backup prévio."""

import argparse

from services.backend.migrate import migrate
from services.backend.storage import make_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direction", choices=["upgrade", "downgrade"])
    parser.add_argument("revision")
    args = parser.parse_args()
    engine = make_engine()
    try:
        migrate(engine, args.revision, downgrade=args.direction == "downgrade")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
