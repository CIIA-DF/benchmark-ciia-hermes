import argparse
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter

from app.config import Settings
from app.db.session import (
    IndexConfigurationError,
    create_database_engine,
    initialize_database,
    session_factory,
)
from app.ingestion import diagnostic, loader, parser
from app.ingestion.chunking import chunk_document
from app.ingestion.embeddings import Embedder, ModelError
from app.ingestion.indexing import ExportError, IndexExport, ParsedExport, index_exports
from sqlalchemy.exc import SQLAlchemyError


def prepare_pdfs(paths: list[Path], output: Path, reports: Path) -> list[Path]:
    if len({path.stem.casefold() for path in paths}) != len(paths):
        raise ExportError("Informe PDFs com nomes distintos.")
    results, jsonls = [], []
    for number, path in enumerate(paths, start=1):
        try:
            pages = loader.salvar_paginas_jsonl(loader.carregar_pdf(path), output)
            result = parser.processar_arquivo(pages)
            jsonls.append(parser.salvar_documentos_jsonl(result, output))
        except (loader.ErroIngestao, ValueError, OSError) as exc:
            raise ExportError(f"Falha na preparação do PDF na posição {number}.") from exc
        results.append(result)
    diagnostic.salvar_relatorio(diagnostic.gerar_relatorio(results, []), reports)
    return jsonls


def main() -> None:
    cli = argparse.ArgumentParser(description="Prepara exportações SEI e constrói o índice RAG.")
    cli.add_argument("files", nargs="*", type=Path, help="PDFs ou JSONLs completos com --jsonl")
    options = cli.add_mutually_exclusive_group()
    options.add_argument("--jsonl", action="store_true", help="Reutiliza JSONLs de documentos")
    options.add_argument("--prepare-only", action="store_true", help="Processa os PDFs sem indexar")
    cli.add_argument("--processed", type=Path, default=loader.PASTA_PROCESSED)
    cli.add_argument("--reports", type=Path, default=loader.PASTA_REPORTS)
    args = cli.parse_args()
    paths = args.files or sorted(
        args.processed.glob(f"*{parser.SUFIXO_DOCUMENTOS}")
        if args.jsonl
        else loader.PASTA_RAW.glob("*.pdf")
    )
    if not paths:
        cli.error("Informe arquivos de entrada ou coloque os PDFs em app/data/raw.")

    try:
        start = perf_counter()
        args.processed.mkdir(parents=True, exist_ok=True)
        output = Path(mkdtemp(prefix="build-", dir=args.processed))
        reports = args.reports / output.name
        jsonls = paths if args.jsonl else prepare_pdfs(paths, output, reports)
        exports = [ParsedExport.from_jsonl(path) for path in jsonls]
        sources = {(export.processo, export.arquivo) for export in exports}
        if len(sources) != len(exports):
            raise ExportError("A mesma exportação foi informada mais de uma vez.")

        summary = {
            "exports": len(exports),
            "documents": sum(len(export.documents) for export in exports),
            "pages": sum(len(doc["paginas"]) for export in exports for doc in export.documents),
            "run": output.name,
        }
        if not args.prepare_only:
            settings = Settings()
            encoder = Embedder(settings)
            engine = create_database_engine(settings)
            try:
                initialize_database(engine, settings)
                prepared = []
                with (output / "corpus.chunks.jsonl").open("w", encoding="utf-8") as stream:
                    for export in exports:
                        chunks = []
                        for doc in export.documents:
                            for chunk in chunk_document(
                                doc,
                                encoder.token_offsets,
                                settings.chunk_tokens,
                                settings.chunk_overlap,
                            ):
                                stream.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
                                chunks.append(chunk)
                        prepared.append(IndexExport(export, chunks))
                if not any(item.chunks for item in prepared):
                    raise ExportError("Nenhum trecho com texto limpo foi encontrado.")
                summary.update(index_exports(session_factory(engine), settings, encoder, prepared))
                summary["embedding"] = asdict(encoder.spec)
                summary["chunk_tokens"] = settings.chunk_tokens
                summary["chunk_overlap"] = settings.chunk_overlap
                summary["embedding_batch_size"] = settings.embedding_batch_size
            finally:
                engine.dispose()
        summary["elapsed_seconds"] = round(perf_counter() - start, 3)
        reports.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(summary, ensure_ascii=False)
        (reports / "build.json").write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    except (ExportError, IndexConfigurationError, ModelError) as exc:
        cli.exit(1, f"{exc}\n")
    except SQLAlchemyError:
        cli.exit(1, "Falha no PostgreSQL. Confira acesso, esquema e extensão pgvector.\n")
    except (ValueError, OSError):
        cli.exit(1, "Falha de configuração ou leitura/gravação dos arquivos do RAG.\n")


if __name__ == "__main__":
    main()
