import pytest
from app.evaluation import ranking_metrics
from app.ingestion.embeddings import ModelError
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.rerank import rerank
from app.schemas.query import Evidence, QueryRequest


def evidence(chunk_id, **scores):
    return Evidence(
        chunk_id=chunk_id,
        text=f"Texto {chunk_id}",
        processo_sei="00000-00000001/2025-01",
        documento_sei_id="123456",
        tipo_documento="Despacho",
        arquivo_origem="sintetico.pdf",
        pagina_inicio=1,
        pagina_fim=1,
        paginas_origem=[1],
        **scores,
    )


def test_rrf_deduplica_e_preserva_pontuacoes_e_fonte():
    dense = [evidence("b", vector_score=0.3), evidence("a", vector_score=0.2)]
    lexical = [
        evidence("a", keyword_score=0.1, exact_identifier_match=True),
        evidence("c", keyword_score=0.8),
        evidence("a", keyword_score=0.1),
    ]
    results = reciprocal_rank_fusion(dense, lexical, k=10)
    assert [hit.chunk_id for hit in results] == ["a", "b", "c"]
    hit = results[0]
    assert hit.rrf_score == pytest.approx(1 / 11 + 1 / 12)
    assert hit.vector_score == 0.2
    assert hit.keyword_score == 0.1
    assert hit.exact_identifier_match
    assert hit.paginas_origem == [1]
    assert reciprocal_rank_fusion([], []) == []


def test_reranking_limita_pares_e_retorna_top_k():
    def score(pairs):
        assert pairs == [("pergunta", "Texto a"), ("pergunta", "Texto b")]
        return [-1.0, 0.0]

    hits = rerank("pergunta", list(map(evidence, "abc")), score, limit=2, top_k=1)
    assert [(hit.chunk_id, hit.rerank_score) for hit in hits] == [("b", 0)]
    assert hits[0].arquivo_origem == "sintetico.pdf"
    with pytest.raises(ModelError):
        rerank("pergunta", [evidence("a")], lambda pairs: [float("nan")], limit=2, top_k=1)


def test_metricas_nao_pontuam_casos_sem_rotulos():
    assert ranking_metrics(["123456"], set(), 5) is None
    result = ranking_metrics(["x", "123456", "123456", "234567"], {"123456", "234567"}, 3)
    assert result["recall_at_k"] == 0.5
    assert result["hit_rate_at_k"] == 1
    assert result["mrr_at_k"] == 0.5
    assert 0 < result["ndcg_at_k"] < 1
    assert ranking_metrics([None], {"123456"}, 1) == dict.fromkeys(result, 0)


def test_query_aceita_filtros_opcionais():
    request = QueryRequest(question="  evidências  ")
    assert request.question == "evidências"
    assert request.top_k is None
    assert request.processo_sei is None
