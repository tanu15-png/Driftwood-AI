# /// script
# requires-python = ">=3.12"
# ///
"""Chunk docling DoclingDocuments with the Hierarchical and Hybrid chunkers.

Reads data/docling/manifest.json, chunks each DoclingDocument JSON with both
docling chunkers, and writes one JSONL row per chunk to
data/chunks/chunks_hybrid.jsonl and data/chunks/chunks_hierarchical.jsonl.

Row shape (JSON per line):
    accession_number  filing accession, to join against source_documents
    chunker           "hybrid" | "hierarchical"
    chunk_index       position of the chunk within its filing
    page              always null for HTML filings — SEC HTML has no real page
                      structure (verified: docling emits no provenance); the
                      column stays available for PDF ingestion later
    section           nearest heading chain ("Part II > Item 7 > ...")
    chunk_text        raw serialized chunk text
    contextualized_text  chunker.contextualize() output — headings prepended —
                      this is what gets embedded
    token_count       token count of contextualized_text in the embedding
                      model's tokenizer
    metadata          {ticker, fiscal_year, company, filing_date, headings,
                       captions, doc_item_refs, num_doc_items, source_url}

Token budget: the embedding model is read from backend settings and its hard
token limit is enforced by the docling tokenizer wrapper; max_tokens for the
chunker is set below it. No network calls, no cost — safe to re-run.

Run with the backend env:
    cd backend && uv run python -m app.ingest.chunk_documents
"""

from __future__ import annotations

import argparse
import json

import tiktoken
from docling_core.transforms.chunker.hierarchical_chunker import HierarchicalChunker
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.types.doc.document import DoclingDocument

from app.config import settings
from app.ingest.paths import CHUNKS_DIR, COMPANY_NAMES, DOCLING_DIR, DOCLING_MANIFEST

# HybridChunker token target (user decision). Must stay below the embedding
# model's hard limit; build_tokenizer enforces that.
CHUNK_MAX_TOKENS = 800
# document_chunks.embedding is vector(1536) — the settings value must match.
EMBEDDING_DIMENSIONS = 1536
# Hard token limit per OpenAI embedding model; the chunker target stays
# comfortably below it so heading context never pushes a chunk over.
EMBEDDING_MODEL_LIMITS = {"text-embedding-3-small": 8191, "text-embedding-3-large": 8191}
# Longest heading chain stored in document_chunks.section (column is 200 chars).
SECTION_MAX_CHARS = 200


def build_tokenizer(max_tokens: int) -> OpenAITokenizer:
    model = settings.openai_embedding_model
    if model not in EMBEDDING_MODEL_LIMITS:
        raise SystemExit(
            f"Unknown embedding model {model!r}; add its token limit to EMBEDDING_MODEL_LIMITS."
        )
    if max_tokens >= EMBEDDING_MODEL_LIMITS[model]:
        raise SystemExit(
            f"max_tokens {max_tokens} must stay below the {model} hard limit "
            f"of {EMBEDDING_MODEL_LIMITS[model]}."
        )
    if settings.openai_embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise SystemExit(
            f"OPENAI_EMBEDDING_DIMENSIONS={settings.openai_embedding_dimensions} but the "
            f"document_chunks.embedding column is vector({EMBEDDING_DIMENSIONS})."
        )
    encoding = tiktoken.encoding_for_model(model)
    return OpenAITokenizer(tokenizer=encoding, max_tokens=max_tokens)


def section_from_headings(headings: list[str] | None) -> str | None:
    if not headings:
        return None
    return " > ".join(headings)[-SECTION_MAX_CHARS:]


