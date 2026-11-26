import re
from dataclasses import dataclass
from itertools import batched
from pathlib import Path, PureWindowsPath

from sqlalchemy import String, all_, cast, delete, select
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import Chunk, Document, Embedding, Process
from app.db.session import require_profile
from app.ingestion.chunking import ChunkData, document_key, read_documents
from app.ingestion.embeddings import EmbeddingEncoder
from app.schemas.query import DOCUMENT_PATTERN, PROCESS_PATTERN


class ExportError(ValueError):
    """Arquivo de entrada inválido ou incompleto para indexação."""


@dataclass(frozen=True)
class ParsedExport:
    processo: str
    arquivo: str
    documents: list[dict]

    @classmethod
    def from_jsonl(cls, path: Path) -> "ParsedExport":
        try:
            documents = list(read_documents(path))
            if not documents:
                raise ExportError("JSONL de documentos vazio.")
            process = documents[0]["processo_sei"]
            source = documents[0]["arquivo_origem"]
            if not isinstance(process, str) or not re.fullmatch(PROCESS_PATTERN, process):
                raise ExportError("O parser não identificou um número de processo válido.")
            if not source or PureWindowsPath(source).name != source:
                raise ExportError("O JSONL precisa identificar o arquivo de origem pelo nome.")

            expected = 1
            for doc in documents:
                start, end = doc["pagina_inicio"], doc["pagina_fim"]
                sei_id = doc["documento_sei_id"]
                doc_type = doc["tipo_documento"]
                if doc["processo_sei"] != process or doc["arquivo_origem"] != source:
                    raise ExportError("O JSONL deve conter uma única exportação do SEI.")
                if sei_id is not None and not re.fullmatch(DOCUMENT_PATTERN, sei_id):
                    raise ExportError("O JSONL contém um ID de documento SEI inválido.")
                if doc_type is not None and not isinstance(doc_type, str):
                    raise ExportError("O JSONL contém um tipo de documento inválido.")
                if start != expected or end < start or len(doc["paginas"]) != end - start + 1:
                    raise ExportError("As páginas da exportação devem ser consecutivas desde 1.")
                for number, page in enumerate(doc["paginas"], start):
                    if page["pagina"] != number or not isinstance(page["texto_limpo"], str):
                        raise ExportError("Página fora de sequência ou com texto limpo inválido.")
                expected = end + 1
        except ExportError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ExportError("O arquivo não segue o esquema JSONL do parser SEI.") from exc
        return cls(process, source, documents)


@dataclass(frozen=True)
class IndexExport:
    export: ParsedExport
    chunks: list[ChunkData]


def index_exports(
    sessions: sessionmaker[Session],
    settings: Settings,
    encoder: EmbeddingEncoder,
    exports: list[IndexExport],
) -> dict[str, int]:
    if encoder.spec != settings.embedding:
        raise ValueError("O encoder precisa corresponder ao perfil configurado.")

    chunks = {chunk.chunk_id: chunk for item in exports for chunk in item.chunks}
    cached = {}
    with sessions() as session:
        require_profile(session, settings)
        for ids in batched(chunks, 500):
            statement = select(Embedding.chunk_id, Embedding.vector).where(
                Embedding.chunk_id.in_(ids)
            )
            cached.update(session.execute(statement).tuples().all())

    # Inferência fora da transação de escrita. Guardamos também os vetores do cache,
    # pois outra ingestão pode substituir a exportação enquanto calculamos os demais.
    vectors = dict(cached)
    missing = (chunk for key, chunk in chunks.items() if key not in cached)
    for batch in batched(missing, settings.embedding_batch_size):
        encoded = encoder.encode([chunk.text for chunk in batch])
        vectors.update(
            (chunk.chunk_id, vector) for chunk, vector in zip(batch, encoded, strict=True)
        )

    with sessions.begin() as session:
        require_profile(session, settings, lock=True)
        documents = insert(Document)
        for item in exports:
            export = item.export
            session.execute(
                insert(Process).values(processo_sei=export.processo).on_conflict_do_nothing()
            )
            rows = [
                {
                    "document_key": document_key(doc),
                    "processo_sei": export.processo,
                    "arquivo_origem": export.arquivo,
                    "documento_sei_id": doc["documento_sei_id"],
                    "tipo_documento": doc["tipo_documento"],
                    "pagina_inicio": doc["pagina_inicio"],
                    "pagina_fim": doc["pagina_fim"],
                    "parser_metadata": {
                        key: doc.get(key)
                        for key in (
                            "rotulo",
                            "numero_documento",
                            "assunto",
                            "data_documento",
                            "data_assinatura",
                            "unidade",
                            "alertas",
                        )
                    },
                }
                for doc in export.documents
            ]
            session.execute(
                documents.on_conflict_do_update(
                    index_elements=[Document.document_key],
                    set_={
                        key: documents.excluded[key]
                        for key in (
                            "documento_sei_id",
                            "tipo_documento",
                            "pagina_fim",
                            "parser_metadata",
                        )
                    },
                ),
                rows,
            )
            document_ids = [row["document_key"] for row in rows]
            chunk_ids = [chunk.chunk_id for chunk in item.chunks]
            session.execute(
                delete(Document).where(
                    Document.processo_sei == export.processo,
                    Document.arquivo_origem == export.arquivo,
                    Document.document_key != all_(cast(document_ids, ARRAY(String))),
                )
            )
            session.execute(
                delete(Chunk).where(
                    Chunk.document_key.in_(document_ids),
                    Chunk.chunk_id != all_(cast(chunk_ids, ARRAY(String))),
                )
            )
            if item.chunks:
                session.execute(
                    insert(Chunk).on_conflict_do_nothing(index_elements=[Chunk.chunk_id]),
                    [
                        {
                            "chunk_id": chunk.chunk_id,
                            "document_key": chunk.document_key,
                            "text": chunk.text,
                            "paginas_origem": list(chunk.paginas_origem),
                            "token_count": chunk.token_count,
                        }
                        for chunk in item.chunks
                    ],
                )
                session.execute(
                    insert(Embedding).on_conflict_do_nothing(index_elements=[Embedding.chunk_id]),
                    [{"chunk_id": key, "vector": vectors[key]} for key in chunk_ids],
                )

    return {
        "exports": len(exports),
        "documents": sum(len(item.export.documents) for item in exports),
        "chunks": len(chunks),
        "embeddings_generated": len(vectors) - len(cached),
        "embeddings_reused": len(cached),
    }
