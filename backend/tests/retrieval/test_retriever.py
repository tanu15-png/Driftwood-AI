"""Unit tests for app.retrieval.retriever. Embedding, DB, and reranker mocked."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from app.retrieval import retriever


class _FakeRow:
    """Mimics a SQLAlchemy Row: attribute access plus the _mapping view."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getattr__(self, name: str):
        return self._data[name]

    @property
    def _mapping(self) -> dict:
        return self._data


class _FakeResult:
    """SQLAlchemy execute() stand-in over pre-built row mappings.

    SQLAlchemy's buffered Result is synchronously iterable (rows are already
    fetched over the wire), so app code iterates it without await.
    """

    def __init__(self, rows: list[dict]) -> None:
        self._rows = [_FakeRow(row) for row in rows]

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    """Routes ANY() chunk lookups to a fixture table; records bound params."""

    def __init__(self, chunk_rows: list[dict], neighbor_rows: list[dict]) -> None:
        self._chunk_rows = chunk_rows
        self._neighbor_rows = neighbor_rows
        self.executed: list[tuple[str, dict]] = []

    async def execute(self, sql, params=None):
        statement = str(sql)
        self.executed.append((statement, params or {}))
        if "JOIN source_documents" in statement:
            wanted = set(params["ids"])
            return _FakeResult([r for r in self._chunk_rows if r["id"] in wanted])
        if "BETWEEN" in statement:
            rows = [
                r
                for r in self._neighbor_rows
                if str(r["document_id"]) == str(params["document_id"])
                and params["lo"] <= r["chunk_index"] <= params["hi"]
            ]
            return _FakeResult(rows)
        raise AssertionError(f"Unexpected SQL in test: {statement}")


def _chunk_row(chunk_id, document_id, index: int, text: str) -> dict:
    return {
        "id": chunk_id,
        "document_id": document_id,
        "chunk_index": index,
        "page": None,
        "section": "Item 7",
        "chunk_text": text,
        "metadata": {"headings": ["Item 7"]},
        "token_count": 10,
        "ticker": "AAPL",
        "company": "Apple Inc.",
        "filing_type": "10-K",
        "filing_date": date(2025, 10, 31),
        "fiscal_year": 2025,
        "accession_number": "0000320193-25-000079",
        "source_url": "https://example.com/aapl.htm",
    }


@pytest.fixture()
def stub_pipeline(monkeypatch: pytest.MonkeyPatch):
    """Patch query embedding + both searches + reranker; returns knobs.

    Tests set calls["dense_ids"] (ids present in the fake chunk table) and
    calls["first_dense_id"] (the id FTS shares so it fuses to the top).
    """
    monkeypatch.setattr(retriever.settings, "cohere_api_key", "")
    calls: dict = {"query": None, "rerank_called": False}

    async def fake_embed_query(client, query: str) -> list[float]:
        calls["query"] = query
        return [0.1] * 8

    async def fake_dense(session, vector, limit=100, **filters):
        calls["dense_filters"] = filters
        return list(calls.get("dense_ids", []))

    async def fake_fts(session, query, limit=100, **filters):
        calls["fts_filters"] = filters
        # Dense and FTS agree on the first id — that one must fuse to the top.
        return [calls["first_dense_id"], uuid4()]

    async def fake_rerank(query, documents, limit):
        calls["rerank_called"] = True

    monkeypatch.setattr(retriever.embeddings, "embed_query", fake_embed_query)
    monkeypatch.setattr(retriever.queries, "dense_search", fake_dense)
    monkeypatch.setattr(retriever.queries, "full_text_search", fake_fts)
    monkeypatch.setattr(retriever.reranker, "rerank", fake_rerank)
    return calls


async def test_hybrid_search_returns_metadata_and_rrf_order(stub_pipeline) -> None:
    doc_id = uuid4()
    ids = [uuid4(), uuid4(), uuid4()]
    chunk_rows = [_chunk_row(id_, doc_id, i, f"text {i}") for i, id_ in enumerate(ids)]
    session = _FakeSession(chunk_rows, neighbor_rows=[])
    stub_pipeline["dense_ids"] = ids
    stub_pipeline["first_dense_id"] = ids[0]

    results = await retriever.hybrid_search(
        session, "apple revenue mix", embed_model=object()
    )

    assert stub_pipeline["rerank_called"] is False  # no-key path keeps RRF
    assert len(results) == 3
    first = results[0]
    assert first["score_source"] == "rrf"
    assert first["id"] == str(ids[0])  # in both lists → fused top
    assert first["metadata"]["ticker"] == "AAPL"
    assert first["metadata"]["filing_date"] == "2025-10-31"
    assert first["metadata"]["company"] == "Apple Inc."
    assert first["chunk_text"].startswith("text ")


async def test_hybrid_search_with_neighbors_includes_adjacent_chunks(
    stub_pipeline,
) -> None:
    doc_id = uuid4()
    ids = [uuid4(), uuid4(), uuid4()]
    chunk_rows = [_chunk_row(id_, doc_id, i, f"text {i}") for i, id_ in enumerate(ids)]
    neighbor_rows = [
        {
            "id": id_,
            "document_id": doc_id,
            "chunk_index": i,
            "section": "Item 7",
            "page": None,
            "chunk_text": f"text {i}",
        }
        for i, id_ in enumerate(ids)
    ]
    session = _FakeSession(chunk_rows, neighbor_rows)
    stub_pipeline["dense_ids"] = ids
    stub_pipeline["first_dense_id"] = ids[0]

    results = await retriever.hybrid_search(
        session,
        "apple revenue mix",
        embed_model=object(),
        with_neighbors=True,
        top_k=1,
    )

    assert len(results) == 1
    neighbors = results[0]["neighbors"]
    # Neighbor window ±1 around chunk 0, excluding itself: only chunk 1.
    assert [n["chunk_index"] for n in neighbors] == [1]
    assert neighbors[0]["chunk_text"] == "text 1"


async def test_hybrid_search_empty_candidates_returns_empty(stub_pipeline) -> None:
    async def no_dense(session, vector, limit=100, **filters):
        return []

    async def no_fts(session, query, limit=100, **filters):
        return []

    from unittest.mock import patch

    with (
        patch.object(retriever.queries, "dense_search", no_dense),
        patch.object(retriever.queries, "full_text_search", no_fts),
    ):
        results = await retriever.hybrid_search(
            _FakeSession([], []), "anything", embed_model=object()
        )

    assert results == []


async def test_filters_reach_both_searches(stub_pipeline) -> None:
    stub_pipeline["dense_ids"] = []
    stub_pipeline["first_dense_id"] = uuid4()
    await retriever.hybrid_search(
        _FakeSession([], []),
        "revenue",
        embed_model=object(),
        ticker="AAPL",
        fiscal_year=2025,
    )
    assert stub_pipeline["dense_filters"] == {"ticker": "AAPL", "fiscal_year": 2025}
    assert stub_pipeline["fts_filters"] == stub_pipeline["dense_filters"]


async def test_blank_query_is_rejected_before_embedding(stub_pipeline) -> None:
    with pytest.raises(ValueError, match="query"):
        await retriever.hybrid_search(_FakeSession([], []), "  ", embed_model=object())
    assert stub_pipeline["query"] is None
