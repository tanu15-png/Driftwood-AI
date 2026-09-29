"""Gemini embedding client shared by ingest and retrieval.

Both corpus chunks and user queries must embed with the same model and
dimensions, so there is exactly one place that talks to the embeddings API.
Query and document embeddings use Gemini's task types for better retrieval
quality (RETRIEVAL_QUERY vs RETRIEVAL_DOCUMENT).

The google-genai SDK reads GOOGLE_API_KEY / GEMINI_API_KEY from the
environment on its own; settings mirrors it here instead of sprinkling
os.environ access around.
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

from google import genai

from app.config import settings
from app.database.models.constants import EMBEDDING_DIMENSIONS

EMBED_BATCH_SIZE = 100
MAX_RETRIES = 5
REQUEST_TIMEOUT_SECONDS = 120.0

TaskType = Literal["RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"]


def _client() -> genai.Client:
    return genai.Client(
        api_key=settings.google_api_key,
        http_options=genai.types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000),
    )


def embed_texts(
    client: genai.Client,
    texts: list[str],
    task_type: TaskType = "RETRIEVAL_DOCUMENT",
) -> tuple[list[list[float]], int]:
    """Embed texts in batches, retrying transient failures with backoff.

    Returns (vectors in input order, total billed tokens).
    """
    vectors: list[list[float]] = []
    billed_tokens = 0
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.embed_content(
                    model=settings.google_embedding_model,
                    contents=batch,
                    config=genai.types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=EMBEDDING_DIMENSIONS,
                    ),
                )
                break
            except Exception as error:  # script boundary: retry transient failures, re-raise the rest
                if attempt == MAX_RETRIES - 1:
                    raise
                wait = 2**attempt * 2
                print(f"  embed batch failed ({error}); retry {attempt + 1} in {wait}s")
                time.sleep(wait)
        assert response is not None and response.embeddings is not None
        embeddings = response.embeddings
        if len(embeddings) != len(batch):
            raise RuntimeError(
                f"Embedding API returned {len(embeddings)} vectors for {len(batch)} inputs"
            )
        vectors.extend(item.values or [] for item in embeddings)
        stats = getattr(response, "embed_content_statistics", None)
        if stats is not None and stats.token_count is not None:
            billed_tokens += int(stats.token_count)
    return vectors, billed_tokens


async def embed_query(client: genai.Client, query: str) -> list[float]:
    """Embed a single user query with the RETRIEVAL_QUERY task type.

    Async because it runs in the request path; the SDK's native async client
    is used rather than a thread offload.
    """
    response = await client.aio.models.embed_content(
        model=settings.google_embedding_model,
        contents=[query],
        config=genai.types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    if response.embeddings is None or not response.embeddings:
        raise RuntimeError("Embedding API returned no vectors for the query")
    values = response.embeddings[0].values
    if not values:
        raise RuntimeError("Embedding API returned an empty vector for the query")
    return list(values)


def embed_query_sync(client: genai.Client, query: str) -> list[float]:
    """Sync twin of embed_query for scripts and integration tests."""
    vectors, _ = embed_texts(client, [query], task_type="RETRIEVAL_QUERY")
    return vectors[0]


def verify_dimensions(client: genai.Client) -> None:
    """Fail fast if the configured model no longer matches vector(1536)."""
    vectors, _ = embed_texts(client, ["dimension probe"])
    if len(vectors[0]) != EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            f"{settings.google_embedding_model} returned {len(vectors[0])} dimensions; "
            f"document_chunks.embedding is vector({EMBEDDING_DIMENSIONS})."
        )
