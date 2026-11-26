import argparse
import json
from collections.abc import Iterable
from math import ceil
from pathlib import Path
from statistics import fmean, median
from time import perf_counter

import httpx
from app.config import RetrievalMode
from app.evaluation import ranking_metrics
from app.ingestion.loader import PASTA_REPORTS
from app.schemas.query import QueryRequest, QueryResponse
from pydantic import BaseModel, ConfigDict


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    request: QueryRequest
    relevant_ids: set[str] | None = None


def evaluate(
    client: httpx.Client,
    cases: list[EvaluationCase],
    modes: Iterable[RetrievalMode],
    k: int,
    unit: str,
) -> dict:
    if not cases:
        raise ValueError("Forneça pelo menos uma consulta.")
    runs = {}
    for mode in modes:
        results = []
        for case in cases:
            request = case.request.model_copy(update={"mode": mode, "top_k": k})
            start = perf_counter()
            response = client.post("/api/query", json=request.model_dump(mode="json"))
            response.raise_for_status()
            elapsed_ms = (perf_counter() - start) * 1000
            query = QueryResponse.model_validate(response.json())
            if query.mode != mode:
                raise ValueError("A API não executou o modo solicitado.")

            retrieved = [getattr(hit, unit) for hit in query.results]
            results.append(
                {
                    "id": case.id,
                    "latency_ms": round(elapsed_ms, 3),
                    "hits": [
                        hit.model_dump(
                            include={
                                "chunk_id",
                                "processo_sei",
                                "documento_sei_id",
                                "pagina_inicio",
                                "pagina_fim",
                            }
                        )
                        for hit in query.results
                    ],
                    "metrics": ranking_metrics(retrieved, case.relevant_ids or set(), k),
                }
            )

        timings = sorted(result["latency_ms"] for result in results)
        scored = [result["metrics"] for result in results if result["metrics"] is not None]
        runs[mode.value] = {
            "parameters": query.model_dump(exclude={"mode", "top_k", "results"}),
            "query_count": len(results),
            "labeled_query_count": len(scored),
            "median_latency_ms": median(timings),
            "p95_latency_ms": timings[ceil(len(timings) * 0.95) - 1],
            "mean_metrics": (
                {metric: fmean(row[metric] for row in scored) for metric in scored[0]}
                if scored
                else None
            ),
            "queries": results,
        }
    return {"k": k, "unit": unit, "modes": runs}


def main() -> None:
    cli = argparse.ArgumentParser(description="Compara recuperação do RAG por consulta anotada.")
    cli.add_argument("dataset", type=Path)
    cli.add_argument("--url", default="http://127.0.0.1:8010")
    cli.add_argument("--top-k", type=int, default=5, choices=range(1, 101), metavar="1..100")
    cli.add_argument("--unit", choices=["chunk_id", "documento_sei_id"], default="chunk_id")
    cli.add_argument(
        "--modes",
        nargs="+",
        type=RetrievalMode,
        choices=list(RetrievalMode),
        default=list(RetrievalMode),
    )
    cli.add_argument("--output", type=Path, default=PASTA_REPORTS / "evaluation.json")
    args = cli.parse_args()
    try:
        with args.dataset.open(encoding="utf-8") as stream:
            cases = [EvaluationCase.model_validate_json(line) for line in stream if line.strip()]
        if not cases or len({case.id for case in cases}) != len(cases):
            cli.error("Forneça pelo menos uma consulta e use IDs únicos.")
        with httpx.Client(base_url=args.url, timeout=180, trust_env=False) as client:
            report = evaluate(client, cases, args.modes, args.top_k, args.unit)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (ValueError, OSError, httpx.HTTPError):
        cli.exit(1, "Confira o JSONL, os modos habilitados na API e a pasta do relatório.\n")
    print(f"Relatório salvo para {len(cases)} consulta(s) e {len(args.modes)} modo(s).")


if __name__ == "__main__":
    main()
