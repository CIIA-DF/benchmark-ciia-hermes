"""Testes da RAG-02 (parser): páginas -> documentos SEI em JSONL."""

import json
import re

import pytest
from app.ingestion import parser
from app.ingestion.diagnostic import gerar_relatorio


def _pagina(numero, texto, doc_id=None, rotulo="Memorando 1", processo="04030-00000001/2024-01"):
    rodape = None
    if doc_id:
        rodape = {
            "rotulo": rotulo,
            "documento_sei_id": doc_id,
            "processo_sei": processo,
            "pagina": numero,
        }
    return {
        "arquivo_origem": "teste.pdf",
        "processo_sei": processo,
        "pagina": numero,
        "texto": texto,
        "rodape": rodape,
        "cobertura_imagens": 0.0,
        "flags": [] if rodape else ["sem_rodape"],
    }


MEMORANDO = (
    "Governo do Distrito Federal\nReitoria\nMemorando Nº 7/2024 - UNDF/REIT/CEINTER\n"
    "Brasília-DF, 07 de maio de 2024.\nÀ Reitoria\nAssunto: Pedido de anuência\n1.\n"
    "Solicito termo de anuência para o projeto de pesquisa.\n"
)
DESPACHO = (
    "Reitoria\nDespacho - UNDF/REIT\nBrasília, 09 de maio de 2024.\n"
    "Assunto: Termo de anuência\n1.\nEncaminho para ciência.\n"
)


# --------------------------------------------------------------------------
# Unitários (páginas sintéticas)
# --------------------------------------------------------------------------


def test_separa_documentos_e_extrai_metadados():
    paginas = [
        _pagina(1, MEMORANDO, "111111111", "Memorando 7"),
        _pagina(2, "continuação do memorando", "111111111", "Memorando 7"),
        _pagina(3, DESPACHO, "222222222", "Despacho"),
    ]
    memorando, despacho = parser.montar_documentos(paginas)

    assert (memorando["pagina_inicio"], memorando["pagina_fim"]) == (1, 2)
    assert memorando["numero_documento"] == "7/2024 - UNDF/REIT/CEINTER"
    assert memorando["assunto"] == "Pedido de anuência"
    assert memorando["data_documento"] == "2024-05-07"
    assert memorando["unidade"] == "UNDF/REIT/CEINTER"
    assert [p["pagina_no_documento"] for p in memorando["paginas"]] == [1, 2]

    assert despacho["tipo_documento"] == "Despacho"
    assert despacho["numero_documento"] is None
    assert despacho["unidade"] == "UNDF/REIT"
    assert despacho["data_documento"] == "2024-05-09"
    assert memorando["alertas"] == [] and despacho["alertas"] == []


def test_pagina_sem_rodape_fica_no_documento_anterior_com_alerta():
    paginas = [_pagina(1, MEMORANDO, "111111111", "Memorando 7"), _pagina(2, "anexo sem rodapé")]
    (doc,) = parser.montar_documentos(paginas)
    assert doc["total_paginas"] == 2
    assert any(a.startswith("paginas_sem_rodape: [2]") for a in doc["alertas"])


def test_documento_sem_rodape_nao_recebe_id_inventado():
    (doc,) = parser.montar_documentos([_pagina(1, "texto sem rodapé")])
    assert doc["documento_sei_id"] is None
    assert any(a.startswith("sem_id_sei") for a in doc["alertas"])


def test_mesmo_id_em_blocos_separados_gera_alerta():
    paginas = [
        _pagina(1, MEMORANDO, "111111111", "Memorando 7"),
        _pagina(2, DESPACHO, "222222222", "Despacho"),
        _pagina(3, "volta do memorando", "111111111", "Memorando 7"),
    ]
    docs = parser.montar_documentos(paginas)
    assert len(docs) == 3
    assert sum(any(a.startswith("id_repetido") for a in d["alertas"]) for d in docs) == 2


def test_numero_nao_confirmado_gera_alerta():
    (doc,) = parser.montar_documentos(
        [_pagina(1, "ATA - UNDF/REIT\nReunião", "333333333", "Ata 1")]
    )
    assert doc["numero_documento"] is None
    assert any(a.startswith("numero_nao_confirmado") for a in doc["alertas"])


