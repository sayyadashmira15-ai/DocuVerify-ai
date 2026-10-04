from collections import defaultdict
import math
from typing import Dict, List

from backend.services.embeddings import create_query_embedding


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def retrieve_relevant_chunks(
    question: str,
    chunks: List[Dict],
    top_k: int = 5,
    min_score: float = 0.24,
    per_document_limit: int = 2,
) -> List[Dict]:
    if not chunks:
        return []

    query_vector = create_query_embedding(question)
    scored: List[Dict] = []

    for chunk in chunks:
        embedding = chunk.get("embedding")
        if not embedding:
            continue
        score = cosine_similarity(query_vector, embedding)
        if score >= min_score:
            scored.append({**chunk, "score": round(score, 4)})

    scored.sort(key=lambda item: item["score"], reverse=True)

    grouped = defaultdict(list)
    for item in scored:
        grouped[item.get("document", "Unknown")].append(item)

    results: List[Dict] = []
    while grouped and len(results) < top_k:
        progressed = False
        for document in list(grouped.keys()):
            if grouped[document]:
                candidate = grouped[document].pop(0)
                used = sum(1 for r in results if r.get("document") == document)
                if used < per_document_limit:
                    results.append(candidate)
                    progressed = True
                    if len(results) >= top_k:
                        break
            if not grouped[document]:
                del grouped[document]
        if not progressed:
            break

    results.sort(key=lambda item: item["score"], reverse=True)
    return results
