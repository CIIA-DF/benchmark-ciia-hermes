import json
import re
from pathlib import Path 

import pymupdf as fitz

PADRONIZAR_PROCESSO = PADRAO_PROCESSO = re.compile(
    r"(?:[A-ZÀ-Ú][\wÀ-ÿ]*\s+){1,3}[Nn][º°o.]?\s*(\d+/\d{4})\s*-\s*([A-Z][A-Z/]+)"
) #expressão regular para padronizar o número do processo

PASTA_APP = Path(__file__).resolve().parent.parent
PASTA_RAW = PASTA_APP / "data" / "raw"
PASTA_PROCESSED = PASTA_APP / "data" / "processed"

def extrair_processo(texto: str) -> str | None:
    """
    Extrai o número do processo de um texto usando a expressão regular definida.
    """
    encontrado = PADRONIZAR_PROCESSO.search(texto)
    if encontrado:
        return f"{encontrado.group(1)} - {encontrado.group(2)}"
    return None

def carregar_pdf(caminho_pdf: Path) -> list[dict]:
    """Lê um PDF  e devolve um registro por página."""
    registros = []
    processo_atual = None

    with fitz.open(caminho_pdf) as documento:
        for num_pag, pagina in enumerate(documento, start=1):
            #  recorta  somente a parte ded cima da página para procurar o processo
            texto_pagina = pagina.get_text("text")

            # se não tiver número do processo na página, usa o último encontrado
            processo = extrair_processo(texto_pagina)
            if processo:
                processo_atual = processo
                
            registros.append({
                "processo": processo_atual,
                "arquivo_origem": caminho_pdf.name,
                "pagina": num_pag,
                "texto": texto_pagina,
            })
        
    return registros
        
def salvar_json(registros: list[dict], nome_saida: Path) -> Path: 
    # salva os  registros em data/processed/ e devolve o caminho do arquivo

    PASTA_PROCESSED.mkdir(parents=True, exist_ok=True)
    caminho_saida = PASTA_PROCESSED / nome_saida
    with open(caminho_saida, "w", encoding="utf-8") as arquivo:
        json.dump(registros, arquivo, ensure_ascii=False, indent=2)
    return caminho_saida

if __name__ == "__main__":
    pdfs = sorted(PASTA_RAW.glob("*.pdf"))

    if not pdfs:
        print(f"Nenhum PDF encontrado em {PASTA_RAW}")

    for pdf in pdfs:
        registros = carregar_pdf(pdf)
        saida = salvar_json(registros, pdf.stem + ".json")
        print(f"{pdf.name}: {len(registros)} páginas processadas -> {saida}")
