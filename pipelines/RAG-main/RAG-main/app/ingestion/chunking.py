"""Janelas sobre o texto limpo dos documentos já segmentados pelo parser."""

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

TokenOffsets = Callable[[str], list[tuple[int, int]]]


def _digest(*parts: object) -> str:
    serialized = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChunkData:
    chunk_id: str
    document_key: str
    processo_sei: str
    documento_sei_id: str | None
    tipo_documento: str | None
    arquivo_origem: str
    pagina_inicio: int
    pagina_fim: int
    paginas_origem: tuple[int, ...]
    token_count: int
    text: str


def read_documents(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, start=1):
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    raise ValueError(f"JSONL de documentos inválido na linha {number}.") from None


def document_key(document: dict) -> str:
    # O parser pode reportar blocos distintos com o mesmo ID SEI, ou ID ausente.
    return _digest(document["processo_sei"], document["arquivo_origem"], document["pagina_inicio"])


def chunk_document(
    document: dict,
    tokenize: TokenOffsets,
    chunk_tokens: int = 500,
    overlap: int = 75,
) -> Iterator[ChunkData]:
    if not 0 <= overlap < chunk_tokens:
        raise ValueError("Use 0 <= overlap < chunk_tokens.")

    texts, spans = [], []
    cursor = 0
    for page in document["paginas"]:
        cleaned = page["texto_limpo"].strip()
        if cleaned:
            texts.append(cleaned)
            spans.append((page["pagina"], cursor, cursor + len(cleaned)))
            cursor += len(cleaned) + 2

    full_text = "\n\n".join(texts)
    offsets = tokenize(full_text) if full_text else []
    key = document_key(document)
    start = 0
    while start < len(offsets):
        stop = min(start + chunk_tokens, len(offsets))
        left = offsets[start][0]
        while stop > start:
            right = max(end for _, end in offsets[start:stop])
            content = full_text[left:right].strip()
            token_count = len(tokenize(content)) if content else 0
            if token_count <= chunk_tokens:
                break
            # Um recorte pode ser retokenizado de forma diferente no início da palavra.
            stop -= 1
        else:
            raise ValueError("Limite de tokens insuficiente para um recorte do tokenizador.")

        if token_count:
            pages = tuple(page for page, begin, end in spans if begin < right and left < end)
            yield ChunkData(
                chunk_id=_digest(key, document["documento_sei_id"], start, stop, pages, content),
                document_key=key,
                processo_sei=document["processo_sei"],
                documento_sei_id=document["documento_sei_id"],
                tipo_documento=document["tipo_documento"],
                arquivo_origem=document["arquivo_origem"],
                pagina_inicio=pages[0],
                pagina_fim=pages[-1],
                paginas_origem=pages,
                token_count=token_count,
                text=content,
            )
        if stop == len(offsets):
            break
        start = max(start + 1, stop - overlap)
