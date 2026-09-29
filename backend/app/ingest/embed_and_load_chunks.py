# /// script
# requires-python = ">=3.12"
# ///
"""Embed chunk JSONL rows and upsert them into document_chunks.

Reads data/chunks/chunks_hybrid.jsonl, embeds contextualized_text with the
configured Google embedding model (backend settings), and upserts one
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

from google import genai
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import DocumentChunk, SourceDocument
from app.database.models.constants import EMBEDDING_DIMENSIONS
from app.embeddings import embed_texts
from app.ingest.paths import CHUNKS_DIR

DEFAULT_INPUT = CHUNKS_DIR / "chunks_hybrid.jsonl"


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

    if args.smoke:
        first_accession = rows[0]["accession_number"]
        rows = [row for row in rows if row["accession_number"] == first_accession][:1]
        row = rows[0]
        print(
            f"SMOKE: embedding only {first_accession} chunk_index={row['chunk_index']} "
            f"(section={row['section']!r}, {row['token_count']} tokens)."
        )

    accession_numbers = list(dict.fromkeys(row["accession_number"] for row in rows))
    engine = create_engine(settings.sqlalchemy_database_url)
    client = genai.Client(api_key=settings.google_api_key)

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
        f"{settings.google_embedding_model} (dimensions={EMBEDDING_DIMENSIONS})..."
    )
    started = time.monotonic()
    vectors, billed_tokens = embed_texts(client, [row["contextualized_text"] for row in rows])
    if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
        raise SystemExit(
            f"{settings.google_embedding_model} returned vectors whose length is not "
            f"{EMBEDDING_DIMENSIONS}; refusing to insert into vector({EMBEDDING_DIMENSIONS})."
        )
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
            chunk = session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.document_id == document_ids[accession_numbers[0]],
                    DocumentChunk.chunk_index == rows[0]["chunk_index"],
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
    else:
        print(f"Done: {inserted} chunk row(s) across {len(accession_numbers)} document(s).")
    engine.dispose()


if __name__ == "__main__":
    main()
