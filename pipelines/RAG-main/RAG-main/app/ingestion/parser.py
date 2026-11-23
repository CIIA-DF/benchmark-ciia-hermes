"""RAG-02 — Parsing: páginas (JSONL do loader) -> documentos SEI (JSONL).

Uso (a partir da raiz do projeto, depois do loader):

    python -m app.ingestion.parser                                   # todos os *.paginas.jsonl
    python -m app.ingestion.parser app/data/processed/X.paginas.jsonl

Para cada processo grava app/data/processed/<nome>.documentos.jsonl, com um
documento SEI por linha: ID SEI, tipo, número, assunto, data, unidade,
intervalo de páginas e o texto de cada página (bruto e limpo). Casos
incertos ficam em "alertas" para revisão; nenhum ID ou metadado é inventado.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from app.ingestion import sei
from app.ingestion.diagnostic import gerar_relatorio, imprimir_resumo, salvar_relatorio
from app.ingestion.loader import PASTA_PROCESSED, PASTA_REPORTS, SUFIXO_PAGINAS

log = logging.getLogger("ingestao.parser")

SUFIXO_DOCUMENTOS = ".documentos.jsonl"
VERSAO_FORMATO = 3

# Limiares das flags de qualidade do texto limpo
MIN_CHARS_CONTEUDO = 200  # abaixo disso a página tem "pouco_texto"
MIN_COBERTURA_IMAGEM = 0.5  # fração da página coberta por imagens


# --------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------


def carregar_paginas(caminho_jsonl: Path) -> list[dict]:
    """Lê o JSONL do loader, validando ordem e unicidade das páginas."""
    paginas = []
    with open(caminho_jsonl, encoding="utf-8") as arquivo:
        for numero_linha, linha in enumerate(arquivo, start=1):
            if not linha.strip():
                continue
            try:
                paginas.append(json.loads(linha))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{caminho_jsonl.name}, linha {numero_linha}: {exc}") from exc
    if not paginas:
        raise ValueError(f"{caminho_jsonl.name}: arquivo sem páginas")
    numeros = [p["pagina"] for p in paginas]
    if numeros != list(range(1, len(numeros) + 1)):
        raise ValueError(f"{caminho_jsonl.name}: páginas fora de ordem, faltando ou repetidas")
    return paginas


# --------------------------------------------------------------------------
# Montagem dos documentos
# --------------------------------------------------------------------------


def _flags_texto(pagina: dict, limpo: sei.TextoLimpo) -> list[str]:
    flags = list(pagina.get("flags", []))
    if limpo.glifos_reparados:
        flags.append("glifos_reparados")
    if limpo.glifos_desconhecidos:
        flags.append("glifos_desconhecidos")
    n = len(limpo.texto)
    if n == 0:
        flags.append("sem_conteudo")
    elif n < MIN_CHARS_CONTEUDO:
        flags.append("pouco_texto")
    if pagina.get("cobertura_imagens", 0.0) >= MIN_COBERTURA_IMAGEM:
        flags.append("imagem_dominante")
        if n < MIN_CHARS_CONTEUDO:
            flags.append("candidata_ocr")
    return flags


def _novo_documento(pagina: dict) -> dict:
    rodape = pagina.get("rodape")
    rotulo = rodape["rotulo"] if rodape else None
    return {
        "versao_formato": VERSAO_FORMATO,
        "processo_sei": pagina.get("processo_sei"),
        "arquivo_origem": pagina.get("arquivo_origem"),
        "documento_sei_id": rodape["documento_sei_id"] if rodape else None,
        "rotulo": rotulo,
        "tipo_documento": sei.tipo_do_rotulo(rotulo) if rotulo else None,
        "numero_documento": None,
        "assunto": None,
        "data_documento": None,
        "data_assinatura": None,
        "unidade": None,
        "pagina_inicio": pagina["pagina"],
        "pagina_fim": pagina["pagina"],
        "total_paginas": 0,
        "alertas": [],
        "paginas": [],
    }


def _extrair_metadados(doc: dict) -> None:
    primeira = doc["paginas"][0]["texto_bruto"]
    texto_completo = "\n".join(p["texto_bruto"] for p in doc["paginas"])
    doc["numero_documento"] = sei.extrair_numero_documento(primeira, doc["rotulo"])
    doc["assunto"] = sei.extrair_assunto(primeira)
    doc["data_documento"] = sei.extrair_data(primeira)
    doc["data_assinatura"] = sei.extrair_data_assinatura(texto_completo)
    doc["unidade"] = sei.extrair_unidade(primeira, doc["numero_documento"])


def _alertas(doc: dict) -> list[str]:
    """Casos que merecem revisão humana (a especificação pede registrá-los)."""
    alertas = []
    if not doc["documento_sei_id"]:
        alertas.append("sem_id_sei: nenhuma página do documento tem rodapé SEI")
    sem_rodape = [p["pagina"] for p in doc["paginas"] if "sem_rodape" in p["flags"]]
    if doc["documento_sei_id"] and sem_rodape:
        alertas.append(f"paginas_sem_rodape: {sem_rodape} atribuídas ao documento anterior")
    esperado = sei.numero_do_rotulo(doc["rotulo"]) if doc["rotulo"] else None
    if esperado and not doc["numero_documento"]:
        alertas.append(f"numero_nao_confirmado: rótulo indica {esperado}, cabeçalho não confirma")
    return alertas


def montar_documentos(paginas: list[dict]) -> list[dict]:
    """Agrupa páginas consecutivas com o mesmo ID de documento SEI.

    Página sem rodapé fica no documento anterior (com flag e alerta);
    nenhuma página é descartada e nenhum ID é inventado.
    """
    documentos: list[dict] = []
    atual: dict | None = None
    for pagina in paginas:
        rodape = pagina.get("rodape")
        if atual is None or (rodape and rodape["documento_sei_id"] != atual["documento_sei_id"]):
            atual = _novo_documento(pagina)
            documentos.append(atual)
        elif rodape and atual["documento_sei_id"] is None:
            # documento aberto por página sem rodapé: adota o primeiro rodapé visto
            novo = _novo_documento(pagina)
            for chave in ("documento_sei_id", "rotulo", "tipo_documento"):
                atual[chave] = novo[chave]

        limpo = sei.limpar_texto(pagina["texto"], atual["documento_sei_id"])
        atual["paginas"].append(
            {
                "pagina": pagina["pagina"],
                "pagina_no_documento": len(atual["paginas"]) + 1,
                "texto_bruto": pagina["texto"],
                "texto_limpo": limpo.texto,
                "flags": _flags_texto(pagina, limpo),
                "cobertura_imagens": pagina.get("cobertura_imagens", 0.0),
            }
        )
        atual["pagina_fim"] = pagina["pagina"]

    repetidos = Counter(d["documento_sei_id"] for d in documentos if d["documento_sei_id"])
    for doc in documentos:
        doc["total_paginas"] = len(doc["paginas"])
        _extrair_metadados(doc)
        doc["alertas"] = _alertas(doc)
        if repetidos[doc["documento_sei_id"]] > 1:
            doc["alertas"].append("id_repetido: o mesmo documento aparece em blocos separados")
    return documentos


def processar_arquivo(caminho_paginas: Path) -> dict:
    """Páginas de um processo -> resultado com os documentos identificados."""
    paginas = carregar_paginas(caminho_paginas)
    primeira = paginas[0]
    return {
        "arquivo_origem": primeira.get("arquivo_origem"),
        "processo_sei": primeira.get("processo_sei"),
        "total_paginas": len(paginas),
        "documentos": montar_documentos(paginas),
    }


# --------------------------------------------------------------------------
# Saída e execução
# --------------------------------------------------------------------------


def salvar_documentos_jsonl(resultado: dict, pasta_saida: Path = PASTA_PROCESSED) -> Path:
    """Grava um documento por linha. Sobrescreve a saída anterior (sem duplicar)."""
    pasta_saida.mkdir(parents=True, exist_ok=True)
    caminho = pasta_saida / (Path(resultado["arquivo_origem"]).stem + SUFIXO_DOCUMENTOS)
    temporario = caminho.with_suffix(".tmp")
    with open(temporario, "w", encoding="utf-8") as arquivo:
        for doc in resultado["documentos"]:
            arquivo.write(json.dumps(doc, ensure_ascii=False) + "\n")
    temporario.replace(caminho)
    return caminho


def processar(
    arquivos: list[Path], pasta_saida: Path = PASTA_PROCESSED
) -> tuple[list[dict], list[dict]]:
    """Processa vários JSONL de páginas. Devolve (resultados, erros)."""
    resultados, erros = [], []
    for caminho in arquivos:
        try:
            resultado = processar_arquivo(caminho)
            saida = salvar_documentos_jsonl(resultado, pasta_saida)
        except Exception as exc:
            log.error("%s: %s", Path(caminho).name, exc)
            erros.append(
                {"arquivo": Path(caminho).name, "erro": str(exc), "tipo": type(exc).__name__}
            )
            continue
        resultados.append(resultado)
        log.info("%s: %d documentos -> %s", caminho.name, len(resultado["documentos"]), saida.name)
    return resultados, erros


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG-02: páginas JSONL -> documentos SEI JSONL")
    parser.add_argument(
        "arquivos", nargs="*", type=Path, help=f"*{SUFIXO_PAGINAS} (padrão: app/data/processed/)"
    )
    parser.add_argument("--saida", type=Path, default=PASTA_PROCESSED, help="pasta de saída")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    arquivos = args.arquivos or sorted(PASTA_PROCESSED.glob(f"*{SUFIXO_PAGINAS}"))
    if not arquivos:
        log.warning(
            "Nenhum %s encontrado. Rode antes: python -m app.ingestion.loader", SUFIXO_PAGINAS
        )
    resultados, erros = processar(arquivos, args.saida)

    relatorio = gerar_relatorio(resultados, erros)
    caminho = salvar_relatorio(relatorio, PASTA_REPORTS)
    imprimir_resumo(relatorio)
    print(f"\nRelatório salvo em {caminho}")
    return 1 if erros and not resultados else 0


if __name__ == "__main__":
    raise SystemExit(main())
