"""Relatório de qualidade da ingestão e do parsing.

Gerado automaticamente ao fim de `python -m app.ingestion.parser`, ou
refeito a partir dos *.documentos.jsonl já gravados com:

    python -m app.ingestion.diagnostic
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

PASTA_APP = Path(__file__).resolve().parent.parent
PASTA_PROCESSED = PASTA_APP / "data" / "processed"
PASTA_REPORTS = PASTA_APP / "data" / "reports"

# Flags que indicam possível perda de informação (as demais são informativas).
FLAGS_ALERTA = {
    "erro_extracao",
    "sem_rodape",
    "rodape_pagina_divergente",
    "glifos_desconhecidos",
    "candidata_ocr",
}
METADADOS = ("numero_documento", "assunto", "data_documento", "data_assinatura", "unidade")


def _relatorio_arquivo(resultado: dict) -> dict:
    paginas_por_flag: dict[str, list[int]] = defaultdict(list)
    registradas: list[int] = []
    documentos = []
    for doc in resultado["documentos"]:
        for pag in doc["paginas"]:
            registradas.append(pag["pagina"])
            for flag in pag["flags"]:
                paginas_por_flag[flag].append(pag["pagina"])
        documentos.append(
            {
                "documento_sei_id": doc["documento_sei_id"],
                "rotulo": doc["rotulo"],
                "tipo_documento": doc["tipo_documento"],
                **{campo: doc.get(campo) for campo in METADADOS},
                "paginas": f"{doc['pagina_inicio']}-{doc['pagina_fim']}",
                "total_paginas": len(doc["paginas"]),
                "caracteres": sum(len(p["texto_limpo"]) for p in doc["paginas"]),
                "alertas": doc.get("alertas", []),
            }
        )

    esperadas = set(range(1, resultado["total_paginas"] + 1))
    contagem = Counter(registradas)
    total = len(documentos)
    cobertura = {campo: sum(1 for d in documentos if d[campo]) for campo in METADADOS}

    return {
        "arquivo": resultado["arquivo_origem"],
        "processo_sei": resultado["processo_sei"],
        "total_paginas": resultado["total_paginas"],
        "paginas_registradas": len(registradas),
        "paginas_faltando": sorted(esperadas - set(registradas)),
        "paginas_duplicadas": sorted(p for p, n in contagem.items() if n > 1),
        "total_documentos": total,
        "cobertura_metadados": {c: f"{n}/{total}" for c, n in cobertura.items()},
        "documentos_com_alerta": sum(1 for d in documentos if d["alertas"]),
        "paginas_por_flag": {f: sorted(p) for f, p in sorted(paginas_por_flag.items())},
        "documentos": documentos,
    }


def gerar_relatorio(resultados: list[dict], erros: list[dict]) -> dict:
    arquivos = [_relatorio_arquivo(r) for r in resultados]
    alertas = []
    for a in arquivos:
        if a["paginas_faltando"]:
            alertas.append(f"{a['arquivo']}: páginas faltando {a['paginas_faltando']}")
        if a["paginas_duplicadas"]:
            alertas.append(f"{a['arquivo']}: páginas duplicadas {a['paginas_duplicadas']}")
        for flag in sorted(FLAGS_ALERTA & a["paginas_por_flag"].keys()):
            alertas.append(f"{a['arquivo']}: {flag} nas páginas {a['paginas_por_flag'][flag]}")
        for d in a["documentos"]:
            for alerta in d["alertas"]:
                alertas.append(f"{a['arquivo']}: {d['rotulo']} ({d['documento_sei_id']}): {alerta}")
    alertas.extend(f"{e['arquivo']}: ERRO {e['erro']}" for e in erros)

    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "totais": {
            "arquivos_processados": len(arquivos),
            "arquivos_com_erro": len(erros),
            "paginas": sum(a["total_paginas"] for a in arquivos),
            "documentos": sum(a["total_documentos"] for a in arquivos),
        },
        "alertas": alertas,
        "erros": erros,
        "arquivos": arquivos,
    }


def salvar_relatorio(relatorio: dict, pasta: Path = PASTA_REPORTS) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / "relatorio_ingestao.json"
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(relatorio, arquivo, ensure_ascii=False, indent=2)
    return caminho


def imprimir_resumo(relatorio: dict) -> None:
    t = relatorio["totais"]
    print(
        f"\n=== {t['arquivos_processados']} processo(s), {t['paginas']} páginas, "
        f"{t['documentos']} documentos, {t['arquivos_com_erro']} arquivo(s) com erro ==="
    )
    for a in relatorio["arquivos"]:
        print(f"\n{a['arquivo']}  [processo {a['processo_sei']}]")
        paginas = f"{a['paginas_registradas']}/{a['total_paginas']}"
        print(f"  páginas: {paginas}   documentos: {a['total_documentos']}")
        cobertura = ", ".join(f"{c}: {n}" for c, n in a["cobertura_metadados"].items())
        print(f"  metadados encontrados: {cobertura}")
        for d in a["documentos"]:
            doc_id = d["documento_sei_id"] or "?"
            rotulo = (d["rotulo"] or "?")[:30]
            data = d["data_documento"] or d["data_assinatura"] or "-"
            unidade = d["unidade"] or "-"
            print(f"    p{d['paginas']:>9}  {doc_id:>10}  {rotulo:30}  {data:10}  {unidade}")
    if relatorio["alertas"]:
        print("\nALERTAS (para revisão):")
        for alerta in relatorio["alertas"]:
            print(f"  - {alerta}")
    else:
        print("\nNenhum alerta.")


def main() -> None:
    from app.ingestion.parser import SUFIXO_DOCUMENTOS

    resultados = []
    for caminho in sorted(PASTA_PROCESSED.glob(f"*{SUFIXO_DOCUMENTOS}")):
        with open(caminho, encoding="utf-8") as arquivo:
            documentos = [json.loads(linha) for linha in arquivo if linha.strip()]
        if not documentos:
            continue
        resultados.append(
            {
                "arquivo_origem": documentos[0]["arquivo_origem"],
                "processo_sei": documentos[0]["processo_sei"],
                "total_paginas": max(d["pagina_fim"] for d in documentos),
                "documentos": documentos,
            }
        )
    relatorio = gerar_relatorio(resultados, [])
    caminho = salvar_relatorio(relatorio)
    imprimir_resumo(relatorio)
    print(f"\nRelatório salvo em {caminho}")


if __name__ == "__main__":
    main()
