# /// script
# requires-python = ">=3.12"
# ///
"""Embed chunk JSONL rows and upsert them into document_chunks.

Reads data/chunks/chunks_hybrid.jsonl, embeds contextualized_text with the
configured OpenAI embedding model (backend settings), and upserts one
document_chunks row per chunk. Idempotent: existing chunks for a document
are deleted before its rows are inserted, so re-running never duplicates.

search_vector needs no population — it is a generated tsvector column filled
by Postgres from chunk_text on insert.

Run the cheap end-to-end check FIRST (one chunk embedded, one row inserted,
the row printed back) before spending on the full corpus:

    cd backend && uv run python -m app.ingest.embed_and_load_chunks --smoke
    cd backend && uv run python -m app.ingest.embed_and_load_chunks
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from openai import OpenAI
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import DocumentChunk, SourceDocument
from app.database.models.constants import EMBEDDING_DIMENSIONS
from app.ingest.paths import CHUNKS_DIR

DEFAULT_INPUT = CHUNKS_DIR / "chunks_hybrid.jsonl"
EMBED_BATCH_SIZE = 100
MAX_RETRIES = 5
REQUEST_TIMEOUT_SECONDS = 120.0


def embed_texts(client: OpenAI, texts: list[str]) -> tuple[list[list[float]], int]:
    """Embed texts in batches, retrying rate limits with exponential backoff.

    Returns (vectors in input order, total billed tokens).
    """
    vectors: list[list[float]] = []
    billed_tokens = 0
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.embeddings.create(
                    model=settings.openai_embedding_model,
                    dimensions=settings.openai_embedding_dimensions,
                    input=batch,
                )
                break
            except Exception as error:  # script boundary: retry transient failures, re-raise the rest
                if attempt == MAX_RETRIES - 1:
                    raise
                wait = 2**attempt * 2
                print(f"  embed batch failed ({error}); retry {attempt + 1} in {wait}s")
                time.sleep(wait)
        assert response is not None
        billed_tokens += response.usage.total_tokens
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        print(f"  embedded {min(start + EMBED_BATCH_SIZE, len(texts))}/{len(texts)}")
    return vectors, billed_tokens


def select_smoke_rows(rows: list[dict]) -> list[dict]:
    """The first chunk of the first filing only — the cost gate."""
    first_accession = rows[0]["accession_number"]
    smoke_rows = [row for row in rows if row["accession_number"] == first_accession][:1]
    row = smoke_rows[0]
    print(
        f"SMOKE: embedding only {first_accession} chunk_index={row['chunk_index']} "
        f"(section={row['section']!r}, {row['token_count']} tokens)."
    )
    return smoke_rows


def print_smoke_row(session: Session, document_id, chunk_index: int) -> None:
    chunk = session.execute(
        select(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.chunk_index == chunk_index,
        )
    ).scalar_one()
    embedding = list(chunk.embedding)
    print(
        "SMOKE row verified:\n"
        f"  id={chunk.id}\n"
        f"  document_id={chunk.document_id}\n"
        f"  chunk_index={chunk.chunk_index} page={chunk.page} "
        f"section={chunk.section!r}\n"
        f"  token_count={chunk.token_count} "
        f"embedding_dims={len(embedding)} (column is vector({EMBEDDING_DIMENSIONS}))\n"
        f"  search_vector populated: {chunk.search_vector is not None}\n"
        f"  metadata keys: {sorted(chunk.chunk_metadata)}\n"
        f"  chunk_text head: {chunk.chunk_text[:100]!r}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT), help="chunk JSONL to embed+load")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="embed ONE chunk from the FIRST filing and insert it — the pre-flight cost gate",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"No chunk file at {input_path}. Run app.ingest.chunk_documents first.")
    with open(input_path, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if not rows:
        raise SystemExit(f"{input_path} has no rows — run app.ingest.chunk_documents first.")
    if settings.openai_embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise SystemExit(
            f"OPENAI_EMBEDDING_DIMENSIONS={settings.openai_embedding_dimensions} but the "
            f"document_chunks.embedding column is vector({EMBEDDING_DIMENSIONS})."
        )

    if args.smoke:
        rows = select_smoke_rows(rows)

    accession_numbers = list(dict.fromkeys(row["accession_number"] for row in rows))
    engine = create_engine(settings.sqlalchemy_database_url)
    client = OpenAI(api_key=settings.openai_api_key, timeout=REQUEST_TIMEOUT_SECONDS)

    with Session(engine) as session:
        document_ids = {}
        for accession in accession_numbers:
            document_id = session.execute(
                select(SourceDocument.id).where(SourceDocument.accession_number == accession)
            ).scalar_one_or_none()
            if document_id is None:
                raise SystemExit(
                    f"No source_documents row for {accession} — "
                    "run app.ingest.load_source_documents first."
                )
            document_ids[accession] = document_id

    print(
        f"Embedding {len(rows)} chunk(s) from {len(accession_numbers)} filing(s) with "
        f"{settings.openai_embedding_model} (dimensions={settings.openai_embedding_dimensions})..."
    )
    started = time.monotonic()
    vectors, billed_tokens = embed_texts(client, [row["contextualized_text"] for row in rows])
    print(f"Embedded in {time.monotonic() - started:.1f}s ({billed_tokens} tokens billed).")

    rows_by_document: dict[object, list[tuple[dict, list[float]]]] = {}
    for row, vector in zip(rows, vectors, strict=True):
        rows_by_document.setdefault(document_ids[row["accession_number"]], []).append((row, vector))

    with Session(engine) as session:
        inserted = 0
        for document_id, document_rows in rows_by_document.items():
            # Delete-then-insert keeps re-runs idempotent; the unique
            # (document_id, chunk_index) constraint is the safety net.
            session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
            for row, vector in document_rows:
                session.add(
                    DocumentChunk(
                        document_id=document_id,
                        chunk_index=row["chunk_index"],
                        page=row["page"],
                        section=row["section"],
                        chunk_text=row["chunk_text"],
                        embedding=vector,
                        token_count=row["token_count"],
                        chunk_metadata=row["metadata"],
                    )
                )
            inserted += len(document_rows)
            session.commit()
            print(f"  inserted {inserted}/{len(rows)}")

    if args.smoke:
        with Session(engine) as session:
            print_smoke_row(session, document_ids[accession_numbers[0]], rows[0]["chunk_index"])
    else:
        print(f"Done: {inserted} chunk row(s) across {len(accession_numbers)} document(s).")
    engine.dispose()


if __name__ == "__main__":
    main()
