from collections import defaultdict

from app.schemas.query import Evidence


def reciprocal_rank_fusion(*rankings: list[Evidence], k: int = 60) -> list[Evidence]:
    scores: dict[str, float] = defaultdict(float)
    candidates: dict[str, Evidence] = {}
    for ranking in rankings:
        seen = set()
        for rank, candidate in enumerate(ranking, start=1):
            key = candidate.chunk_id
            if key in seen:
                continue
            seen.add(key)
            scores[key] += 1 / (k + rank)
            previous = candidates.get(key)
            candidates[key] = (
                candidate
                if previous is None
                else previous.model_copy(
                    update=candidate.model_dump(
                        include={"vector_score", "keyword_score", "exact_identifier_match"},
                        exclude_none=True,
                        exclude_defaults=True,
                    )
                )
            )

    return [
        candidates[key].model_copy(update={"rrf_score": scores[key]})
        for key in sorted(scores, key=lambda key: (-scores[key], key))
    ]
