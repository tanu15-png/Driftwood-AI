"""Integration tests for app.ingest.embed_and_load_chunks.

Run real local CPU model inference and database checks explicitly:
    uv run pytest -m integration
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_local_embedding_vectors_are_normalized_and_distinct() -> None:
    import math

    from app.database.models.constants import EMBEDDING_DIMENSIONS
    from app.embeddings import create_model, embed_texts

    vectors = embed_texts(
        create_model(),
        ["Apple revenue grew by five percent.", "NVIDIA sells data center GPUs."],
    )
    assert len(vectors) == 2
    assert all(len(vector) == EMBEDDING_DIMENSIONS for vector in vectors)
    assert all(math.isclose(sum(x*x for x in v), 1.0, abs_tol=1e-5) for v in vectors)
    # Distinct inputs get distinct vectors; order matches input order.
    assert vectors[0] != vectors[1]


def test_reingest_and_smoke_preserve_chunk_ids(monkeypatch, tmp_path) -> None:
    """Reuse stored vectors to isolate database idempotency from CPU inference."""
    import json
    import sys

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.config import settings
    from app.database.models import DocumentChunk, SourceDocument
    from app.ingest import embed_and_load_chunks as loader

    engine = create_engine(settings.sqlalchemy_database_url)
    try:
        with Session(engine) as session:
            document = session.execute(
                select(SourceDocument)
                .order_by(SourceDocument.accession_number)
                .limit(1)
            ).scalar_one()
            chunks = (
                session.execute(
                    select(DocumentChunk)
                    .where(DocumentChunk.document_id == document.id)
                    .order_by(DocumentChunk.chunk_index)
                )
                .scalars()
                .all()
            )
            assert len(chunks) > 1
            original_ids = [c.id for c in chunks]
            document_id = document.id
            rows = [
                {
                    "accession_number": document.accession_number,
                    "chunk_index": c.chunk_index,
                    "page": c.page,
                    "section": c.section,
                    "chunk_text": c.chunk_text,
                    "contextualized_text": c.chunk_text,
                    "token_count": c.token_count,
                    "metadata": c.chunk_metadata,
                }
                for c in chunks
            ]
            vectors = [list(c.embedding) for c in chunks]
        input_path = tmp_path / "chunks.jsonl"
        input_path.write_text(
            "\n".join(json.dumps(row) for row in rows), encoding="utf-8"
        )
        monkeypatch.setattr(
            loader, "embed_texts", lambda model, texts: vectors[: len(texts)]
        )
        monkeypatch.setattr(loader, "create_model", lambda: object())
        for mode in ([], ["--smoke"]):
            monkeypatch.setattr(
                sys, "argv", ["ingest", "--input", str(input_path), *mode]
            )
            loader.main()
            with Session(engine) as session:
                ids = (
                    session.execute(
                        select(DocumentChunk.id)
                        .where(DocumentChunk.document_id == document_id)
                        .order_by(DocumentChunk.chunk_index)
                    )
                    .scalars()
                    .all()
                )
                assert ids == original_ids
    finally:
        engine.dispose()
