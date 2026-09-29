"""Integration tests for app.ingest.embed_and_load_chunks.

Hit the live Google (Gemini) embeddings API — run explicitly:
    uv run pytest -m integration
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_embed_texts_returns_ordered_vectors_and_usage() -> None:
    from google import genai

    from app.config import settings
    from app.embeddings import embed_texts
    from app.database.models.constants import EMBEDDING_DIMENSIONS

    client = genai.Client(api_key=settings.google_api_key)
    vectors, billed_tokens = embed_texts(
        client, ["Apple revenue grew by five percent.", "NVIDIA sells data center GPUs."]
    )
    assert len(vectors) == 2
    assert all(len(vector) == EMBEDDING_DIMENSIONS for vector in vectors)
    assert billed_tokens > 0
    # Distinct inputs get distinct vectors; order matches input order.
    assert vectors[0] != vectors[1]
