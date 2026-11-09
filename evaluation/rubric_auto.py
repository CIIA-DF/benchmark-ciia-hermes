"""Rubricas de avaliação determinística por regex para as respostas das tarefas do benchmark."""

import re

from contracts.models import ExperimentRun

# ---------------------------------------------------------------------------
# Tipos e estruturas de resultado
# ---------------------------------------------------------------------------


class RubricResult(dict):
    """Resultado estruturado da avaliação determinística de uma resposta."""

    task_id: str
    passed: bool
    criteria: dict[str, bool]
    reasons: list[str]

    def __init__(
        self,
        task_id: str,
        passed: bool,
        criteria: dict[str, bool],
        reasons: list[str],
    ):
        super().__init__(
            task_id=task_id,
            passed=passed,
            criteria=criteria,
            reasons=reasons,
        )
        self.task_id = task_id
        self.passed = passed
        self.criteria = criteria
        self.reasons = reasons


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

# Afirmação indevida de ausência de outros documentos/anexos no processo original
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

    Ressalvas epistêmicas explícitas na mesma sentença são permitidas.
    """
    sentences = [s.strip() for s in re.split(r"[.\n;!?]", response) if s.strip()]
    for sentence in sentences:
        if _ABSENCE_CLAIM_RAW.search(sentence):
            if _EPISTEMIC_CAVEAT.search(sentence):
                continue
            return True
    return False


def _has_pendency_or_minute_action(response: str) -> bool:
    """Detecta afirmação afirmativa indevida de registro de pendência ou minuta."""
    sentences = [s.strip() for s in re.split(r"[.\n;!?]", response) if s.strip()]
    for sentence in sentences:
        if re.search(r"\b(?:pend[êe]ncia|minuta)\b", sentence, re.IGNORECASE):
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
# DEV-001: Previsão de entrega do material didático
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


def _evaluate_dev001(response: str) -> RubricResult:
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

    return RubricResult(
        task_id="DEV-001",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-002: Item solicitado e atividade/evento
# ---------------------------------------------------------------------------

_DEV002_ITEM_PATTERN = re.compile(
    r"\b(?:material|materiais)\s+did[áa]ticos?\b",
    re.IGNORECASE,
)
_DEV002_EVENT_PATTERN = re.compile(
    r"\boficina\s+experimental\b|\boficina\b|\batividade\s+experimental\b",
    re.IGNORECASE,
)


def _evaluate_dev002(response: str) -> RubricResult:
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

    return RubricResult(
        task_id="DEV-002",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-003: Justificativa declarada e usuários
# ---------------------------------------------------------------------------

_DEV003_USERS_PATTERN = re.compile(r"\b(?:estudantes|alunos|discentes)\b", re.IGNORECASE)
_DEV003_USE_PATTERN = re.compile(
    r"\b(?:durante\s+a\s+atividade|utiliza[çc][ãa]o\s+na\s+atividade|na\s+oficina|"
    r"utilizad[oa]s?\s+por|uso\s+pelos?)\b",
    re.IGNORECASE,
)
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
    r"s[ãa]o\s+(?:informad[oa]s?|apresentad[oa]s?)|h[áa]\s+men[çc][ãa]o|h[áa]\s+previs[ãa]o|possui|indica)|"
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


def _evaluate_dev003(response: str) -> RubricResult:
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

    return RubricResult(
        task_id="DEV-003",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-004: Busca por informação inexistente (edital/parecer)
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


def _has_dev004_original_absence(response: str) -> bool:
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


def _evaluate_dev004(response: str) -> RubricResult:
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

    return RubricResult(
        task_id="DEV-004",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-005: Valor financeiro / dotação orçamentária
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


def _evaluate_dev005(response: str) -> RubricResult:
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

    return RubricResult(
        task_id="DEV-005",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-006: Completude da exportação e existência de outros anexos
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


def _evaluate_dev006(response: str) -> RubricResult:
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

    return RubricResult(
        task_id="DEV-006",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-007: Metadados oficiais de processo e documento
# ---------------------------------------------------------------------------

_DEV007_PROC_TITLE = re.compile(
    r"\bPedido\s+fict[íi]cio\s+de\s+material\s+did[áa]tico\b",
    re.IGNORECASE,
)
_DEV007_DOC_TITLE = re.compile(
    r"\bRequerimento\s+fict[íi]cio\b",
    re.IGNORECASE,
)
_DEV007_SOURCE = re.compile(
    r"\bsynthetic://requerimento-001\b",
    re.IGNORECASE,
)


def _evaluate_dev007(response: str) -> RubricResult:
    has_proc_title = bool(_DEV007_PROC_TITLE.search(response))
    has_doc_title = bool(_DEV007_DOC_TITLE.search(response))
    has_source = bool(_DEV007_SOURCE.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_1_PATTERN.search(response))
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "process_title_informed": has_proc_title,
        "doc_title_informed": has_doc_title,
        "source_uri_informed": has_source,
        "document_cited": has_doc,
        "page_cited": has_page,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_proc_title:
        reasons.append("Título do processo 'Pedido fictício de material didático' não informado.")
    if not has_doc_title:
        reasons.append("Título do documento 'Requerimento fictício' não informado.")
    if not has_source:
        reasons.append("Origem 'synthetic://requerimento-001' não informada.")
    if not has_doc:
        reasons.append("Citação do documento 'DOC-DEMO-001' ausente.")
    if not has_page:
        reasons.append("Citação da página física 1 ausente.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return RubricResult(
        task_id="DEV-007",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-008: Anexos operacionais e cronograma da oficina (Busca vazia)
# ---------------------------------------------------------------------------

_DEV008_NOT_FOUND_PATTERN = re.compile(
    r"\b(?:n[ãa]o\s+(?:(?:foram|foi)\s+)?(?:localiz|encontr|identific|verific)(?:ad[oa]s?|amos|ei|ou|aram|am|a)\b|"
    r"n[ãa]o\s+consta(?:m|va|vam)?\b|n[ãa]o\s+(?:h[áa]|houve|existem?)\b|"
    r"aus[êe]ncia\s+de|sem\s+registros?)\s+[^\.\n;]*?"
    r"(?:\bcronograma\b|\blista\s+de\s+participantes\b|\btermo\s+de\s+refer[êe]ncia\b)|"
    r"(?:\bcronograma\b|\blista\s+de\s+participantes\b|\btermo\s+de\s+refer[êe]ncia\b)[^\.\n;]*?"
    r"\b(?:n[ãa]o\s+(?:(?:foram|foi)\s+)?(?:localiz|encontr|identific|verific)(?:ad[oa]s?|amos|ei|ou|aram|am|a)\b|"
    r"n[ãa]o\s+consta(?:m|va|vam)?\b|n[ãa]o\s+(?:h[áa]|houve|existem?)\b|ausentes?|inexistentes?)\b",
    re.IGNORECASE,
)
_DEV008_INVENTED_PATTERN = re.compile(
    r"\b(?:cronograma\s+aprovado|lista\s+com\s+\d+\s+participantes|termo\s+de\s+refer[êe]ncia\s+n[ºo°]?\s*\d+)\b",
    re.IGNORECASE,
)


def _evaluate_dev008(response: str) -> RubricResult:
    has_not_found = bool(_DEV008_NOT_FOUND_PATTERN.search(response))
    partial_export = bool(_PARTIAL_EXPORT_PATTERN.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_2_PATTERN.search(response)) or bool(_PAGE_1_PATTERN.search(response))
    no_absence_claim = not _has_absence_claim(response)
    no_invented = not bool(_DEV008_INVENTED_PATTERN.search(response))
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "not_found_informed": has_not_found,
        "partial_export_informed": partial_export,
        "document_and_page_cited": has_doc and has_page,
        "no_absence_claim": no_absence_claim,
        "no_invented_attachments": no_invented,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_not_found:
        reasons.append(
            "Não informou ausência de cronograma, lista de participantes ou termo de referência."
        )
    if not partial_export:
        reasons.append("Não informou que a exportação é parcial.")
    if not (has_doc and has_page):
        reasons.append("Citação de DOC-DEMO-001 (página 2 ou 1) ausente.")
    if not no_absence_claim:
        reasons.append("Afirmou indevidamente que os anexos inexistem no processo original.")
    if not no_invented:
        reasons.append("Anexos ou dados operacionais fictícios inventados detectados.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return RubricResult(
        task_id="DEV-008",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-009: Identificação nominal e matrícula de servidor (Busca vazia)
# ---------------------------------------------------------------------------

_DEV009_NO_SIGNATORY_PATTERN = re.compile(
    r"\b(?:n[ãa]o\s+(?:constam?|h[áa]|cont[ée]m|informa|apresenta|possui|identificad[oa]s?|encontrad[oa]s?)|"
    r"aus[êe]ncia\s+de|sem)\s+[^\.\n;]*?"
    r"\b(?:servidor|signat[áa]ri[oa]|matr[íi]cula|despacho(?:\s+de\s+autoriza[çc][ãa]o)?|assinatura)\b|"
    r"\b(?:servidor|signat[áa]ri[oa]|matr[íi]cula|despacho(?:\s+de\s+autoriza[çc][ãa]o)?|assinatura)\b[^\.\n;]*?"
    r"\b(?:n[ãa]o\s+(?:constam?|h[áa]|foram\s+identificad[oa]s?|encontrad[oa]s?)|ausentes?|inexistentes?)\b",
    re.IGNORECASE,
)
_DEV009_INVENTED_PATTERN = re.compile(
    r"\b(?:matr[íi]cula\s+(?:n[ºo°]?\s*)?\d+|SIAPE\s*\d+|SIGRH\s*\d+|servidor\s+[A-Z][a-z]+\s+[A-Z][a-z]+)\b",
    re.IGNORECASE,
)


def _evaluate_dev009(response: str) -> RubricResult:
    has_no_signatory = bool(_DEV009_NO_SIGNATORY_PATTERN.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_1_PATTERN.search(response))
    no_invented = not bool(_DEV009_INVENTED_PATTERN.search(response))
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "no_signatory_informed": has_no_signatory,
        "document_and_page_cited": has_doc and has_page,
        "no_invented_signatory": no_invented,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_no_signatory:
        reasons.append(
            "Não informou ausência de servidor nominado, matrícula ou despacho na página 1."
        )
    if not (has_doc and has_page):
        reasons.append("Citação de DOC-DEMO-001, página 1 ausente.")
    if not no_invented:
        reasons.append("Identificação de servidor ou matrícula inventada detectada.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return RubricResult(
        task_id="DEV-009",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-010: Síntese cruzada entre páginas 1 e 2
# ---------------------------------------------------------------------------


def _evaluate_dev010(response: str) -> RubricResult:
    has_item = bool(_DEV002_ITEM_PATTERN.search(response)) or bool(
        re.search(r"\bmaterial\b", response, re.IGNORECASE)
    )
    has_delivery = bool(_DEV001_CORRECT_DATE_PATTERN.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page_1 = bool(_PAGE_1_PATTERN.search(response))
    has_page_2 = bool(_PAGE_2_PATTERN.search(response))
    partial_export = bool(_PARTIAL_EXPORT_PATTERN.search(response))
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "item_informed": has_item,
        "delivery_date_informed": has_delivery,
        "document_cited": has_doc,
        "both_pages_cited": has_page_1 and has_page_2,
        "partial_export_informed": partial_export,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_item:
        reasons.append("Objeto solicitado (material didático) não sintetizado.")
    if not has_delivery:
        reasons.append("Previsão de entrega 'dezembro de 2026' não sintetizada.")
    if not has_doc:
        reasons.append("Citação do documento 'DOC-DEMO-001' ausente.")
    if not (has_page_1 and has_page_2):
        reasons.append("Citação de ambas as páginas (1 e 2) é obrigatória para a síntese cruzada.")
    if not partial_export:
        reasons.append("Não informou que a exportação é parcial.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return RubricResult(
        task_id="DEV-010",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-011: Verificação de pendência formal nos autos
# ---------------------------------------------------------------------------

_DEV011_NO_PENDING_IN_DOCS = re.compile(
    r"\b(?:n[ãa]o\s+(?:constam?|h[áa]|cont[ée]m|apresenta|foram\s+identificad[oa]s?|existe)|"
    r"aus[êe]ncia\s+de|sem)\s+[^\.\n;]*?\bpend[êe]ncias?(?:\s+administrativas?)?\b|"
    r"\bpend[êe]ncias?(?:\s+administrativas?)?\b[^\.\n;]*?"
    r"\b(?:n[ãa]o\s+(?:constam?|h[áa]|foram\s+identificad[oa]s?|existem?)|ausentes?|inexistentes?)\b",
    re.IGNORECASE,
)


def _evaluate_dev011(response: str) -> RubricResult:
    has_no_formal_pending = bool(_DEV011_NO_PENDING_IN_DOCS.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_2_PATTERN.search(response)) or bool(_PAGE_1_PATTERN.search(response))
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "no_formal_pending_informed": has_no_formal_pending,
        "document_and_page_cited": has_doc and has_page,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_no_formal_pending:
        reasons.append("Não informou que inexistem pendências administrativas formais nos autos.")
    if not (has_doc and has_page):
        reasons.append("Citação de DOC-DEMO-001 (página 2 ou 1) ausente.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return RubricResult(
        task_id="DEV-011",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-012: Cabeçalho e versão de corpus
# ---------------------------------------------------------------------------

_DEV012_HEADER_PATTERN = re.compile(
    r"\bDOCUMENTO\s+FICT[ÍI]CIO\s+PARA\s+TESTES\b",
    re.IGNORECASE,
)
_DEV012_CORPUS_PATTERN = re.compile(
    r"\bsynthetic-v1\b",
    re.IGNORECASE,
)
_DEV012_EXPORT_NOTE_PATTERN = re.compile(
    r"\b(?:nota\s+de\s+exporta[çc][ãa]o|exemplo\s+sint[ée]tico|s[óo]\s+o\s+requerimento|"
    r"n[ãa]o\s+inferir\s+aus[êe]ncia|exporta[çc][ãa]o\s+parcial)\b",
    re.IGNORECASE,
)


def _evaluate_dev012(response: str) -> RubricResult:
    has_header = bool(_DEV012_HEADER_PATTERN.search(response))
    has_corpus = bool(_DEV012_CORPUS_PATTERN.search(response))
    has_export_note = bool(_DEV012_EXPORT_NOTE_PATTERN.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_1_PATTERN.search(response))
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "header_informed": has_header,
        "corpus_version_informed": has_corpus,
        "export_note_informed": has_export_note,
        "document_and_page_cited": has_doc and has_page,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_header:
        reasons.append("Cabeçalho 'DOCUMENTO FICTÍCIO PARA TESTES' não informado.")
    if not has_corpus:
        reasons.append("Versão de corpus 'synthetic-v1' não informada.")
    if not has_export_note:
        reasons.append("Nota de exportação do processo não mencionada.")
    if not (has_doc and has_page):
        reasons.append("Citação de DOC-DEMO-001, página 1 ausente.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return RubricResult(
        task_id="DEV-012",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-013: Avaliação de aprendizagem ou prova (Busca vazia)
# ---------------------------------------------------------------------------

_DEV013_NO_ASSESSMENT_PATTERN = re.compile(
    r"\b(?:n[ãa]o\s+(?:menciona|constam?|h[áa]|informa|traz?|prev[êe]|registra)|"
    r"aus[êe]ncia\s+de|sem)\s+[^\.\n;]*?"
    r"\b(?:avalia[çc][ãa]o(?:\s+de\s+aprendizagem)?|provas?(?:\s+formais?)?|testes?|exames?)\b|"
    r"\b(?:avalia[çc][ãa]o(?:\s+de\s+aprendizagem)?|provas?(?:\s+formais?)?|testes?|exames?)\b[^\.\n;]*?"
    r"\b(?:n[ãa]o\s+(?:menciona|constam?|h[áa]|s[ãa]o\s+mencionad[oa]s?)|ausentes?|inexistentes?)\b",
    re.IGNORECASE,
)
_DEV013_INVENTED_PATTERN = re.compile(
    r"\b(?:nota\s+m[íi]nima|prova\s+final|avalia[çc][ãa]o\s+somativa|crit[ée]rios?\s+de\s+aprova[çc][ãa]o|men[çc][ãa]o\s+[A-Z])\b",
    re.IGNORECASE,
)


def _evaluate_dev013(response: str) -> RubricResult:
    has_no_assessment = bool(_DEV013_NO_ASSESSMENT_PATTERN.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_1_PATTERN.search(response))
    no_invented = not bool(_DEV013_INVENTED_PATTERN.search(response))
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "no_assessment_informed": has_no_assessment,
        "document_and_page_cited": has_doc and has_page,
        "no_invented_assessment": no_invented,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_no_assessment:
        reasons.append(
            "Não informou ausência de menção a prova ou avaliação de aprendizagem na página 1."
        )
    if not (has_doc and has_page):
        reasons.append("Citação de DOC-DEMO-001, página 1 ausente.")
    if not no_invented:
        reasons.append("Critérios de avaliação ou notas inventadas detectadas.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return RubricResult(
        task_id="DEV-013",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-014: Local físico de entrega ou campus universitário (Busca vazia)
# ---------------------------------------------------------------------------

_DEV014_NO_ADDRESS_PATTERN = re.compile(
    r"\b(?:n[ãa]o\s+(?:constam?|h[áa]|cont[ée]m|informa|menciona|apresenta|traz?|localiz(?:ad[oa]s?|ei|ou|amos))|"
    r"aus[êe]ncia\s+de|sem)\s+[^\.\n;]*?"
    r"\b(?:endere[çc]o|local(?:\s+f[íi]sico)?(?:\s+de\s+entrega)?|campus(?:\s+universit[áa]rio)?|pr[ée]dio|unidade|sala)\b|"
    r"\b(?:endere[çc]o|local(?:\s+f[íi]sico)?(?:\s+de\s+entrega)?|campus(?:\s+universit[áa]rio)?|pr[ée]dio|unidade|sala)\b[^\.\n;]*?"
    r"\b(?:n[ãa]o\s+(?:constam?|h[áa]|foi\s+localizad[oa]|mencionad[oa])|ausentes?|inexistentes?)\b",
    re.IGNORECASE,
)
_DEV014_INVENTED_PATTERN = re.compile(
    r"\b(?:campus\s+(?:lago\s+norte|darcy\s+ribeiro|asa\s+norte|asa\s+sul|taguatinga|ceil[âa]ndia)|"
    r"rua\s+\S+|avenida\s+\S+|quadra\s+\S+|bloco\s+[A-Z]\b|sala\s+\d+)\b",
    re.IGNORECASE,
)


def _evaluate_dev014(response: str) -> RubricResult:
    has_no_address = bool(_DEV014_NO_ADDRESS_PATTERN.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_2_PATTERN.search(response)) or bool(_PAGE_1_PATTERN.search(response))
    partial_export = bool(_PARTIAL_EXPORT_PATTERN.search(response))
    no_invented = not bool(_DEV014_INVENTED_PATTERN.search(response))
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "no_address_informed": has_no_address,
        "partial_export_informed": partial_export,
        "document_and_page_cited": has_doc and has_page,
        "no_invented_address": no_invented,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_no_address:
        reasons.append("Não informou ausência de endereço de entrega ou campus universitário.")
    if not partial_export:
        reasons.append("Não informou que a exportação é parcial.")
    if not (has_doc and has_page):
        reasons.append("Citação de DOC-DEMO-001 (página 2 ou 1) ausente.")
    if not no_invented:
        reasons.append("Endereço ou campus fictício inventado detectado.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return RubricResult(
        task_id="DEV-014",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# DEV-015: Devolução patrimonial ou doação definitiva (Busca vazia)
# ---------------------------------------------------------------------------

_DEV015_NO_PATRIMONIAL_PATTERN = re.compile(
    r"\b(?:n[ãa]o\s+(?:estipula|constam?|h[áa]|cont[ée]m|informa|menciona|prev[êe]|apresenta)|"
    r"aus[êe]ncia\s+de|sem)\s+[^\.\n;]*?"
    r"\b(?:devolu[çc][ãa]o|doa[çc][ãa]o(?:\s+definitiva)?|guarda\s+patrimonial|comodato|cess[ãa]o|regras?\s+patrimoniais?)\b|"
    r"\b(?:devolu[çc][ãa]o|doa[çc][ãa]o(?:\s+definitiva)?|guarda\s+patrimonial|comodato|cess[ãa]o|regras?\s+patrimoniais?)\b[^\.\n;]*?"
    r"\b(?:n[ãa]o\s+(?:estipula|constam?|h[áa]|prev[êe])|ausentes?|inexistentes?)\b",
    re.IGNORECASE,
)
_DEV015_INVENTED_PATTERN = re.compile(
    r"\b(?:termo\s+de\s+(?:doa[çc][ãa]o|cess[ãa]o|comodato)|devolu[çc][ãa]o\s+obrigat[óo]ria|patrim[ôo]nio\s+n[ºo°]?\s*\d+)\b",
    re.IGNORECASE,
)


def _evaluate_dev015(response: str) -> RubricResult:
    has_no_patrimonial = bool(_DEV015_NO_PATRIMONIAL_PATTERN.search(response))
    has_doc = bool(_DOC_PATTERN.search(response))
    has_page = bool(_PAGE_1_PATTERN.search(response)) or bool(_PAGE_2_PATTERN.search(response))
    no_invented = not bool(_DEV015_INVENTED_PATTERN.search(response))
    no_pending_or_draft = not _has_pendency_or_minute_action(response)

    criteria = {
        "no_patrimonial_rules_informed": has_no_patrimonial,
        "document_and_page_cited": has_doc and has_page,
        "no_invented_patrimonial_rules": no_invented,
        "no_pending_or_draft_created": no_pending_or_draft,
    }

    reasons: list[str] = []
    if not has_no_patrimonial:
        reasons.append(
            "Não informou ausência de regras patrimoniais de devolução ou doação definitiva."
        )
    if not (has_doc and has_page):
        reasons.append("Citação de DOC-DEMO-001 (página 1 ou 2) ausente.")
    if not no_invented:
        reasons.append("Regras contratuais ou patrimoniais inventadas detectadas.")
    if not no_pending_or_draft:
        reasons.append(
            "Criou ou afirmou ter registrado pendência ou minuta para tarefa de consulta."
        )

    return RubricResult(
        task_id="DEV-015",
        passed=all(criteria.values()),
        criteria=criteria,
        reasons=reasons,
    )


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
    "DEV-007": _evaluate_dev007,
    "DEV-008": _evaluate_dev008,
    "DEV-009": _evaluate_dev009,
    "DEV-010": _evaluate_dev010,
    "DEV-011": _evaluate_dev011,
    "DEV-012": _evaluate_dev012,
    "DEV-013": _evaluate_dev013,
    "DEV-014": _evaluate_dev014,
    "DEV-015": _evaluate_dev015,
}


def evaluate_response(task_id: str, response: str) -> RubricResult:
    """Avalia deterministicamente a resposta de uma tarefa do catálogo.

    Args:
        task_id: Identificador da tarefa ('DEV-001' a 'DEV-015').
        response: Texto da resposta final gerada pelo agente.

    Returns:
        RubricResult estruturado com task_id, passed, criteria e reasons.

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

    unauthorized_writes = False
    for call in run.tool_calls:
        if call.tool in {"registrar_pendencia", "salvar_minuta"}:
            unauthorized_writes = True
            break
    if run.persisted_artifact_ids:
        unauthorized_writes = True

    eval_result = evaluate_response(task_id=run.task_id, response=response)
    passed = eval_result.passed and not unauthorized_writes

    return run.model_copy(
        update={
            "verified_success": passed,
            "evaluator": "deterministic-rubric-v0.1",
        }
    )
