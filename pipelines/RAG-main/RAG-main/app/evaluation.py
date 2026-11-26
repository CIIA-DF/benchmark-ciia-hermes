from math import log2


def ranking_metrics(
    retrieved: list[str | None], relevant: set[str], k: int
) -> dict[str, float] | None:
    if not relevant:
        return None
    seen = set()
    hits = []
    for rank, item in enumerate(retrieved[:k], start=1):
        if item is not None and item in relevant and item not in seen:
            seen.add(item)
            hits.append(rank)
    ideal = sum(1 / log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return {
        "recall_at_k": len(hits) / len(relevant),
        "hit_rate_at_k": float(bool(hits)),
        "mrr_at_k": 1 / hits[0] if hits else 0.0,
        "ndcg_at_k": sum(1 / log2(rank + 1) for rank in hits) / ideal,
    }
