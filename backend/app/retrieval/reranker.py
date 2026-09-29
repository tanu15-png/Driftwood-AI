"""Cross-encoder reranking via the Cohere Rerank API.

The bi-encoder retrievers (dense + full-text) embed query and document
independently; a cross-encoder sees both jointly and scores true relevance.
It is far more accurate per call but too slow to run over a whole corpus, so
it only re-scores the top hybrid candidates.

Called with httpx directly: the API is one POST endpoint, and the dependency
policy bars SDK wrappers for calls this small. Without COHERE_API_KEY the
reranker is a no-op (hybrid ranking passes through) so the pipeline still
works on keys alone.
"""

from __future__ import annotations

import httpx

from app.config import settings

RERANK_MODEL = "rerank-v4.0-fast"
RERANK_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 3


async def rerank(
    query: str,
    documents: list[str],
    limit: int,
) -> list[tuple[int, float]] | None:
    """Re-score documents against the query with the Cohere cross-encoder.

    Returns [(original_index, relevance_score)] best-first, or None when no
    COHERE_API_KEY is configured (caller keeps the hybrid order).
    """
    if not settings.cohere_api_key:
        return None
    if not documents:
        return []

    payload = {
        "model": RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": min(limit, len(documents)),
        "return_documents": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.cohere_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=RERANK_TIMEOUT_SECONDS) as client:
        response = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.post(
                    "https://api.cohere.com/v2/rerank", json=payload, headers=headers
                )
                response.raise_for_status()
                break
            except httpx.HTTPStatusError:
                raise  # 4xx/5xx are real errors, not transient transport issues
            except httpx.TransportError:
                if attempt == MAX_RETRIES - 1:
                    raise
        assert response is not None
        results = response.json()["results"]
    return [(item["index"], item["relevance_score"]) for item in results]
