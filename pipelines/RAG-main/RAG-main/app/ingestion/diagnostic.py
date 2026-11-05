# ingestion/diagnostico.py
from pathlib import Path
import re
import pymupdf

PDF = Path("data/raw/SEI_04030_00001179_2025_55 (2).pdf")
termos = re.compile(r"memorando|processo|SEI\s*n|ofício|oficio|177/2025", re.IGNORECASE)

with pymupdf.open(PDF) as documento:
    for numero, pagina in enumerate(documento, start=1):
        texto = pagina.get_text("text")
        for linha in texto.splitlines():
            if termos.search(linha):
                print(f"página {numero}: {linha.strip()}")