"""pgvector + Postgres full-text queries over document_chunks.

Both searches return chunk ids ordered best-first. They run as two separate
queries so fusion happens in Python (RRF), per the stack decision in
AGENTS.md — no generated SQL, only bound parameters.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Candidate pools must exceed the final top-k so RRF has overlap to work with.
DENSE_CANDIDATES = 100
FTS_CANDIDATES = 100

# Cosine distance (pgvector vector_cosine_ops, matches the HNSW index) —
# vectors come back already L2-normalized from the local BGE model.
_DENSE_SQL = text("""
    SELECT c.id
    FROM document_chunks c
    JOIN source_documents s ON s.id = c.document_id
    WHERE embedding IS NOT NULL
      AND (CAST(:ticker AS text) IS NULL OR s.ticker = :ticker)
      AND (CAST(:fiscal_year AS integer) IS NULL OR s.fiscal_year = :fiscal_year)
    ORDER BY embedding <=> (:query_vector)::vector
    LIMIT :limit
""")

# websearch_to_tsquery: analyst-friendly syntax ("iPhone vs Services revenue",
# quoted phrases, OR, -exclusions) without writing tsquery expressions.
_FTS_SQL = text("""
    SELECT c.id
    FROM document_chunks c
    JOIN source_documents s ON s.id = c.document_id
    WHERE (CAST(:ticker AS text) IS NULL OR s.ticker = :ticker)
      AND (CAST(:fiscal_year AS integer) IS NULL OR s.fiscal_year = :fiscal_year)
      AND search_vector @@ websearch_to_tsquery('english', :query)
    ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery('english', :query)) DESC
    LIMIT :limit
""")


async def dense_search(
    session: AsyncSession,
    query_vector: list[float],
    limit: int = DENSE_CANDIDATES,
    *,
    ticker: str | None = None,
    fiscal_year: int | None = None,
) -> list[UUID]:
    result = await session.execute(
        _DENSE_SQL,
        {
            "query_vector": str(query_vector),
            "limit": limit,
            "ticker": ticker.upper() if ticker else None,
            "fiscal_year": fiscal_year,
        },
    )
    return [row.id for row in result]


async def full_text_search(
    session: AsyncSession,
    query: str,
    limit: int = FTS_CANDIDATES,
    *,
    ticker: str | None = None,
    fiscal_year: int | None = None,
) -> list[UUID]:
    result = await session.execute(
        _FTS_SQL,
        {
            "query": query,
            "limit": limit,
            "ticker": ticker.upper() if ticker else None,
            "fiscal_year": fiscal_year,
        },
    )
    return [row.id for row in result]
