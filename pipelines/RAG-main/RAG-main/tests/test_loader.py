"""Testes da RAG-01 (loader): PDF -> páginas em JSONL."""

import json

import pytest

pymupdf = pytest.importorskip("pymupdf")

from app.ingestion import loader  # noqa: E402

PDF_2024 = loader.PASTA_RAW / "SEI_04030_00001001_2024_23 (2).pdf"
PDF_2025 = loader.PASTA_RAW / "SEI_04030_00001179_2025_55 (2).pdf"

precisa_dos_pdfs = pytest.mark.skipif(
    not (PDF_2024.exists() and PDF_2025.exists()), reason="PDFs reais não estão em app/data/raw/"
)


def _pdf(caminho, *textos):
    doc = pymupdf.open()
    for texto in textos:
        doc.new_page().insert_text((72, 72), texto)
    doc.save(caminho)
    doc.close()


def _linhas(caminho):
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines()]


RODAPE = "Memorando 1 (123456789) SEI 04030-00000001/2024-01 / pg. {}"


def test_uma_linha_por_pagina_com_metadados(tmp_path):
    pdf = tmp_path / "SEI_04030_00000001_2024_01.pdf"
    _pdf(
        pdf, "Texto da primeira página.\n" + RODAPE.format(1), "Outra página.\n" + RODAPE.format(2)
    )

    (resultado,), erros = loader.processar([pdf], tmp_path)
    linhas = _linhas(tmp_path / "SEI_04030_00000001_2024_01.paginas.jsonl")

    assert erros == []
    assert [linha["pagina"] for linha in linhas] == [1, 2]
    for linha in linhas:
        assert linha["arquivo_origem"] == pdf.name
        assert linha["processo_sei"] == "04030-00000001/2024-01"
        assert linha["rodape"]["documento_sei_id"] == "123456789"
        assert "texto" in linha and "flags" in linha
    assert resultado["avisos"] == []


def test_reexecucao_nao_duplica(tmp_path):
    pdf = tmp_path / "a.pdf"
    _pdf(pdf, "Página única com texto suficiente.\n" + RODAPE.format(1))
    loader.processar([pdf], tmp_path)
    loader.processar([pdf], tmp_path)
    assert len(_linhas(tmp_path / "a.paginas.jsonl")) == 1


def test_divergencia_entre_nome_e_rodape_gera_aviso(tmp_path):
    pdf = tmp_path / "SEI_04030_00009999_2024_01.pdf"
    _pdf(pdf, "Texto.\n" + RODAPE.format(1))
    resultado = loader.carregar_pdf(pdf)
    assert resultado["processo_sei"] == "04030-00000001/2024-01"  # vale o conteúdo
    assert any("nome do arquivo indica" in aviso for aviso in resultado["avisos"])


def test_pagina_sem_texto_e_sem_rodape_e_mantida_e_sinalizada(tmp_path):
    pdf = tmp_path / "b.pdf"
    _pdf(pdf, "")
    (pagina,) = loader.carregar_pdf(pdf)["paginas"]
    assert pagina["texto"].strip() == ""
    assert {"sem_texto", "sem_rodape"} <= set(pagina["flags"])


def test_pdf_invalido_ou_inexistente_nao_interrompe(tmp_path):
    quebrado = tmp_path / "quebrado.pdf"
    quebrado.write_bytes(b"isto nao e um pdf")
    bom = tmp_path / "bom.pdf"
    _pdf(bom, "Texto.\n" + RODAPE.format(1))

    resultados, erros = loader.processar([quebrado, tmp_path / "nao_existe.pdf", bom], tmp_path)

    assert sorted(e["arquivo"] for e in erros) == ["nao_existe.pdf", "quebrado.pdf"]
    assert [r["arquivo_origem"] for r in resultados] == ["bom.pdf"]


def test_caminho_por_argumento(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "PASTA_REPORTS", tmp_path / "reports")
    pdf = tmp_path / "c.pdf"
    _pdf(pdf, "Texto.\n" + RODAPE.format(1))
    assert loader.main([str(pdf), "--saida", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "c.paginas.jsonl").exists()


@precisa_dos_pdfs
@pytest.mark.parametrize(
    "pdf, total, processo",
    [
        (PDF_2024, 61, "04030-00001001/2024-23"),
        (PDF_2025, 212, "04030-00001179/2025-55"),
    ],
)
def test_pdfs_reais_todas_as_paginas(pdf, total, processo):
    resultado = loader.carregar_pdf(pdf)
    assert resultado["processo_sei"] == processo
    assert [p["pagina"] for p in resultado["paginas"]] == list(range(1, total + 1))
    assert all(p["rodape"] for p in resultado["paginas"])  # todas têm rodapé SEI
    assert resultado["avisos"] == []
