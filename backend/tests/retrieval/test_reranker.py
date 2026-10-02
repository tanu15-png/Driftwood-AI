"""Unit tests for app.retrieval.reranker. httpx transport is mocked."""

from __future__ import annotations

import httpx
import pytest

from app.retrieval import reranker


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


async def test_rerank_without_api_key_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reranker.settings, "cohere_api_key", "")
    assert await reranker.rerank("q", ["a", "b"], 2) is None


async def test_rerank_empty_documents_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reranker.settings, "cohere_api_key", "key")
    assert await reranker.rerank("q", [], 5) == []


async def test_rerank_posts_payload_and_maps_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reranker.settings, "cohere_api_key", "key")
    captured: dict = {}

    async def fake_post(self, url, json=None, headers=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(
            {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.1},
                ]
            }
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    result = await reranker.rerank("query", ["doc0", "doc1"], 2)

    assert captured["url"] == "https://api.cohere.com/v2/rerank"
    assert captured["json"]["model"] == reranker.RERANK_MODEL
    assert captured["json"]["documents"] == ["doc0", "doc1"]
    assert result == [(1, 0.9), (0, 0.1)]


async def test_rerank_caps_top_n_at_document_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reranker.settings, "cohere_api_key", "key")
    captured: dict = {}

    async def fake_post(self, url, json=None, headers=None):
        captured["json"] = json
        return _FakeResponse({"results": []})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await reranker.rerank("q", ["a"], 10)
    assert captured["json"]["top_n"] == 1