def test_jsonl_de_paginas_invalido(tmp_path):
    arquivo = tmp_path / "x.paginas.jsonl"
    arquivo.write_text(
        json.dumps(_pagina(1, "a", "1")) + "\n" + json.dumps(_pagina(3, "b", "1")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fora de ordem"):
        parser.carregar_paginas(arquivo)


def test_grava_um_documento_por_linha_sem_duplicar(tmp_path):
    entrada = tmp_path / "teste.paginas.jsonl"
    linhas = [
        _pagina(1, MEMORANDO, "111111111", "Memorando 7"),
        _pagina(2, DESPACHO, "222222222", "Despacho"),
    ]
    entrada.write_text("".join(json.dumps(p) + "\n" for p in linhas), encoding="utf-8")

    parser.processar([entrada], tmp_path)
    parser.processar([entrada], tmp_path)  # reexecução

    saida = (tmp_path / "teste.documentos.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(linha)["documento_sei_id"] for linha in saida] == ["111111111", "222222222"]


# --------------------------------------------------------------------------
# Integração com os PDFs reais (pulados se os PDFs não estiverem presentes)
# --------------------------------------------------------------------------

pymupdf = pytest.importorskip("pymupdf")

from app.ingestion import loader  # noqa: E402

PDF_2024 = loader.PASTA_RAW / "SEI_04030_00001001_2024_23 (2).pdf"
PDF_2025 = loader.PASTA_RAW / "SEI_04030_00001179_2025_55 (2).pdf"
precisa_dos_pdfs = pytest.mark.skipif(
    not (PDF_2024.exists() and PDF_2025.exists()), reason="PDFs reais não estão em app/data/raw/"
)


def _documentos(pdf):
    return parser.montar_documentos(
        [
            {**p, "arquivo_origem": pdf.name, "processo_sei": None}
            for p in loader.carregar_pdf(pdf)["paginas"]
        ]
    )


@pytest.fixture(scope="module")
def docs2024():
    return _documentos(PDF_2024)


@pytest.fixture(scope="module")
def docs2025():
    return _documentos(PDF_2025)


def _por_id(docs, doc_id):
    return next(d for d in docs if d["documento_sei_id"] == doc_id)


@precisa_dos_pdfs
def test_reais_documentos_e_paginas(docs2024, docs2025):
    for docs, total, n_docs in ((docs2024, 61, 19), (docs2025, 212, 30)):
        paginas = [p["pagina"] for d in docs for p in d["paginas"]]
        assert paginas == list(range(1, total + 1))
        assert len(docs) == n_docs
        assert all(re.fullmatch(r"\d{6,10}", d["documento_sei_id"]) for d in docs)


@precisa_dos_pdfs
def test_reais_localiza_documento_pelo_id(docs2024):
    doc = _por_id(docs2024, "142739020")
    assert doc["rotulo"] == "Memorando 131"
    assert doc["numero_documento"] == "131/2024 - UNDF/REIT/CEINTER"
    assert doc["data_documento"] == "2024-06-06"
    assert doc["unidade"] == "UNDF/REIT/CEINTER"
    assert doc["assunto"].startswith("Pedido de anuência do representante legal")
    assert (doc["pagina_inicio"], doc["pagina_fim"]) == (37, 38)


@precisa_dos_pdfs
def test_reais_documentos_com_mesmo_rotulo_separados(docs2024):
    memorandos = [d for d in docs2024 if d["rotulo"] == "Memorando 11"]
    assert {(d["numero_documento"], d["data_documento"]) for d in memorandos} == {
        ("11/2024 - UNDF/REIT/SECEX", "2024-06-07"),
        ("11/2026 - UNDF/REIT/CEINTER", "2026-02-10"),
    }


@precisa_dos_pdfs
def test_reais_assunto_em_varias_linhas(docs2025):
    assert _por_id(docs2025, "213950020")["assunto"].endswith("Extensão, com prazo.")
    assert _por_id(docs2025, "178454191")["assunto"] == (
        "proposição para criação de núcleo de inteligência artificial na UnDF"
    )


@precisa_dos_pdfs
def test_reais_despachos_sem_numero_tem_unidade(docs2025):
    despachos = [d for d in docs2025 if d["rotulo"] == "Despacho"]
    assert all(d["numero_documento"] is None for d in despachos)
    assert all(d["unidade"] and d["unidade"].startswith("UNDF/") for d in despachos)


@precisa_dos_pdfs
def test_reais_numeros_citados_nao_contaminam(docs2025):
    assert _por_id(docs2025, "213940949")["numero_documento"] is None  # Despacho CONSEPE
    numeros = [d["numero_documento"] for d in docs2025 if d["numero_documento"]]
    assert not any("500/2024" in n or "FAPDF" in n for n in numeros)


@precisa_dos_pdfs
def test_reais_texto_limpo_e_glifos(docs2024, docs2025):
    for doc in docs2024 + docs2025:
        for pag in doc["paginas"]:
            assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f�ﬀ-ﬆ]", pag["texto_limpo"])
            assert "Código Verificador" not in pag["texto_limpo"]
    edital = "\n".join(p["texto_limpo"] for p in _por_id(docs2024, "140334392")["paginas"])
    assert "Incentivar e apoiar a pesquisa científica" in edital


@precisa_dos_pdfs
def test_reais_relatorio(docs2024, docs2025):
    resultados = [
        {"arquivo_origem": "a", "processo_sei": "x", "total_paginas": 61, "documentos": docs2024},
        {"arquivo_origem": "b", "processo_sei": "y", "total_paginas": 212, "documentos": docs2025},
    ]
    relatorio = gerar_relatorio(resultados, [])
    assert relatorio["totais"]["documentos"] == 49
    for arquivo in relatorio["arquivos"]:
        assert arquivo["paginas_faltando"] == [] and arquivo["paginas_duplicadas"] == []