def chunk_rows(
    document: DoclingDocument,
    entry: dict,
    chunker_name: str,
    chunker: HierarchicalChunker | HybridChunker,
    tokenizer: OpenAITokenizer,
) -> list[dict]:
    rows = []
    for index, chunk in enumerate(chunker.chunk(dl_doc=document)):
        # contextualize() is the embedding-targeted serialization on every
        # BaseChunker; hybrid prepends headings, hierarchical's default
        # serialization is the plain text.
        contextualized = chunker.contextualize(chunk)
        meta = chunk.meta
        headings = list(meta.headings) if meta.headings else None
        captions = list(meta.captions) if meta.captions else None
        rows.append(
            {
                "accession_number": entry["accession_number"],
                "chunker": chunker_name,
                "chunk_index": index,
                "page": None,
                "section": section_from_headings(headings),
                "chunk_text": chunk.text,
                "contextualized_text": contextualized,
                "token_count": tokenizer.count_tokens(contextualized),
                "metadata": {
                    "ticker": entry["ticker"],
                    "fiscal_year": int(entry["report_date"][:4]),
                    "company": COMPANY_NAMES[entry["ticker"]],
                    "filing_type": entry["form"],
                    "filing_date": entry["filing_date"],
                    "headings": headings,
                    "captions": captions,
                    "doc_item_refs": [item.self_ref for item in meta.doc_items],
                    "num_doc_items": len(meta.doc_items),
                    "source_url": entry["source_url"],
                    "primary_document": entry["primary_document"],
                },
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=CHUNK_MAX_TOKENS,
        help="HybridChunker token target (default: 800; must stay below the embedding model limit)",
    )
    parser.add_argument(
        "--filter-accession",
        default=None,
        help="chunk only the filing with this accession number (debugging)",
    )
    args = parser.parse_args()

    if not DOCLING_MANIFEST.exists():
        raise SystemExit(
            f"No docling manifest at {DOCLING_MANIFEST}. "
            "Run app.ingest.convert_to_docling_json first."
        )
    manifest = json.loads(DOCLING_MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["filings"]
    if not entries:
        raise SystemExit("Manifest has no filings — nothing to chunk.")
    if args.filter_accession:
        entries = [e for e in entries if e["accession_number"] == args.filter_accession]
        if not entries:
            raise SystemExit(f"No filing with accession {args.filter_accession} in the manifest.")

    tokenizer = build_tokenizer(args.max_tokens)
    print(
        f"Chunking {len(entries)} filing(s) with HybridChunker (max_tokens={args.max_tokens}) "
        f"and HierarchicalChunker, tokenizer={settings.openai_embedding_model}."
    )

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    chunkers = {
        "hybrid": HybridChunker(tokenizer=tokenizer),
        "hierarchical": HierarchicalChunker(),
    }
    total = {"hybrid": 0, "hierarchical": 0}
    oversize = 0
    with open(CHUNKS_DIR / "chunks_hybrid.jsonl", "w", encoding="utf-8") as hybrid_handle, open(
        CHUNKS_DIR / "chunks_hierarchical.jsonl", "w", encoding="utf-8"
    ) as hierarchical_handle:
        handles = {"hybrid": hybrid_handle, "hierarchical": hierarchical_handle}
        for entry in entries:
            docling_path = DOCLING_DIR / entry["docling_path"]
            if not docling_path.exists():
                raise SystemExit(
                    f"Missing docling JSON for {entry['accession_number']}: {docling_path}"
                )
            document = DoclingDocument.load_from_json(docling_path)
            per_filing = {}
            for name, chunker in chunkers.items():
                rows = chunk_rows(document, entry, name, chunker, tokenizer)
                for row in rows:
                    handles[name].write(json.dumps(row, ensure_ascii=False) + "\n")
                per_filing[name] = len(rows)
                total[name] += len(rows)
                if name == "hybrid":
                    oversize += sum(1 for row in rows if row["token_count"] > args.max_tokens)
            print(
                f"{entry['accession_number']}: {per_filing['hybrid']} hybrid + "
                f"{per_filing['hierarchical']} hierarchical chunks"
            )

    print(
        f"Wrote {total['hybrid']} hybrid + {total['hierarchical']} hierarchical chunks "
        f"to {CHUNKS_DIR} ({oversize} hybrid chunks over the token budget)."
    )
    if oversize:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
