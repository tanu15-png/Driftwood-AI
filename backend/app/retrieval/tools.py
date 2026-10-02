"""Bounded passage tools for the future assistant; no model-generated SQL."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.retriever import _chunk_dict, _fetch_chunks, _to_chunk, hybrid_search


async def search_filings(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 10,
    ticker: str | None = None,
    fiscal_year: int | None = None,
    embed_model: Any = None,
) -> list[dict[str, Any]]:
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    return await hybrid_search(
        session,
        query,
        top_k=limit,
        ticker=ticker,
        fiscal_year=fiscal_year,
        embed_model=embed_model,
    )


async def read_chunk(session: AsyncSession, chunk_id: UUID) -> dict[str, Any] | None:
    rows = await _fetch_chunks(session, [chunk_id])
    row = rows.get(chunk_id)
    return _chunk_dict(_to_chunk(row, 0.0, "rrf")) if row else None


async def read_surrounding_chunks(
    session: AsyncSession,
    chunk_id: UUID,
    *,
    window: int = 1,
) -> list[dict[str, Any]]:
    if not 0 <= window <= 3:
        raise ValueError("window must be between 0 and 3")
    rows = await _fetch_chunks(session, [chunk_id])
    if chunk_id not in rows:
        return []
    hit = rows[chunk_id]
    result = await session.execute(
        text("""
        SELECT id FROM document_chunks
        WHERE document_id = :document_id AND chunk_index BETWEEN :lo AND :hi
        ORDER BY chunk_index
    """),
        {
            "document_id": hit["document_id"],
            "lo": hit["chunk_index"] - window,
            "hi": hit["chunk_index"] + window,
        },
    )
    ids = [row.id for row in result]
    passages = await _fetch_chunks(session, ids)
    return [_chunk_dict(_to_chunk(passages[id_], 0.0, "rrf")) for id_ in ids]
