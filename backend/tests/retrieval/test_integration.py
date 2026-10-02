"""Live corpus retrieval, explicitly enabled with pytest -m integration."""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.retrieval.queries import full_text_search
from app.retrieval.retriever import hybrid_search
from app.retrieval.tools import read_chunk, read_surrounding_chunks

pytestmark = pytest.mark.integration


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_apple_revenue_passages_are_citable() -> None:
    engine = create_async_engine(settings.sqlalchemy_database_url)
    try:
        async with AsyncSession(engine) as session:
            counts = (
                await session.execute(
                    text("""
                SELECT count(DISTINCT s.id) documents, count(c.id) chunks,
                       count(c.embedding) embeddings, count(c.search_vector) vectors
                FROM source_documents s
                LEFT JOIN document_chunks c ON c.document_id = s.id
            """)
                )
            ).one()
            assert counts.documents == 25
            assert counts.chunks > 25
            assert counts.embeddings == counts.vectors == counts.chunks
            mismatched_models = await session.scalar(
                text("""
                SELECT count(*) FROM document_chunks
                WHERE metadata->>'embedding_model' IS DISTINCT FROM :model
                   OR metadata->>'embedding_dimensions' IS DISTINCT FROM '384'
            """),
                {"model": settings.embedding_model},
            )
            assert mismatched_models == 0
            missing = (
                await session.execute(
                    text("""
                SELECT s.accession_number FROM source_documents s
                LEFT JOIN document_chunks c ON c.document_id = s.id
                GROUP BY s.id HAVING count(c.id) = 0
            """)
                )
            ).all()
            assert missing == []
            keyword_ids = await full_text_search(
                session, "iPhone Services", ticker="AAPL"
            )
            assert keyword_ids
            passages = await hybrid_search(
                session,
                "Apple iPhone vs Services revenue mix",
                ticker="AAPL",
                top_k=10,
            )
            assert passages
            assert all(p["metadata"]["ticker"] == "AAPL" for p in passages)
            assert all(p["metadata"]["source_url"] for p in passages)
            assert any(
                "iphone" in p["chunk_text"].lower()
                and "services" in p["chunk_text"].lower()
                for p in passages
            )
            chunk_id = UUID(passages[0]["id"])
            passage = await read_chunk(session, chunk_id)
            assert passage["chunk_text"] == passages[0]["chunk_text"]
            neighbors = await read_surrounding_chunks(session, chunk_id)
            assert 1 <= len(neighbors) <= 3
            assert all(p["document_id"] == passage["document_id"] for p in neighbors)
    finally:
        await engine.dispose()
