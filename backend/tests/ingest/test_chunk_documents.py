"""Unit tests for app.ingest.chunk_documents row building. No network, no DB."""

from __future__ import annotations

import json

import pytest

from app.ingest import chunk_documents
from app.ingest.chunk_documents import (
    chunk_rows,
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


class _FakeTokenizer:
    def count_tokens(self, text):
        return len(text.split())


class _FakeHybridChunker:
    """A deterministic parser/tokenizer boundary, with no model download."""

    def __init__(self, chunks):
        self._chunks = chunks
        self.tokenizer = _FakeTokenizer()

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


def test_chunk_target_reserves_special_token_space() -> None:
    assert chunk_documents.CHUNK_MAX_TOKENS == 480
    assert chunk_documents.EMBEDDING_MODEL_TOKEN_LIMIT == 512


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
        tokenizer=chunker.tokenizer,
    )
    assert [row["chunk_index"] for row in rows] == [0, 1]
    assert rows[0]["section"] == "Part I > Item 1"
    assert rows[1]["section"] is None
    assert rows[0]["page"] is None  # SEC HTML has no page structure
    assert rows[0]["chunker"] == "hybrid"
    # The fake chunker's contextualize() prepends the heading chain.
    assert rows[0]["contextualized_text"] == "Part I > Item 1\nFirst chunk text."
    assert rows[1]["contextualized_text"] == "Second chunk text."
    assert rows[0]["token_count"] == 8
    meta = rows[0]["metadata"]
    assert meta["page"] is None
    assert meta["section"] == "Part I > Item 1"
    assert meta["offsets"] is None
    assert meta["ticker"] == "AAPL"
    assert meta["fiscal_year"] == 2025
    assert meta["company"] == "Apple Inc."
    assert meta["filing_type"] == "10-K"
    assert meta["headings"] == ["Part I", "Item 1"]
    assert meta["doc_item_refs"] == ["#/texts/0"]
    assert meta["num_doc_items"] == 1


def test_chunk_target_stays_below_model_limit() -> None:
    """The chunk target must stay under the embedding model's input cap."""
    assert chunk_documents.CHUNK_MAX_TOKENS < chunk_documents.EMBEDDING_MODEL_TOKEN_LIMIT


@pytest.mark.parametrize("tokens, fits", [(500, True), (511, False)])
def test_publication_enforces_model_limit_not_target(monkeypatch, tmp_path, tokens, fits):
    docling = tmp_path / "docling"
    docling.mkdir()
    (docling / "filing.json").write_text("{}")
    manifest = docling / "manifest.json"
    manifest.write_text(json.dumps({"filings": [{**_entry(), "docling_path": "filing.json"}]}))
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    previous = chunks / "chunks_hybrid.jsonl"
    previous.write_text("previous corpus")
    monkeypatch.setattr(chunk_documents, "DOCLING_DIR", docling)
    monkeypatch.setattr(chunk_documents, "DOCLING_MANIFEST", manifest)
    monkeypatch.setattr(chunk_documents, "CHUNKS_DIR", chunks)
    monkeypatch.setattr(chunk_documents, "create_tokenizer", lambda **kwargs: _FakeTokenizer())
    monkeypatch.setattr(chunk_documents.DoclingDocument, "load_from_json", lambda path: object())
    fake = _FakeHybridChunker([_row(None, "word " * tokens)])
    monkeypatch.setattr(chunk_documents, "HybridChunker", lambda **kwargs: fake)
    monkeypatch.setattr(chunk_documents, "HierarchicalChunker", lambda: fake)
    monkeypatch.setattr("sys.argv", ["chunk_documents"])
    if fits:
        chunk_documents.main()
        assert json.loads(previous.read_text())["token_count"] == tokens
    else:
        with pytest.raises(SystemExit):
            chunk_documents.main()
        assert previous.read_text() == "previous corpus"
