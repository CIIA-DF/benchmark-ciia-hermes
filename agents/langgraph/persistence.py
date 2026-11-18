"""Checkpointer SQLite local com desserialização MsgPack restrita."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver


@contextmanager
def open_persistent_checkpointer(path: str | Path | None = None) -> Iterator[SqliteSaver]:
    """Abre o armazenamento retomável configurado por ``LANGGRAPH_CHECKPOINT_PATH``.

    O arquivo contém mensagens e resultados de ferramentas do grafo; use apenas
    corpus sintético enquanto o ambiente não tiver controles de acesso e retenção.
    """

    checkpoint_path = Path(
        path or os.getenv("LANGGRAPH_CHECKPOINT_PATH", "data/langgraph-checkpoints.sqlite")
    )
    if str(checkpoint_path) != ":memory:":
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
        saver.setup()
        saver.serde = JsonPlusSerializer(allowed_msgpack_modules=None)
        yield saver
