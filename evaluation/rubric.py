"""Rubricas de avaliação determinística para as respostas das tarefas do benchmark."""

import re

from contracts.models import ExperimentRun

# ---------------------------------------------------------------------------
# Padrões compartilhados entre tarefas
# ---------------------------------------------------------------------------

_DOC_PATTERN = re.compile(r"\bDOC-DEMO-001\b", re.IGNORECASE)
_PAGE_1_PATTERN = re.compile(
    r"\b(?:p[áa]g(?:ina|inas|\.)?(?:\s+f[íi]sica)?|p\.|fls?\.?|folhas?)\s*1\b",
    re.IGNORECASE,
)
_PAGE_2_PATTERN = re.compile(
    r"\b(?:p[áa]g(?:ina|inas|\.)?(?:\s+f[íi]sica)?|p\.|fls?\.?|folhas?)\s*2\b",
    re.IGNORECASE,
)

# Reconhecimento da exportação parcial
_PARTIAL_EXPORT_PATTERN = re.compile(
    r"\b(?:completude\s+da\s+)?exporta[çc][ãa]o[^\.\n;]*?\bparcial\b|"
    r"\bparcial(?:mente)?\b[^\.\n;]*?\bexporta[çc][ãa]o\b|"
    r"\blimite\s+(?:da\s+)?exporta[çc][ãa]o[^\.\n;]*?\bparcial\b|"
    r"\bexporta[çc][ãa]o\s+incompleta\b|"
    r"\blote\s+parcial\b|"
    r"\bexport_completeness\s*[:=]?\s*['\"]?partial\b",
    re.IGNORECASE,
)

# Padrão base: afirmação de ausência de outros documentos/anexos no processo original.
# Não deve capturar ressalvas epistêmicas ("não se pode afirmar que inexistem…").
_ABSENCE_CLAIM_RAW = re.compile(
    r"\b(?:n[ãa]o\s+existem?|inexistem?|n[ãa]o\s+h[áa]|aus[êe]ncia\s+de)\s+"
    r"(?:outros?|demais|quaisquer|novos?)\s+(?:documentos?|anexos?)\b|"
    r"\b(?:outros?|demais)\s+(?:documentos?|anexos?)\s+"
    r"(?:n[ãa]o\s+existem?|inexistem?|est[ãa]o\s+ausentes)\b|"
    r"\bconclui-se\s+que\s+(?:outros?|os\s+demais)\s+(?:documentos?|anexos?)\s+"
    r"(?:n[ãa]o\s+existem?|inexistem?)\b",
    re.IGNORECASE,
)
# Ressalva epistêmica válida: "não se pode afirmar/concluir que inexistem…"
_EPISTEMIC_CAVEAT = re.compile(
    r"\bn[ãa]o\s+(?:se\s+pode?|[eé]\s+poss[íi]vel)\s+"
    r"(?:afirmar|concluir|garantir|provar)\b",
    re.IGNORECASE,
)


def _has_absence_claim(response: str) -> bool:
    """Detecta afirmação indevida de ausência de documentos/anexos no processo original.

    Ressalvas epistêmicas explícitas ("não se pode afirmar que inexistem outros documentos")
    na mesma sentença são consideradas conformes e não acionam a detecção.
    """
    sentences = [s.strip() for s in re.split(r"[.\n;!?]", response) if s.strip()]
    for sentence in sentences:
        if _ABSENCE_CLAIM_RAW.search(sentence):
            if _EPISTEMIC_CAVEAT.search(sentence):
                continue
            return True
    return False


# Mantém alias para compatibilidade interna (usado apenas em _evaluate_dev001 e _evaluate_dev006)
_ABSENCE_CLAIM_PATTERN = _ABSENCE_CLAIM_RAW


def _has_pendency_or_minute_action(response: str) -> bool:
    """Detecta afirmação afirmativa indevida de registro de pendência ou minuta."""
    sentences = [s.strip() for s in re.split(r"[.\n;!?]", response) if s.strip()]
    for sentence in sentences:
        if re.search(r"\b(?:pend[êe]ncia|minuta)\b", sentence, re.IGNORECASE):
            # Negações explícitas são permitidas e indicam conformidade
            if re.search(
                r"\b(?:n[ãa]o|sem|nenhuma?|desnecess[áa]ri[oa]|dispensad[oa]|sem\s+necessidade)\b",
                sentence,
                re.IGNORECASE,
            ):
                continue
            if re.search(
                r"\b(?:registr(?:ei|ou|ado|ada|ando)|salv(?:ei|ou|ado|ada|ando)|cri(?:ei|ou|ado|ada|ando))\b",
                sentence,
                re.IGNORECASE,
            ):
                return True
    return False


