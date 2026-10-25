"""Importa checklist administrativo versionado, sem endpoint de escrita para o agente."""

import argparse
import json

from sqlalchemy import insert, select

from contracts.models import Requirement
from services.backend.schema import requirements
from services.backend.storage import initialize, make_engine, processes


def import_checklist(engine, process_id, corpus_version, requirements_version, values):
    items = [Requirement.model_validate(v) for v in values]
    if not items or len({v.requirement_id for v in items}) != len(items):
        raise ValueError("Checklist vazio ou com IDs duplicados.")
    with engine.begin() as conn:
        process = conn.execute(
            select(processes.c.payload)
            .where(
                processes.c.process_id == process_id, processes.c.corpus_version == corpus_version
            )
            .with_for_update()
        ).scalar_one()
        if process["requirements_version"] != requirements_version:
            raise ValueError("Versão não corresponde ao processo/corpus.")
        scope = (
            requirements.c.process_id == process_id,
            requirements.c.corpus_version == corpus_version,
            requirements.c.requirements_version == requirements_version,
        )
        old = conn.execute(select(requirements.c.payload).where(*scope)).scalars().all()
        expected = {v.requirement_id: v.model_dump(mode="json") for v in items}
        if old:
            if {v["requirement_id"]: v for v in old} != expected:
                raise ValueError("Checklist imutável: alteração exige nova versão.")
            return
        conn.execute(
            insert(requirements),
            [
                dict(
                    process_id=process_id,
                    corpus_version=corpus_version,
                    requirements_version=requirements_version,
                    requirement_id=v.requirement_id,
                    payload=v.model_dump(mode="json"),
                )
                for v in items
            ],
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    parser.add_argument("--process", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    engine = make_engine()
    initialize(engine)
    with open(args.file, encoding="utf-8") as stream:
        import_checklist(engine, args.process, args.corpus, args.version, json.load(stream))
    engine.dispose()


if __name__ == "__main__":
    main()
