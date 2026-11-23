"""RAG-01 — Ingestão: PDF do SEI -> uma linha JSONL por página.

Uso (a partir da raiz do projeto):

    python -m app.ingestion.loader                      # todos os PDFs de app/data/raw/
    python -m app.ingestion.loader caminho/arquivo.pdf  # um ou mais PDFs

Para cada PDF grava app/data/processed/<nome>.paginas.jsonl, com texto bruto,
rodapé SEI identificado e flags de qualidade de cada página. Não separa os
documentos internos: isso é feito pelo parser (RAG-02). Um PDF com problema
é registrado e não interrompe os demais; reexecutar sobrescreve a saída.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pymupdf

from app.ingestion import sei

log = logging.getLogger("ingestao.loader")

PASTA_APP = Path(__file__).resolve().parent.parent
PASTA_RAW = PASTA_APP / "data" / "raw"
PASTA_PROCESSED = PASTA_APP / "data" / "processed"
PASTA_REPORTS = PASTA_APP / "data" / "reports"

SUFIXO_PAGINAS = ".paginas.jsonl"
VERSAO_FORMATO = 3
MIN_CHARS_TEXTO = 30  # abaixo disso a página é considerada "sem_texto"


class ErroIngestao(Exception):
    """PDF que não pode ser processado (inexistente, inválido, protegido, vazio...)."""


def _cobertura_imagens(pagina: pymupdf.Page) -> float:
    area_pagina = pagina.rect.width * pagina.rect.height or 1.0
    area = 0.0
    for imagem in pagina.get_images(full=True):
        for rect in pagina.get_image_rects(imagem[0]):
            rect = rect & pagina.rect  # ignora o que estiver fora da página
            area += rect.width * rect.height
    return min(area / area_pagina, 1.0)


def _ler_pagina(pagina: pymupdf.Page, numero: int) -> dict:
    """Texto bruto, rodapé SEI e cobertura de imagens de uma página."""
    registro = {
        "pagina": numero,
        "texto": "",
        "rodape": None,
        "cobertura_imagens": 0.0,
        "erro": None,
        "flags": [],
    }
    try:
        registro["texto"] = pagina.get_text("text")
    except Exception as exc:  # página corrompida não derruba o PDF
        registro["erro"] = f"{type(exc).__name__}: {exc}"
        registro["flags"].append("erro_extracao")
        log.warning("Falha ao extrair texto da página %s: %s", numero, exc)
        return registro

    rodape = sei.extrair_rodape(registro["texto"])
    registro["rodape"] = asdict(rodape) if rodape else None
    try:
        registro["cobertura_imagens"] = round(_cobertura_imagens(pagina), 3)
    except Exception as exc:
        log.debug("Não foi possível medir imagens da página %s: %s", numero, exc)

    if len(registro["texto"].strip()) < MIN_CHARS_TEXTO:
        registro["flags"].append("sem_texto")
    if rodape is None:
        registro["flags"].append("sem_rodape")
    elif rodape.pagina != numero:
        registro["flags"].append("rodape_pagina_divergente")
    return registro


def carregar_pdf(caminho_pdf: Path) -> dict:
    """Lê um PDF do SEI e devolve o processo e a lista de páginas."""
    caminho_pdf = Path(caminho_pdf)
    if not caminho_pdf.is_file():
        raise ErroIngestao(f"arquivo não encontrado: {caminho_pdf}")
    try:
        documento = pymupdf.open(caminho_pdf)
    except Exception as exc:
        raise ErroIngestao(f"não foi possível abrir o PDF: {type(exc).__name__}: {exc}") from exc

    with documento:
        if documento.needs_pass:
            raise ErroIngestao("PDF protegido por senha")
        if documento.page_count == 0:
            raise ErroIngestao("PDF sem páginas")
        paginas = [_ler_pagina(pagina, n) for n, pagina in enumerate(documento, start=1)]

    # Processo: maioria dos rodapés, conferida com o nome do arquivo.
    processos = Counter(p["rodape"]["processo_sei"] for p in paginas if p["rodape"])
    processo_nome = sei.processo_do_nome_arquivo(caminho_pdf.name)
    processo = processos.most_common(1)[0][0] if processos else processo_nome
    avisos = []
    if len(processos) > 1:
        avisos.append(f"rodapés citam mais de um processo: {sorted(processos)}")
    if processo_nome and processo and processo_nome != processo:
        avisos.append(f"nome do arquivo indica {processo_nome}, rodapés indicam {processo}")
    if processo is None:
        avisos.append("processo não identificado (sem rodapé SEI e nome fora do padrão)")

    return {
        "arquivo_origem": caminho_pdf.name,
        "processo_sei": processo,
        "total_paginas": len(paginas),
        "avisos": avisos,
        "paginas": paginas,
    }


def salvar_paginas_jsonl(resultado: dict, pasta_saida: Path = PASTA_PROCESSED) -> Path:
    """Grava uma linha por página. Sobrescreve a saída anterior (sem duplicar)."""
    pasta_saida.mkdir(parents=True, exist_ok=True)
    caminho = pasta_saida / (Path(resultado["arquivo_origem"]).stem + SUFIXO_PAGINAS)
    temporario = caminho.with_suffix(".tmp")
    with open(temporario, "w", encoding="utf-8") as arquivo:
        for pagina in resultado["paginas"]:
            registro = {
                "versao_formato": VERSAO_FORMATO,
                "arquivo_origem": resultado["arquivo_origem"],
                "processo_sei": resultado["processo_sei"],
                "total_paginas": resultado["total_paginas"],
                **pagina,
            }
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    temporario.replace(caminho)  # troca atômica: nunca deixa um arquivo pela metade
    return caminho


def processar(
    pdfs: list[Path], pasta_saida: Path = PASTA_PROCESSED
) -> tuple[list[dict], list[dict]]:
    """Processa uma lista de PDFs. Devolve (resultados, erros)."""
    resultados, erros = [], []
    for pdf in pdfs:
        try:
            resultado = carregar_pdf(pdf)
            saida = salvar_paginas_jsonl(resultado, pasta_saida)
        except Exception as exc:
            log.error("%s: %s", Path(pdf).name, exc)
            erros.append({"arquivo": Path(pdf).name, "erro": str(exc), "tipo": type(exc).__name__})
            continue
        resultado["saida"] = str(saida)
        resultados.append(resultado)
        for aviso in resultado["avisos"]:
            log.warning("%s: %s", pdf.name, aviso)
        log.info("%s: %d páginas -> %s", pdf.name, resultado["total_paginas"], saida.name)
    return resultados, erros


def resumo(resultados: list[dict], erros: list[dict]) -> dict:
    """Resumo da execução: páginas processadas e problemas encontrados."""
    arquivos = []
    for r in resultados:
        por_flag: dict[str, list[int]] = {}
        for p in r["paginas"]:
            for flag in p["flags"]:
                por_flag.setdefault(flag, []).append(p["pagina"])
        arquivos.append(
            {
                "arquivo": r["arquivo_origem"],
                "processo_sei": r["processo_sei"],
                "total_paginas": r["total_paginas"],
                "saida": r["saida"],
                "paginas_por_flag": por_flag,
                "avisos": r["avisos"],
            }
        )
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "pdfs_processados": len(resultados),
        "pdfs_com_erro": len(erros),
        "paginas": sum(r["total_paginas"] for r in resultados),
        "arquivos": arquivos,
        "erros": erros,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG-01: PDFs do SEI -> páginas em JSONL")
    parser.add_argument("pdfs", nargs="*", type=Path, help="PDFs (padrão: app/data/raw/*.pdf)")
    parser.add_argument("--saida", type=Path, default=PASTA_PROCESSED, help="pasta de saída")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    pdfs = args.pdfs or sorted(PASTA_RAW.glob("*.pdf"))
    if not pdfs:
        log.warning("Nenhum PDF informado ou encontrado em %s", PASTA_RAW)
    resultados, erros = processar(pdfs, args.saida)

    dados = resumo(resultados, erros)
    PASTA_REPORTS.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_REPORTS / "relatorio_loader.json"
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"\nRAG-01: {dados['pdfs_processados']} PDF(s), {dados['paginas']} páginas, "
        f"{dados['pdfs_com_erro']} PDF(s) com erro. Resumo em {caminho}"
    )
    for a in dados["arquivos"]:
        flags = ", ".join(f"{f}: {len(p)}" for f, p in a["paginas_por_flag"].items()) or "nenhuma"
        print(f"  {a['arquivo']}: {a['total_paginas']} páginas | flags: {flags}")
    for e in erros:
        print(f"  ERRO {e['arquivo']}: {e['erro']}")
    return 1 if erros and not resultados else 0


if __name__ == "__main__":
    raise SystemExit(main())
