"""Integration tests for app.ingest.embed_and_load_chunks.

Hit the live OpenAI embeddings API — run explicitly:
    uv run pytest -m integration
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_embed_texts_returns_ordered_vectors_and_usage() -> None:
    from openai import OpenAI

    from app.config import settings
    from app.ingest.embed_and_load_chunks import embed_texts

    client = OpenAI(api_key=settings.openai_api_key)
    vectors, billed_tokens = embed_texts(
        client, ["Apple revenue grew by five percent.", "NVIDIA sells data center GPUs."]
    )
    assert len(vectors) == 2
    assert all(len(vector) == settings.openai_embedding_dimensions for vector in vectors)
    assert billed_tokens > 0
    # Distinct inputs get distinct vectors; order matches input order.
    assert vectors[0] != vectors[1]
