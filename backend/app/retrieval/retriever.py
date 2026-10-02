"""Hybrid retrieval pipeline: dense + full-text → RRF → rerank → passages.

One entry point, `hybrid_search`, returns citable passages with source
metadata (ticker, company, filing, section) and optional neighbor chunks for
reading around a hit. No LLM involved — Phase 5 testability contract.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import embeddings
from app.config import settings
from app.retrieval import queries, reranker
from app.retrieval.fusion import reciprocal_rank_fusion

DEFAULT_HYBRID_LIMIT = 50
DEFAULT_TOP_K = 10
NEIGHBOR_WINDOW = 1  # chunks on each side of a hit

# RRF fuses candidates before reranking; the cross-encoder only sees this many.
RERANK_CANDIDATES = 50


@dataclass(frozen=True)
class RetrievedChunk:
    id: UUID
    document_id: UUID
    chunk_index: int
    page: int | None
    section: str | None
    chunk_text: str
    score: float
    score_source: str  # "rerank" | "rrf"
    metadata: dict[str, Any]


def _chunks_by_ids_sql() -> Any:
    return text("""
        SELECT c.id, c.document_id, c.chunk_index, c.page, c.section,
               c.chunk_text, c.metadata, c.token_count,
               s.ticker, s.company, s.filing_type, s.filing_date, s.fiscal_year,
               s.accession_number, s.source_url
        FROM document_chunks c
        JOIN source_documents s ON s.id = c.document_id
        WHERE c.id = ANY(:ids)
    """)


def _neighbors_sql() -> Any:
    return text("""
        SELECT c.id, c.document_id, c.chunk_index, c.chunk_text, c.section, c.page
        FROM document_chunks c
        WHERE c.document_id = :document_id
          AND c.chunk_index BETWEEN :lo AND :hi
        ORDER BY c.chunk_index
    """)


async def _fetch_chunks(
    session: AsyncSession, ids: list[UUID]
) -> dict[UUID, dict[str, Any]]:
    if not ids:
        return {}
    result = await session.execute(_chunks_by_ids_sql(), {"ids": list(ids)})
    return {row.id: dict(row._mapping) for row in result}


async def hybrid_search(
    session: AsyncSession,
    query: str,
    *,
    embed_model: Any = None,
    top_k: int = DEFAULT_TOP_K,
    with_neighbors: bool = False,
    ticker: str | None = None,
    fiscal_year: int | None = None,
) -> list[dict[str, Any]]:
    """Retrieve the top-k passages for a query.

    embed_model is a local CPU model; created in a worker thread when omitted so the
    function stays testable without network. When COHERE_API_KEY is unset,
    results keep their RRF order (score_source="rrf").
    """
    if not 1 <= top_k <= 100:
        raise ValueError("top_k must be between 1 and 100")
    if not query.strip():
        raise ValueError("query must not be empty")
    if embed_model is None:
        embed_model = await asyncio.to_thread(embeddings.create_model)

    # 1. Dense: embed the query with the same model/task as retrieval queries.
    query_vector = await embeddings.embed_query(embed_model, query)

    # AsyncSession owns one connection and cannot execute concurrent queries.
    filters = {"ticker": ticker, "fiscal_year": fiscal_year}
    dense_ids = await queries.dense_search(session, query_vector, **filters)
    fts_ids = await queries.full_text_search(session, query, **filters)

    # 3. Fuse ranks (RRF), then take the rerank pool.
    fused = reciprocal_rank_fusion(
        [[str(i) for i in dense_ids], [str(i) for i in fts_ids]],
        limit=max(top_k, RERANK_CANDIDATES),
    )
    if not fused:
        return []

    candidate_ids = [UUID(id_) for id_, _ in fused]
    chunks = await _fetch_chunks(session, candidate_ids)

    # 4. Rerank the candidate texts with the cross-encoder when configured.
    # Without a COHERE_API_KEY the call is skipped entirely (not just a no-op
    # inside the reranker) so the request path never touches the network.
    ordered: list[RetrievedChunk] = []
    texts = [chunks[id_]["chunk_text"] for id_ in candidate_ids if id_ in chunks]
    present_ids = [id_ for id_ in candidate_ids if id_ in chunks]
    rrf_scores = {UUID(id_): score for id_, score in fused}
    reranked = (
        await reranker.rerank(query, texts, top_k) if settings.cohere_api_key else None
    )
    if reranked is None:
        for id_ in present_ids:
            ordered.append(_to_chunk(chunks[id_], rrf_scores[id_], "rrf"))
        ordered.sort(key=lambda c: -c.score)
    else:
        for index, score in reranked:
            id_ = present_ids[index]
            ordered.append(_to_chunk(chunks[id_], score, "rerank"))

    results = ordered[:top_k]
    if with_neighbors:
        return [
            {**_chunk_dict(c), "neighbors": await _fetch_neighbors(session, c)}
            for c in results
        ]
    return [_chunk_dict(c) for c in results]


def _to_chunk(row: dict[str, Any], score: float, source: str) -> RetrievedChunk:
    return RetrievedChunk(
        id=row["id"],
        document_id=row["document_id"],
        chunk_index=row["chunk_index"],
        page=row["page"],
        section=row["section"],
        chunk_text=row["chunk_text"],
        score=score,
        score_source=source,
        metadata={
            **(row["metadata"] or {}),
            "ticker": row["ticker"],
            "company": row["company"],
            "filing_type": row["filing_type"],
            "filing_date": row["filing_date"].isoformat(),
            "fiscal_year": row["fiscal_year"],
            "accession_number": row["accession_number"],
            "source_url": row["source_url"],
        },
    )


def _chunk_dict(chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "chunk_index": chunk.chunk_index,
        "page": chunk.page,
        "section": chunk.section,
        "chunk_text": chunk.chunk_text,
        "score": chunk.score,
        "score_source": chunk.score_source,
        "metadata": chunk.metadata,
    }


async def _fetch_neighbors(
    session: AsyncSession, chunk: RetrievedChunk
) -> list[dict[str, Any]]:
    lo = chunk.chunk_index - NEIGHBOR_WINDOW
    hi = chunk.chunk_index + NEIGHBOR_WINDOW
    result = await session.execute(
        _neighbors_sql(),
        {"document_id": str(chunk.document_id), "lo": lo, "hi": hi},
    )
    return [
        {
            "id": str(row.id),
            "document_id": str(row.document_id),
            "page": row.page,
            "chunk_index": row.chunk_index,
            "section": row.section,
            "chunk_text": row.chunk_text,
        }
        for row in result
        if row.id != chunk.id
    ]
