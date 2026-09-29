"""Unit tests for app.ingest.chunk_documents row building. No network, no DB."""

from __future__ import annotations

import pytest

from app.ingest import chunk_documents
from app.ingest.chunk_documents import (
    CharEstimateTokenizer,
    chunk_rows,
    estimate_tokens,
    section_from_headings,
)


def _entry(ticker: str = "AAPL") -> dict:
    return {
        "ticker": ticker,
        "form": "10-K",
        "filing_date": "2025-10-31",
        "report_date": "2025-09-27",
        "accession_number": "0000320193-25-000079",
        "source_url": "https://example.com/aapl.htm",
        "primary_document": "aapl-20250927.htm",
    }


def _row(headings: list[str] | None, text: str = "Apple revenue grew by five percent."):
    """Build a DocChunk with the minimal required metadata."""
    from docling_core.transforms.chunker.doc_chunk import DocChunk, DocMeta
    from docling_core.types.doc.document import DocItem
    from docling_core.types.doc.labels import DocItemLabel

    meta = DocMeta(
        doc_items=[DocItem(self_ref="#/texts/0", label=DocItemLabel.TEXT)], headings=headings
    )
    return DocChunk(text=text, meta=meta)


class _FakeHybridChunker:
    """Stands in for HybridChunker (initialized with CharEstimateTokenizer)."""

    def __init__(self, chunks):
        self._chunks = chunks
        self.tokenizer = CharEstimateTokenizer(max_tokens=chunk_documents.CHUNK_MAX_TOKENS)

    def chunk(self, dl_doc):
        return iter(self._chunks)

    def contextualize(self, chunk):
        headings = chunk.meta.headings or []
        return " > ".join(headings) + "\n" + chunk.text if headings else chunk.text


def test_section_joins_headings() -> None:
    assert section_from_headings(["Part II", "Item 7", "MD&A"]) == "Part II > Item 7 > MD&A"


def test_section_none_without_headings() -> None:
    assert section_from_headings(None) is None
    assert section_from_headings([]) is None


def test_section_truncates_to_column_limit() -> None:
    long = section_from_headings(["x" * 80] * 5)
    assert long is not None and len(long) <= 200


def test_char_estimate_tokenizer_is_conservative() -> None:
    tokenizer = CharEstimateTokenizer(max_tokens=800)
    assert tokenizer.count_tokens("") == 0
    assert tokenizer.count_tokens("abcd" * 100) == 100
    assert tokenizer.get_max_tokens() == 800
    # Estimate must over-count real tokens, never under-count (40 chars of
    # typical English is ~10 real tokens).
    assert estimate_tokens("The iPhone segment generated revenue of") >= 9


def test_chunk_rows_maps_metadata_and_orders_chunks() -> None:
    chunker = _FakeHybridChunker(
        [
            _row(["Part I", "Item 1"], "First chunk text."),
            _row(None, "Second chunk text."),
        ]
    )
    rows = chunk_rows(
        document=object(),  # chunker is faked; the document is never touched
        entry=_entry(),
        chunker_name="hybrid",
        chunker=chunker,  # type: ignore[arg-type]
    )
    assert [row["chunk_index"] for row in rows] == [0, 1]
    assert rows[0]["section"] == "Part I > Item 1"
    assert rows[1]["section"] is None
    assert rows[0]["page"] is None  # SEC HTML has no page structure
    assert rows[0]["chunker"] == "hybrid"
    # The fake chunker's contextualize() prepends the heading chain.
    assert rows[0]["contextualized_text"] == "Part I > Item 1\nFirst chunk text."
    assert rows[1]["contextualized_text"] == "Second chunk text."
    assert rows[0]["token_count"] == estimate_tokens("Part I > Item 1\nFirst chunk text.")
    meta = rows[0]["metadata"]
    assert meta["ticker"] == "AAPL"
    assert meta["fiscal_year"] == 2025
    assert meta["company"] == "Apple Inc."
    assert meta["filing_type"] == "10-K"
    assert meta["headings"] == ["Part I", "Item 1"]
    assert meta["doc_item_refs"] == ["#/texts/0"]
    assert meta["num_doc_items"] == 1


def test_chunk_target_stays_below_gemini_limit() -> None:
    """The chunk target must stay under the embedding model's input cap."""
    assert chunk_documents.CHUNK_MAX_TOKENS < chunk_documents.EMBEDDING_MODEL_TOKEN_LIMIT
