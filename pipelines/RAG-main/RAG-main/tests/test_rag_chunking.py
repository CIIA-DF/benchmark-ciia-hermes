import json
import re

import pymupdf
import pytest
from app.ingestion.chunking import chunk_document, read_documents
from app.ingestion.indexing import ExportError, ParsedExport
from scripts.build_index import prepare_pdfs

PROCESSO = "00000-00000001/2025-01"


def offsets(text):
    return [match.span() for match in re.finditer(r"\S+", text)]


def test_pdf_usa_loader_parser_e_texto_limpo(tmp_path):
    path = tmp_path / "exportacao-sintetica.pdf"
    pages = [
        ("alpha beta gama delta", "Oficio 123456"),
        ("    ", "Oficio 123456"),
        ("epsilon zeta eta theta", "Oficio 123456"),
        ("iota kappa lambda mu", "Despacho 234567"),
    ]
    with pymupdf.open() as pdf:
        for number, (text, label) in enumerate(pages, start=1):
            page = pdf.new_page()
            page.insert_text((72, 72), f"{text}\n{label} SEI {PROCESSO} / pg. {number}")
        pdf.save(path)

    (jsonl,) = prepare_pdfs([path], tmp_path / "out", tmp_path / "reports")
    parsed = list(read_documents(jsonl))
    assert len(parsed) == 2
    assert (tmp_path / "reports" / "relatorio_ingestao.json").is_file()
    assert ParsedExport.from_jsonl(jsonl).processo == PROCESSO

    chunks = [chunk for doc in parsed for chunk in chunk_document(doc, offsets, 5, 2)]
    assert chunks == [chunk for doc in parsed for chunk in chunk_document(doc, offsets, 5, 2)]
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks) == 3
    assert [chunk.text.split() for chunk in chunks] == [
        ["alpha", "beta", "gama", "delta", "epsilon"],
        ["delta", "epsilon", "zeta", "eta", "theta"],
        ["iota", "kappa", "lambda", "mu"],
    ]
    assert [chunk.paginas_origem for chunk in chunks] == [(1, 3), (1, 3), (4,)]
    assert [chunk.pagina_inicio for chunk in chunks] == [1, 1, 4]
    assert [chunk.pagina_fim for chunk in chunks] == [3, 3, 4]
    assert [chunk.token_count for chunk in chunks] == [5, 5, 4]
    assert [chunk.documento_sei_id for chunk in chunks] == ["123456", "123456", "234567"]
    assert chunks[2].tipo_documento == "Despacho"
    assert all(
        chunk.processo_sei == PROCESSO and chunk.arquivo_origem == path.name for chunk in chunks
    )


def test_texto_vazio_e_id_repetido():
    document = {
        "processo_sei": PROCESSO,
        "arquivo_origem": "teste.pdf",
        "pagina_inicio": 1,
        "documento_sei_id": None,
        "tipo_documento": None,
        "paginas": [],
    }
    assert list(chunk_document(document, offsets)) == []

    document["documento_sei_id"] = "123456"
    document["paginas"] = [{"pagina": 1, "texto_limpo": "Texto sintético."}]
    (first,) = chunk_document(document, offsets)
    other = {**document, "pagina_inicio": 2, "paginas": [{"pagina": 2, "texto_limpo": first.text}]}
    (second,) = chunk_document(other, offsets)
    assert first.document_key != second.document_key
    assert first.chunk_id != second.chunk_id


def test_rejeita_jsonl_de_exportacao_inconsistente(tmp_path):
    path = tmp_path / "corpus.documentos.jsonl"
    path.write_text(
        json.dumps(
            {
                "processo_sei": PROCESSO,
                "arquivo_origem": "teste.pdf",
                "pagina_inicio": 2,
                "pagina_fim": 2,
                "documento_sei_id": None,
                "tipo_documento": None,
                "paginas": [{"pagina": 2, "texto_limpo": "Texto sintético."}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExportError, match="consecutivas"):
        ParsedExport.from_jsonl(path)