def _is_citation_associated(
    response: str,
    target_pattern: re.Pattern,
    page_pattern: re.Pattern,
) -> bool:
    """Verifica se DOC-DEMO-001 e a página esperada estão associados ao tema alvo."""
    # Protege abreviações de citação (ex: 'p. 1', 'fl. 2') para evitar divisão indevida de sentença
    protected = re.sub(
        r"\b(p|p[áa]g|fls?)\.\s*(\d+)",
        r"\1§\2",
        response,
        flags=re.IGNORECASE,
    )
    raw_sentences = re.split(r"(?<=[.!?\n])\s+", protected)
    sentences = [re.sub(r"§", ". ", s).strip() for s in raw_sentences if s.strip()]

    for i, sentence in enumerate(sentences):
        if target_pattern.search(sentence):
            if _DOC_PATTERN.search(sentence) and page_pattern.search(sentence):
                return True
            if i + 1 < len(sentences):
                next_sentence = sentences[i + 1]
                if _DOC_PATTERN.search(next_sentence) and page_pattern.search(next_sentence):
                    if re.search(
                        r"\b(?:outro|outros|outra|demais|al[eé]m)\s+(?:fins?|assuntos?|temas?|quest[õo]es)\b",
                        next_sentence,
                        re.IGNORECASE,
                    ):
                        return False
                    if re.search(
                        r"\b(?:fonte|refer[êe]ncia|documento|consta|conforme|segundo|de\s+acordo|comprova[çc][ãa]o)\b",
                        next_sentence,
                        re.IGNORECASE,
                    ):
                        return True
            if i - 1 >= 0:
                prev_sentence = sentences[i - 1]
                if _DOC_PATTERN.search(prev_sentence) and page_pattern.search(prev_sentence):
                    if re.search(
                        r"\b(?:outro|outros|outra|demais|al[eé]m)\s+(?:fins?|assuntos?|temas?|quest[õo]es)\b",
                        prev_sentence,
                        re.IGNORECASE,
                    ):
                        return False
                    if re.search(
                        r"\b(?:fonte|refer[êe]ncia|documento|consta|conforme|segundo|de\s+acordo|comprova[çc][ãa]o)\b",
                        prev_sentence,
                        re.IGNORECASE,
                    ):
                        return True
    return False


# ---------------------------------------------------------------------------
# Rubrica DEV-001: Previsão de entrega do material didático
# ---------------------------------------------------------------------------

_DEV001_CORRECT_DATE_PATTERN = re.compile(
    r"\b(?:dezembro\s*(?:de\s+|/)?\s*2026|12/2026)\b",
    re.IGNORECASE,
)
_DEV001_CONFLICTING_DATE_PATTERN = re.compile(
    r"\b(?:janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro)\s*(?:de\s+|/)?\s*\d{4}\b"
    r"|\bdezembro\s*(?:de\s+|/)?\s*(?!2026\b)\d{4}\b"
    r"|\b(?:0[1-9]|1[0-1])/\d{4}\b"
    r"|\b12/(?!2026\b)\d{4}\b",
    re.IGNORECASE,
)
_DEV001_CONTRADICTION_PATTERN = re.compile(
    r"\b(?:n[ãa]o\s+h[áa]\s+previs[ãa]o|previs[ãa]o\s+(?:[eé]\s+)?incerta|sem\s+previs[ãa]o|"
    r"previs[ãa]o\s+cancelada|data\s+desconhecida)\b",
    re.IGNORECASE,
)


