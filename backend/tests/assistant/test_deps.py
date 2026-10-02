from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.assistant.agent import create_agent
from app.assistant.deps import DocumentAgentDeps, DocumentRetriever
from app.auth.dependencies import CurrentUser
from app.grounding.validator import GroundingValidator


async def test_neighbor_tool_cannot_read_an_unknown_chunk(monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr("app.assistant.deps.tools.read_surrounding_chunks", fetch)
    retriever = DocumentRetriever(None, None)
    assert await retriever.neighbors(uuid4()) == []
    fetch.assert_not_awaited()


async def test_agent_search_passes_bounded_filters():
    search = AsyncMock(return_value=[])
    retriever = SimpleNamespace(
        passages={}, search=search,
        embed_model=SimpleNamespace(tokenizer=SimpleNamespace(count_tokens=lambda text: 10)),
    )
    calls = []

    async def respond(messages, info):
        calls.append(messages)
        assert {t.name for t in info.function_tools} == {
            "search_filings", "read_chunk", "read_surrounding_chunks"
        }
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart("search_filings", {
                "query": "Apple net sales", "ticker": "AAPL", "fiscal_year": 2024,
            })])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "claims": [], "citations": [], "refusal_reason": "insufficient_evidence",
        })])

    deps = DocumentAgentDeps(
        CurrentUser(uuid4(), "test@example.com"), uuid4(), retriever, GroundingValidator()
    )
    await create_agent(FunctionModel(respond)).run("question", deps=deps)
    search.assert_awaited_once_with("Apple net sales", "AAPL", 2024)
