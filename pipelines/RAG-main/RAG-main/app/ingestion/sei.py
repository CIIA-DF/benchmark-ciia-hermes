"""Regras de interpretação de PDFs exportados do SEI-GDF.

Funções puras (sem dependência do PyMuPDF), para poderem ser testadas com
strings simples.

Todo PDF de processo exportado pelo SEI traz, no fim de cada página, um
rodapé padronizado:

    Memorando 131 (142739020)         SEI 04030-00001001/2024-23 / pg. 38
    Despacho 140494121                SEI 04030-00001001/2024-23 / pg. 36

Esse rodapé é a fonte confiável de: rótulo do documento, ID do documento no
SEI, número do processo e página. O número oficial do documento
(ex.: "98/2024 - UNDF/REIT/CEINTER") só aparece no cabeçalho da primeira
página de cada documento.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Rodapé
# --------------------------------------------------------------------------

RODAPE = re.compile(
    r"(?P<rotulo>[^\n]*?)\s*\(?(?P<documento_sei_id>\d{6,10})\)?"
    r"[ \t]+SEI[ \t]+(?P<processo_sei>\d{5}-\d{8}/\d{4}-\d{2})"
    r"[ \t]*/[ \t]*pg\.[ \t]*(?P<pagina>\d+)[ \t]*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Rodape:
    rotulo: str
    documento_sei_id: str
    processo_sei: str
    pagina: int


def extrair_rodape(texto: str) -> Rodape | None:
    """Devolve o rodapé SEI da página (a última ocorrência), ou None."""
    ocorrencias = list(RODAPE.finditer(texto))
    if not ocorrencias:
        return None
    m = ocorrencias[-1]
    return Rodape(
        rotulo=re.sub(r"\s+", " ", m["rotulo"]).strip(),
        documento_sei_id=m["documento_sei_id"],
        processo_sei=m["processo_sei"],
        pagina=int(m["pagina"]),
    )


# --------------------------------------------------------------------------
# Tipo de documento (a partir do rótulo do rodapé)
# --------------------------------------------------------------------------

# Ordem importa: prefixos mais longos antes dos mais curtos.
TIPOS_CONHECIDOS = [
    "Termo de Aceite",
    "Termo de Outorga",
    "Termo",
    "Nota Jurídica",
    "Nota Técnica",
    "Declaração Simples",
    "Declaração",
    "Regimento Interno",
    "Regimento",
    "Relatório",
    "Memorando",
    "Ofício",
    "Despacho",
    "Edital",
    "Projeto",
    "Ata",
    "E-mail",
    "Apresentação",
    "Decreto",
    "Instrução",
    "Portaria",
    "Convênio",
    "Justificativa",
    "Parecer",
    "Anexo",
]


def tipo_do_rotulo(rotulo: str) -> str | None:
    """'Memorando 131' -> 'Memorando'; 'Despacho CONSEPE' -> 'Despacho'."""
    for tipo in TIPOS_CONHECIDOS:
        if re.match(rf"{re.escape(tipo)}\b", rotulo, re.IGNORECASE):
            return tipo
    # Fallback: rótulo sem o número final ("Circular 3" -> "Circular").
    base = re.sub(r"\s*\d[\w./-]*$", "", rotulo).strip()
    return base or None


def numero_do_rotulo(rotulo: str) -> str | None:
    """'Memorando 131' -> '131'; 'Termo de Aceite 19' -> '19'.

    Só vale quando o rótulo é "<palavras> <número>": em "Decreto n. 44.969,
    de 19/09/2023" o número final é um ano, não o número do documento.
    """
    m = re.fullmatch(r"\D+\s(\d+)", rotulo)
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# Número oficial do documento (cabeçalho da 1ª página)
# --------------------------------------------------------------------------

# Como cada tipo de documento se apresenta no cabeçalho. Só procuramos o
# número com o MESMO tipo do documento: um despacho que cita "Memorando
# 131/2024" no assunto não pode herdar esse número.
TIPO_NO_CABECALHO = {
    "Memorando": r"memorando",
    "Ofício": r"of[ií]cio",
    "Despacho": r"despacho",
    "Termo de Aceite": r"termo\s+de\s+aceite",
    "Nota Jurídica": r"nota\s+jur[ií]dica",
    "Nota Técnica": r"nota\s+t[eé]cnica",
    "Edital": r"edital|chamada\s+p[uú]blica",
    "Ata": r"ata",
    "Portaria": r"portaria",
    "Parecer": r"parecer",
    "Instrução": r"instru[cç][aã]o",
    "Decreto": r"decreto",
    "Circular": r"circular",
}

NUMERO_CABECALHO = (
    r"\s*(?:[Nn]\.?\s*[º°oO]?\s*\.?\s*º?\s*)?"
    r"(?P<numero>\d{1,5}/\d{4})"
    r"(?:[ \t]*-[ \t]*(?P<sigla>[A-Z][A-Z0-9/\-]*[A-Z0-9]))?"
)

LINHAS_CABECALHO = 20


def extrair_numero_documento(texto_primeira_pagina: str, rotulo: str | None) -> str | None:
    """Número oficial do documento, procurado só no cabeçalho.

    - Só nas primeiras linhas, para não capturar números citados no corpo
      (ex.: "Termo de Outorga 500/2024" mencionado num despacho).
    - Só com o mesmo tipo do documento (vem do rótulo do rodapé).
    - Se o rótulo tiver número ("Memorando 131"), o número do cabeçalho
      precisa coincidir; caso contrário, é descartado.
    """
    if not rotulo:
        return None
    tipo = tipo_do_rotulo(rotulo)
    padrao_tipo = TIPO_NO_CABECALHO.get(tipo or "")
    if not padrao_tipo:
        return None
    regex = re.compile(rf"\b(?i:{padrao_tipo}){NUMERO_CABECALHO}")
    cabecalho = "\n".join(texto_primeira_pagina.splitlines()[:LINHAS_CABECALHO])
    esperado = numero_do_rotulo(rotulo)
    for m in regex.finditer(cabecalho):
        numero = m["numero"]
        if esperado and numero.split("/")[0].lstrip("0") != esperado.lstrip("0"):
            continue
        return f"{numero} - {m['sigla']}" if m["sigla"] else numero
    return None


# --------------------------------------------------------------------------
# Processo a partir do nome do arquivo
# --------------------------------------------------------------------------

NOME_ARQUIVO = re.compile(r"SEI_(\d{5})_(\d{8})_(\d{4})_(\d{2})")


def processo_do_nome_arquivo(nome: str) -> str | None:
    """'SEI_04030_00001001_2024_23 (2).pdf' -> '04030-00001001/2024-23'."""
    m = NOME_ARQUIVO.search(nome)
    if not m:
        return None
    return f"{m[1]}-{m[2]}/{m[3]}-{m[4]}"


# --------------------------------------------------------------------------
# Limpeza de texto
# --------------------------------------------------------------------------

# Glifos sem mapeamento Unicode viram caracteres de controle (\x01, \x02...)
# na extração: o PyMuPDF usa o ID do glifo no lugar do caractere. Os IDs são
# próprios da fonte embutida em cada documento, então o reparo é cadastrado
# por documento, depois de conferido manualmente.
REPAROS_GLIFOS: dict[str, dict[str, str]] = {
    # Edital FAPDF (Chamada Pública 53/2024), fonte Calibri com ligaduras.
    # Conferido em "Incen\x01var", "cien\x02ﬁca", "h\x03p://", "\x04sico-ﬁnanceiro", "h\x05ps://".
    "140334392": {"\x01": "ti", "\x02": "tí", "\x03": "tt", "\x04": "fí", "\x05": "tt"},
}

CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]")
LIGADURAS = re.compile(r"[\ufb00-\ufb06]")
SUBSTITUICOES = {
    "\u200b": "",  # zero-width space
    "\u00ad": "",  # hífen condicional
    "\u00a0": " ",  # espaço inseparável
    "\uf0b7": "•",  # marcador de lista (área de uso privado, fonte Symbol)
    "\u0336": "-",  # traço combinante em "Despacho ̶ UNDF/REIT"
}

# Linhas que são apenas "moldura" do SEI e não carregam conteúdo.
LINHAS_BOILERPLATE = [
    re.compile(p)
    for p in (
        RODAPE.pattern,
        r"^A auten\w*cidade do documento pode ser conferida",
        r"^https?://sei\.df\.gov\.br/?(?:sei/controlador_externo\.php\?.*)?$",
        r"^/?sei/controlador_externo\.php\?",
        r"^acao=documento_conferir",
        r"^C[óo]digo Verificador:",
        r"^veri\w*cador\s*=",
        r'^"Bras[ií]lia - Patrim[ôo]nio Cultural da Humanidade"$',
        r"^.*\bCEP\s*[\d.\-]+\s*-\s*DF$",
        r"^Telefone\(s\):",
        r"^S[ií]\w*o\s+-\s+\S+$",
        r"^\d{5}-\d{8}/\d{4}-\d{2}$",
        r"^Doc\. SEI/GDF \d+$",
        # Artefatos de "imprimir para PDF" do navegador (ex.: edital da FAPDF)
        r"^SEI/GDF - \d+ - ",
        r"^https?://sei\.df\.gov\.br/sei/controlador\.php\?acao=documento_imprimir",
        r"^\d+ of \d+$",
        r"^\d{2}/\d{2}/\d{4}, \d{2}:\d{2}$",
    )
]


@dataclass
class TextoLimpo:
    texto: str
    glifos_reparados: int = 0
    glifos_desconhecidos: int = 0


def limpar_texto(texto: str, documento_sei_id: str | None = None) -> TextoLimpo:
    """Normaliza o texto de uma página e remove a moldura do SEI.

    Mantém as assinaturas ("Documento assinado eletronicamente por ..."),
    que são conteúdo útil (quem assinou e quando).
    """
    reparados = 0
    for glifo, troca in REPAROS_GLIFOS.get(documento_sei_id or "", {}).items():
        reparados += texto.count(glifo)
        texto = texto.replace(glifo, troca)

    desconhecidos = len(CONTROLE.findall(texto))
    texto = CONTROLE.sub("", texto)

    texto = LIGADURAS.sub(lambda m: unicodedata.normalize("NFKC", m.group()), texto)
    for antigo, novo in SUBSTITUICOES.items():
        texto = texto.replace(antigo, novo)

    linhas = []
    for linha in texto.splitlines():
        linha = linha.rstrip()
        conteudo = linha.strip()
        if conteudo and any(p.search(conteudo) for p in LINHAS_BOILERPLATE):
            continue
        linhas.append(linha)

    limpo = "\n".join(linhas)
    limpo = re.sub(r"[ \t]+\n", "\n", limpo)
    limpo = re.sub(r"\n{3,}", "\n\n", limpo).strip()
    return TextoLimpo(limpo, reparados, desconhecidos)


# --------------------------------------------------------------------------
# Metadados do documento (RAG-02): assunto, data e unidade
# --------------------------------------------------------------------------


def _linhas_nao_vazias(texto: str, limite: int) -> list[str]:
    linhas = [linha.strip() for linha in texto.replace("̶", "-").splitlines()]
    return [linha for linha in linhas if linha][:limite]


LINHAS_ASSUNTO = 40
MAX_LINHAS_EXTRAS_ASSUNTO = 5
PARAGRAFO_NUMERADO = re.compile(r"^\d+(\.\d+)*\.?$|^\d+\.\s")
COMECA_CONTINUACAO = re.compile(r"^[a-zà-ú(\-–]")
TERMINA_EM_CONECTIVO = re.compile(
    r"\b(e|ou|de|da|do|das|dos|a|à|às|ao|aos|o|os|para|com|em|no|na|nos|nas|por|sobre)$|[-–]$"
)


def _assunto_continua(acumulado: str, proxima: str) -> bool:
    """Decide se a próxima linha ainda faz parte do assunto (que pode quebrar)."""
    if PARAGRAFO_NUMERADO.match(proxima):
        return False
    if acumulado.count('"') % 2 == 1 or acumulado.count("“") > acumulado.count("”"):
        return True  # aspas abertas: o assunto ainda não terminou
    if TERMINA_EM_CONECTIVO.search(acumulado):
        return True  # "... às Pró-Reitorias de Pesquisa e" + próxima linha
    if COMECA_CONTINUACAO.match(proxima):
        return True  # "(NIAUnDF)", "- Instrução complementar", "aprovação de ..."
    # Uma palavra solta ("NIAUnDF", "PRODRS.") costuma ser o fim do assunto,
    # mas não uma saudação como "Prezado,".
    return " " not in proxima and len(proxima) <= 25 and not proxima.endswith(",")


def extrair_assunto(texto_primeira_pagina: str) -> str | None:
    """Texto após "Assunto:" no início do documento, juntando as linhas quebradas."""
    linhas = _linhas_nao_vazias(texto_primeira_pagina, LINHAS_ASSUNTO + MAX_LINHAS_EXTRAS_ASSUNTO)
    for i, linha in enumerate(linhas[:LINHAS_ASSUNTO]):
        m = re.match(r"(?i)^assunto\s*:\s*(.*)$", linha)
        if not m:
            continue
        partes = [m.group(1)]
        for proxima in linhas[i + 1 : i + 1 + MAX_LINHAS_EXTRAS_ASSUNTO]:
            if not _assunto_continua(" ".join(partes), proxima):
                break
            partes.append(proxima)
        assunto = re.sub(r"\s+", " ", " ".join(partes)).strip()
        return assunto or None
    return None


MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
LINHAS_DATA = 30
DATA_CABECALHO = re.compile(
    r"Bras[ií]lia(?:\s*-\s*DF)?\s*,?\s*(?P<dia>\d{1,2})\s+de\s+(?P<mes>[a-zç]+)\s+de\s+(?P<ano>\d{4})",
    re.IGNORECASE,
)
DATA_ASSINATURA = re.compile(
    r"assinado\s+eletronicamente\s+por[\s\S]{0,250}?\bem\s+(\d{2})/(\d{2})/(\d{4})",
    re.IGNORECASE,
)


def _iso(ano: int, mes: int, dia: int) -> str | None:
    if not (1 <= mes <= 12 and 1 <= dia <= 31):
        return None
    return f"{ano:04d}-{mes:02d}-{dia:02d}"


def extrair_data(texto_primeira_pagina: str) -> str | None:
    """Data do cabeçalho ("Brasília-DF, 07 de maio de 2024") em formato ISO."""
    cabecalho = "\n".join(_linhas_nao_vazias(texto_primeira_pagina, LINHAS_DATA))
    m = DATA_CABECALHO.search(cabecalho)
    if not m:
        return None
    mes = MESES.get(m["mes"].lower())
    return _iso(int(m["ano"]), mes, int(m["dia"])) if mes else None


def extrair_data_assinatura(texto_documento: str) -> str | None:
    """Data da primeira assinatura eletrônica do documento, em formato ISO."""
    datas = [_iso(int(a), int(m), int(d)) for d, m, a in DATA_ASSINATURA.findall(texto_documento)]
    datas = [data for data in datas if data]
    return min(datas) if datas else None


LINHAS_UNIDADE = 15
SIGLA = r"[A-Z][A-Z0-9\-]*(?:/[A-Z0-9][A-Z0-9\-]*)+"
CABECALHO_COM_SIGLA = re.compile(rf"^[A-Za-zÀ-ú .]+?\s*[-–]\s*(?P<sigla>{SIGLA})$")


def extrair_unidade(texto_primeira_pagina: str, numero_documento: str | None) -> str | None:
    """Unidade emissora (sigla SEI), ex.: "UNDF/REIT/CEINTER".

    Vem do número oficial ("98/2024 - UNDF/REIT/CEINTER") ou, em documentos
    sem número, da linha de cabeçalho ("Despacho - UNDF/REIT").
    """
    if numero_documento and " - " in numero_documento:
        return numero_documento.split(" - ", 1)[1]
    for linha in _linhas_nao_vazias(texto_primeira_pagina, LINHAS_UNIDADE):
        m = CABECALHO_COM_SIGLA.match(re.sub(r"\s+", " ", linha))
        if m:
            return m["sigla"]
    return None