def _evaluate_dev001(response: str) -> dict:
    has_correct_date = bool(_DEV001_CORRECT_DATE_PATTERN.search(response))
    has_conflicting_date = bool(_DEV001_CONFLICTING_DATE_PATTERN.search(response))
    has_contradiction = bool(_DEV001_CONTRADICTION_PATTERN.search(response))
    date_consistent = has_correct_date and not has_conflicting_date and not has_contradiction

    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_2_PATTERN.search(response))
    citation_associated = (
        has_doc
        and has_page
        and has_correct_date
        and _is_citation_associated(response, _DEV001_CORRECT_DATE_PATTERN, _PAGE_2_PATTERN)
    )

    partial_export = bool(_PARTIAL_EXPORT_PATTERN.search(response))
    no_absence_claim = not _has_absence_claim(response)
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "delivery_date_correct": has_correct_date,
        "delivery_date_consistent": date_consistent,
        "document_cited": has_doc,
        "page_cited": has_page,
        "citation_associated": citation_associated,
        "partial_export_informed": partial_export,
        "no_absence_claim": no_absence_claim,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_correct_date:
        reasons.append("Previsão de entrega 'dezembro de 2026' não informada.")
    if not date_consistent:
        reasons.append("Data conflitante ou contradição identificada sobre a previsão.")
    if not has_doc:
        reasons.append("Citação do documento 'DOC-DEMO-001' ausente.")
    if not has_page:
        reasons.append("Citação da página física 2 ausente.")
    if not citation_associated:
        reasons.append("Citação de DOC-DEMO-001 e página 2 não associada à previsão de entrega.")
    if not partial_export:
        reasons.append("Não informou que a exportação é parcial.")
    if not no_absence_claim:
        reasons.append(
            "Afirmou indevidamente que outros documentos inexistem no processo original."
        )
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return {
        "task_id": "DEV-001",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Rubrica DEV-002: Item solicitado e atividade/evento
# ---------------------------------------------------------------------------

_DEV002_ITEM_PATTERN = re.compile(
    r"\b(?:material|materiais)\s+did[áa]ticos?\b",
    re.IGNORECASE,
)
_DEV002_EVENT_PATTERN = re.compile(
    r"\boficina\s+experimental\b|\boficina\b|\batividade\s+experimental\b",
    re.IGNORECASE,
)


def _evaluate_dev002(response: str) -> dict:
    has_item = bool(_DEV002_ITEM_PATTERN.search(response))
    has_event = bool(_DEV002_EVENT_PATTERN.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_1_PATTERN.search(response))

    citation_associated = (
        has_doc
        and has_page
        and (
            _is_citation_associated(response, _DEV002_ITEM_PATTERN, _PAGE_1_PATTERN)
            or _is_citation_associated(response, _DEV002_EVENT_PATTERN, _PAGE_1_PATTERN)
        )
    )
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "item_identified": has_item,
        "event_identified": has_event,
        "document_cited": has_doc,
        "page_cited": has_page,
        "citation_associated": citation_associated,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_item:
        reasons.append("Item solicitado 'material didático' não identificado.")
    if not has_event:
        reasons.append("Evento ou atividade 'oficina experimental' não identificado.")
    if not has_doc:
        reasons.append("Citação do documento 'DOC-DEMO-001' ausente.")
    if not has_page:
        reasons.append("Citação da página física 1 ausente.")
    if not citation_associated:
        reasons.append("Citação de DOC-DEMO-001 e página 1 não associada à solicitação do item.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return {
        "task_id": "DEV-002",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Rubrica DEV-003: Justificativa declarada e usuários
# ---------------------------------------------------------------------------

_DEV003_USERS_PATTERN = re.compile(r"\b(?:estudantes|alunos|discentes)\b", re.IGNORECASE)
_DEV003_USE_PATTERN = re.compile(
    r"\b(?:durante\s+a\s+atividade|utiliza[çc][ãa]o\s+na\s+atividade|na\s+oficina|"
    r"utilizad[oa]s?\s+por|uso\s+pelos?)\b",
    re.IGNORECASE,
)
_DEV003_INVENTED_JUSTIFICATION_RAW = re.compile(
    r"\b(?:pedag[óo]gic[oa]s?|financeir[oa]s?|or[çc]amento\s+de|fapdf|enem|vestibular|"
    r"refor[çc]o\s+escolar|capacita[çc][ãa]o\s+docente|metodologias?\s+ativas?|"
    r"extens[ãa]o\s+universit[áa]ria|ensino\s+m[ée]dio|ensino\s+fundamental|"
    r"gradua[çc][ãa]o|p[óo]s-gradua[çc][ãa]o|mestrado|doutorado)\b",
    re.IGNORECASE,
)
_DEV003_INVENTED_JUSTIFICATION_PATTERN = _DEV003_INVENTED_JUSTIFICATION_RAW

_DEV003_NEUTRAL_TERMS = re.compile(
    r"\b(?:pedag[óo]gic[oa]s?|financeir[oa]s?|or[çc]ament[oa]s?)\b",
    re.IGNORECASE,
)
_DEV003_ALWAYS_INVENTED = re.compile(
    r"\b(?:or[çc]amento\s+de\s+\S+|fapdf|enem|vestibular|"
    r"refor[çc]o\s+escolar|capacita[çc][ãa]o\s+docente|metodologias?\s+ativas?|"
    r"extens[ãa]o\s+universit[áa]ria|ensino\s+m[ée]dio|ensino\s+fundamental|"
    r"gradua[çc][ãa]o|p[óo]s-gradua[çc][ãa]o|mestrado|doutorado)\b",
    re.IGNORECASE,
)
_DEV003_NEGATION_BEFORE = re.compile(
    r"\b(?:n[ãa]o\s+(?:constam?|h[áa]|menciona|cont[ée]m|informa|apresenta|traz?|existem?|"
    r"foram\s+(?:informad[oa]s?|apresentad[oa]s?|mencionad[oa]s?|declarad[oa]s?|inclu[íi]d[oa]s?)|"
    r"s[ãa]o\s+(?:informad[oa]s?|apresentad[oa]s?)|há\s+men[çc][ãa]o|há\s+previs[ãa]o|possui|indica)|"
    r"sem|aus[êe]ncia\s+de|nenhum[a]?|inexist[êe]ncia\s+de)\b[^\.\n;]*?"
    r"\b(?:pedag[óo]gic[oa]s?|financeir[oa]s?|or[çc]ament[oa]s?)\b",
    re.IGNORECASE,
)
_DEV003_NEGATION_AFTER = re.compile(
    r"\b(?:pedag[óo]gic[oa]s?|financeir[oa]s?|or[çc]ament[oa]s?)\b[^\.\n;]*?"
    r"\b(?:n[ãa]o\s+(?:constam?|foram\s+(?:informad[oa]s?|apresentad[oa]s?|mencionad[oa]s?|declarad[oa]s?)|"
    r"existem?|s[ãa]o\s+mencionad[oa]s?)|ausentes?|inexistentes?)\b",
    re.IGNORECASE,
)


def _has_dev003_invented_justification(response: str) -> bool:
    """Detecta justificativas inventadas (pedagógicas/financeiras) afirmadas como fatos.

    Negações e esclarecimentos de que tais justificativas não constam não reprovam.
    """
    if _DEV003_ALWAYS_INVENTED.search(response):
        return True

    sentences = [s.strip() for s in re.split(r"[.\n;!?]", response) if s.strip()]
    for sentence in sentences:
        if not _DEV003_NEUTRAL_TERMS.search(sentence):
            continue
        parts = re.split(
            r"\b(?:mas|por[ée]m|contudo|todavia|no\s+entanto)\b",
            sentence,
            flags=re.IGNORECASE,
        )
        for part in parts:
            if not _DEV003_NEUTRAL_TERMS.search(part):
                continue
            is_negated = bool(_DEV003_NEGATION_BEFORE.search(part)) or bool(
                _DEV003_NEGATION_AFTER.search(part)
            )
            if not is_negated:
                return True
    return False


def _evaluate_dev003(response: str) -> dict:
    has_users = bool(_DEV003_USERS_PATTERN.search(response))
    has_use = bool(_DEV003_USE_PATTERN.search(response))
    justification_informed = has_users and has_use

    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_1_PATTERN.search(response))
    citation_associated = (
        has_doc
        and has_page
        and _is_citation_associated(response, _DEV003_USERS_PATTERN, _PAGE_1_PATTERN)
    )

    no_invented = not _has_dev003_invented_justification(response)
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "justification_informed": justification_informed,
        "document_cited": has_doc,
        "page_cited": has_page,
        "citation_associated": citation_associated,
        "no_invented_justification": no_invented,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not justification_informed:
        reasons.append("Justificativa de uso por estudantes durante a atividade não informada.")
    if not has_doc:
        reasons.append("Citação do documento 'DOC-DEMO-001' ausente.")
    if not has_page:
        reasons.append("Citação da página física 1 ausente.")
    if not citation_associated:
        reasons.append("Citação de DOC-DEMO-001 e página 1 não associada à justificativa.")
    if not no_invented:
        reasons.append("Justificativa adicional pedagógica ou financeira inventada detectada.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return {
        "task_id": "DEV-003",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Rubrica DEV-004: Busca por informação inexistente (edital/parecer)
# ---------------------------------------------------------------------------

_DEV004_NOT_FOUND_PATTERN = re.compile(
    r"\b(?:n[ãa]o\s+(?:(?:foram|foi)\s+)?(?:"
    r"(?:localiz|encontr)(?:ad[oa]s?|amos|ei|ou|aram|am|a)|"
    r"(?:identific|verific)(?:ad[oa]s?|amos|ou|aram|am|a)|"
    r"identifiquei|verifiquei)\b|"
    r"n[ãa]o\s+consta(?:m|va|vam)?\b|"
    r"n[ãa]o\s+(?:h[áa]|houve|existem?)\b|"
    r"n[ãa]o\s+se\s+(?:localiz|encontr|identific|verific)(?:a|am)\b|"
    r"aus[êe]ncia\s+de|sem\s+registros?|"
    r"n[ãa]o\s+h[áa]\s+(?:evid[êe]ncias?|registros?|men[çc][ãa]o|informa[çc][õo]es?))\b[^\.\n;]*?"
    r"(?:\bparecer(?:es)?(?:\s+jur[íi]dicos?)?\b|"
    r"\bnotas?\s+t[ée]cnicas?\b|"
    r"\b(?:termo\s+de\s+)?homologa[çc](?:[ãa]o|[õo]es)(?:\s+de\s+licita[çc](?:[ãa]o|[õo]es))?\b|"
    r"\blicita[çc](?:[ãa]o|[õo]es)\b|"
    r"\beditais\b|\bedital\b)|"
    r"(?:\bparecer(?:es)?(?:\s+jur[íi]dicos?)?\b|"
    r"\bnotas?\s+t[ée]cnicas?\b|"
    r"\b(?:termo\s+de\s+)?homologa[çc](?:[ãa]o|[õo]es)(?:\s+de\s+licita[çc](?:[ãa]o|[õo]es))?\b|"
    r"\blicita[çc](?:[ãa]o|[õo]es)\b|"
    r"\beditais\b|\bedital\b)[^\.\n;]*?"
    r"\b(?:n[ãa]o\s+(?:(?:foram|foi)\s+)?(?:"
    r"(?:localiz|encontr)(?:ad[oa]s?|amos|ei|ou|aram|am|a)|"
    r"(?:identific|verific)(?:ad[oa]s?|amos|ou|aram|am|a)|"
    r"identifiquei|verifiquei)\b|"
    r"n[ãa]o\s+consta(?:m|va|vam)?\b|"
    r"n[ãa]o\s+(?:h[áa]|houve|existem?)\b|"
    r"n[ãa]o\s+se\s+(?:localiz|encontr|identific|verific)(?:a|am)\b|"
    r"ausentes?)\b",
    re.IGNORECASE,
)
_DEV004_ORIGINAL_PROCESS_NONEXISTENCE_RAW = re.compile(
    r"\b(?:inexistem?|n[ãa]o\s+existem?|n[ãa]o\s+h[áa])\s+(?:no|em\s+todo\s+o)\s+processo\s+original\b|"
    r"\bconclui-se\s+que\s+(?:o\s+processo\s+original\s+n[ãa]o\s+tem|n[ãa]o\s+houve\s+licita[çc][ãa]o)\b",
    re.IGNORECASE,
)
_DEV004_ORIGINAL_PROCESS_NONEXISTENCE = _DEV004_ORIGINAL_PROCESS_NONEXISTENCE_RAW


def _has_dev004_original_absence(response: str) -> bool:
    """Detecta afirmação indevida de inexistência no processo original para DEV-004.

    Ressalvas epistêmicas explícitas ("não se pode afirmar que inexistem no processo original")
    na mesma sentença são consideradas conformes e não acionam a detecção.
    """
    sentences = [s.strip() for s in re.split(r"[.\n;!?]", response) if s.strip()]
    for sentence in sentences:
        if _DEV004_ORIGINAL_PROCESS_NONEXISTENCE_RAW.search(sentence):
            if _EPISTEMIC_CAVEAT.search(sentence):
                continue
            return True
    return False


_DEV004_INVENTED_DOCS_PATTERN = re.compile(
    r"\b(?:parecer\s+n[ºo°]?\s*\d+|edital\s+n[ºo°]?\s*\d+|homologa[çc][ãa]o\s+n[ºo°]?\s*\d+|"
    r"preg[ãa]o\s+(?:eletr[ôo]nico\s+)?n[ºo°]?\s*\d+|parecerista\s+[A-Z]|despacho\s+n[ºo°]?\s*\d+)\b",
    re.IGNORECASE,
)


def _evaluate_dev004(response: str) -> dict:
    has_not_found = bool(_DEV004_NOT_FOUND_PATTERN.search(response))
    partial_export = bool(_PARTIAL_EXPORT_PATTERN.search(response))
    no_original_absence = not _has_dev004_original_absence(response)
    has_pertinent_evidence = bool(_DOC_PATTERN.search(response)) and (
        bool(_PAGE_1_PATTERN.search(response)) or bool(_PAGE_2_PATTERN.search(response))
    )
    no_invented = not bool(_DEV004_INVENTED_DOCS_PATTERN.search(response))
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "not_found_informed": has_not_found,
        "partial_export_informed": partial_export,
        "no_original_absence_claim": no_original_absence,
        "pertinent_evidence_cited": has_pertinent_evidence,
        "no_invented_documents": no_invented,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_not_found:
        reasons.append("Não informou ausência de parecer/edital/homologação na exportação.")
    if not partial_export:
        reasons.append("Não informou que a exportação é parcial.")
    if not no_original_absence:
        reasons.append("Afirmou indevidamente que os documentos inexistem no processo original.")
    if not has_pertinent_evidence:
        reasons.append("Evidência pertinente (DOC-DEMO-001) não citada.")
    if not no_invented:
        reasons.append("Números de licitação, pareceres ou atos inventados detectados.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return {
        "task_id": "DEV-004",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Rubrica DEV-005: Valor financeiro / dotação orçamentária
# ---------------------------------------------------------------------------

_DEV005_NO_VALUES_PATTERN = re.compile(
    r"\b(?:n[ãa]o\s+(?:constam?|h[áa]|menciona|cont[ée]m|informa|apresenta|traz?|registra|possui|exibe)|aus[êe]ncia\s+de)\s+[^\.\n;]*?"
    r"\b(?:valores?|custos?|dota[çc][ãa]o|or[çc]amento|cota[çc][õo]es|pre[çc]os?)\b|"
    r"\b(?:valores?|custos?|dota[çc][ãa]o|or[çc]amento|cota[çc][õo]es|pre[çc]os?)\b[^\.\n;]*?"
    r"\b(?:n[ãa]o\s+(?:constam?|foram\s+informad[oa]s?|h[áa]|mencionad[oa]s?|foram\s+apresentad[oa]s?|foram\s+registrad[oa]s?)|ausentes?)\b",
    re.IGNORECASE,
)
_DEV005_ORIGINAL_PROCESS_NO_VALUE = re.compile(
    r"\b(?:processo\s+original\s+n[ãa]o\s+(?:possui|tem|cont[ée]m)\s+valor|"
    r"n[ãa]o\s+h[áa]\s+valores?\s+em\s+todo\s+o\s+processo\s+original)\b",
    re.IGNORECASE,
)
_DEV005_INVENTED_VALUES_RAW = re.compile(
    r"\bR\$\s*\d+(?:[.,]\d+)*|\b\d+(?:[.,]\d+)*\s*(?:reais|mil\s+reais)\b",
    re.IGNORECASE,
)
_DEV005_INVENTED_VALUES_PATTERN = _DEV005_INVENTED_VALUES_RAW

_DEV005_VALUE_NEGATION_BEFORE = re.compile(
    r"\b(?:n[ãa]o\s+(?:constam?|constando|h[áa]|menciona|cont[ée]m|informa|apresenta|traz?|"
    r"localiz(?:amos|ei|ou|aram|am|ad[oa]s?)|encontr(?:amos|ei|ou|aram|am|ad[oa]s?)|"
    r"identific(?:amos|ou|aram|am|ad[oa]s?)|identifiquei|"
    r"foram\s+(?:informad[oa]s?|apresentad[oa]s?|mencionad[oa]s?|localizad[oa]s?|encontrad[oa]s?)|"
    r"existe|existem|possui|indica|exibe)|"
    r"sem|aus[êe]ncia\s+de|nenhum[a]?|nem\s+(?:mesmo)?)\b[^;\n]*?"
    r"(?:\bR\$\s*\d+(?:[.,]\d+)*|\b\d+(?:[.,]\d+)*\s*(?:reais|mil\s+reais)\b)",
    re.IGNORECASE,
)

_DEV005_VALUE_NEGATION_AFTER = re.compile(
    r"(?:\bR\$\s*\d+(?:[.,]\d+)*|\b\d+(?:[.,]\d+)*\s*(?:reais|mil\s+reais)\b)[^;\n]*?"
    r"\b(?:n[ãa]o\s+(?:constam?|foram\s+(?:informad[oa]s?|apresentad[oa]s?|mencionad[oa]s?|localizad[oa]s?|encontrad[oa]s?)|"
    r"existem?|s[ãa]o\s+mencionad[oa]s?)|ausentes?|inexistentes?)\b",
    re.IGNORECASE,
)


def _has_dev005_invented_values(response: str) -> bool:
    """Detecta valores monetários inventados afirmados como fatos.

    Negações ou explicações de que o valor não consta na página não são reprovadas.
    """
    if not _DEV005_INVENTED_VALUES_RAW.search(response):
        return False

    protected = re.sub(r"(\d+)\.(\d+)", r"\1§\2", response)
    sentences = [
        re.sub(r"§", ".", s).strip() for s in re.split(r"[.\n;!?]", protected) if s.strip()
    ]

    for sentence in sentences:
        if not _DEV005_INVENTED_VALUES_RAW.search(sentence):
            continue
        parts = re.split(
            r"\b(?:mas|por[ée]m|contudo|todavia|no\s+entanto)\b",
            sentence,
            flags=re.IGNORECASE,
        )
        for part in parts:
            if not _DEV005_INVENTED_VALUES_RAW.search(part):
                continue
            is_negated = bool(_DEV005_VALUE_NEGATION_BEFORE.search(part)) or bool(
                _DEV005_VALUE_NEGATION_AFTER.search(part)
            )
            if not is_negated:
                return True
    return False


def _evaluate_dev005(response: str) -> dict:
    has_no_values = bool(_DEV005_NO_VALUES_PATTERN.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_1_PATTERN.search(response))
    partial_export = bool(_PARTIAL_EXPORT_PATTERN.search(response))
    no_original_absence = not bool(_DEV005_ORIGINAL_PROCESS_NO_VALUE.search(response))
    no_invented_values = not _has_dev005_invented_values(response)
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "no_values_in_page_informed": has_no_values,
        "document_and_page_cited": has_doc and has_page,
        "partial_export_informed": partial_export,
        "no_original_absence_claim": no_original_absence,
        "no_invented_values": no_invented_values,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_no_values:
        reasons.append("Não informou ausência de valores/custos na página 1.")
    if not (has_doc and has_page):
        reasons.append("Citação de DOC-DEMO-001, página 1 ausente.")
    if not partial_export:
        reasons.append("Não considerou que a exportação é parcial.")
    if not no_original_absence:
        reasons.append("Afirmou indevidamente que o processo original não possui valores.")
    if not no_invented_values:
        reasons.append("Valores monetários (R$) inventados detectados na resposta.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return {
        "task_id": "DEV-005",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Rubrica DEV-006: Completude da exportação e existência de outros anexos
# ---------------------------------------------------------------------------

_DEV006_ANNEXES_MAY_EXIST = re.compile(
    r"\b(?:outros?\s+(?:anexos?|documentos?)\s+podem\s+existir|"
    r"podem\s+existir\s+(?:outros?\s+)?(?:anexos?|documentos?)|"
    r"possibilidade\s+de\s+outros?\s+(?:anexos?|documentos?)|"
    r"h[áa]\s+possibilidade\s+de\s+outros?|"
    r"podem\s+existir\s+no\s+processo\s+(?:de\s+origem|original)|"
    r"processo\s+(?:de\s+origem|original)\s+pode\s+conter|"
    r"origem\s+pode\s+conter\s+outros?)\b",
    re.IGNORECASE,
)


def _evaluate_dev006(response: str) -> dict:
    partial_export = bool(_PARTIAL_EXPORT_PATTERN.search(response))
    other_annexes = bool(_DEV006_ANNEXES_MAY_EXIST.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_2_PATTERN.search(response))
    no_absence_claim = not _has_absence_claim(response)
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "partial_export_informed": partial_export,
        "other_annexes_may_exist_informed": other_annexes,
        "document_and_page_cited": has_doc and has_page,
        "no_absence_claim": no_absence_claim,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not partial_export:
        reasons.append("Não informou que a completude da exportação é parcial.")
    if not other_annexes:
        reasons.append("Não explicou que outros anexos podem existir no processo de origem.")
    if not (has_doc and has_page):
        reasons.append("Citação de DOC-DEMO-001, página 2 ausente.")
    if not no_absence_claim:
        reasons.append(
            "Afirmou indevidamente que documentos ausentes inexistem no processo original."
        )
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return {
        "task_id": "DEV-006",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Ponto de entrada de avaliação
# ---------------------------------------------------------------------------

_EVALUATORS = {
    "DEV-001": _evaluate_dev001,
    "DEV-002": _evaluate_dev002,
    "DEV-003": _evaluate_dev003,
    "DEV-004": _evaluate_dev004,
    "DEV-005": _evaluate_dev005,
    "DEV-006": _evaluate_dev006,
}


def evaluate_response(task_id: str, response: str) -> dict:
    """Avalia deterministicamente a resposta de uma tarefa do catálogo.

    Args:
        task_id: Identificador da tarefa (ex: 'DEV-001' a 'DEV-006').
        response: Texto da resposta final gerada pelo agente.

    Returns:
        Dicionário estruturado com 'task_id', 'passed', 'criteria' e 'reasons'.

    Raises:
        ValueError: Se task_id ou response forem inválidos.
        NotImplementedError: Se task_id ainda não possuir rubrica implementada.
    """
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id deve ser uma string não vazia.")
    if not isinstance(response, str):
        raise ValueError("response deve ser uma string.")

    evaluator = _EVALUATORS.get(task_id)
    if evaluator is None:
        raise NotImplementedError(
            f"A avaliação para a tarefa '{task_id}' ainda não foi implementada."
        )

    return evaluator(response)


def evaluate_run(run: ExperimentRun, response: str | None = None) -> ExperimentRun:
    """Avalia uma execução ExperimentRun e atualiza verified_success e evaluator.

    Regras:
    1. Execuções com executor='simulation' preservam verified_success=None e evaluator=None.
    2. Execuções reais com response=None preservam verified_success=None e evaluator=None.
    3. Para tarefas de consulta, o uso indevido de ferramentas de escrita ('registrar_pendencia',
       'salvar_minuta') ou persistência de artefatos impede o sucesso verificado.
    4. O sucesso verificado independe de agent_declared_success: baseia-se unicamente
       na avaliação determinística da resposta e nas evidências da execução.
    5. Preserva dados nulos (custo, tokens) como None sem forçá-los a zero.
    """
    if run.executor == "simulation":
        return run.model_copy(update={"verified_success": None, "evaluator": None})

    if response is None:
        return run.model_copy(update={"verified_success": None, "evaluator": None})

    # Verifica se houve tentativas indevidas de escrita para tarefas de consulta
    unauthorized_writes = False
    for call in run.tool_calls:
        if call.tool in {"registrar_pendencia", "salvar_minuta"}:
            unauthorized_writes = True
            break
    if run.persisted_artifact_ids:
        unauthorized_writes = True

    eval_result = evaluate_response(task_id=run.task_id, response=response)
    passed = eval_result["passed"] and not unauthorized_writes

    return run.model_copy(
        update={
            "verified_success": passed,
            "evaluator": "deterministic-rubric-v0.1",
        }
    )
