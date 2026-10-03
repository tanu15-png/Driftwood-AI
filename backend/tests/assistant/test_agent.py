from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from app.assistant.agent import create_agent, create_gemini_model
from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import SourcePassage
from app.auth.dependencies import CurrentUser
from app.config import settings
from app.grounding.validator import GroundingValidator


async def test_output_validator_is_enforced_by_real_agent():
    output = {
        "claims": [{"text": "Invented revenue.", "citation_ids": [1]}],
        "citations": [{"id": 1, "chunk_id": str(uuid4()), "quote": "Invented quote."}],
        "refusal_reason": None,
    }

    calls = []

    async def respond(messages, info):
        calls.append(messages)
        assert "Use only passages" in info.instructions
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    class Retriever:
        def __init__(self):
            self.passages = {}

    deps = DocumentAgentDeps(
        CurrentUser(uuid4(), "test@example.com"), uuid4(), Retriever(), GroundingValidator()
    )
    with pytest.raises(UnexpectedModelBehavior, match="retries"):
        await create_agent(FunctionModel(respond)).run("question", deps=deps)
    assert len(calls) == 2


async def test_invalid_quote_can_be_corrected_without_relaxing_grounding():
    source = SourcePassage(
        id=uuid4(), document_id=uuid4(), chunk_text="Services revenue increased.",
        ticker="AAPL", company="Apple", fiscal_year=2024, filing_type="10-K",
        filing_date="2024-11-01", source_url="https://www.sec.gov/filing",
    )
    calls = []

    async def respond(messages, info):
        calls.append(messages)
        quote = "Invented quote." if len(calls) == 1 else source.chunk_text
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "claims": [{"text": source.chunk_text, "citation_ids": [1]}],
            "citations": [{"id": 1, "chunk_id": str(source.id), "quote": quote}],
            "refusal_reason": None,
        })])

    deps = DocumentAgentDeps(
        CurrentUser(uuid4(), "test@example.com"), uuid4(),
        SimpleNamespace(passages={source.id: source}), GroundingValidator(),
    )
    result = await create_agent(FunctionModel(respond)).run("question", deps=deps)
    assert len(calls) == 2
    assert "Citation quote must occur" in str(calls[1])
    assert result.output.citations[0].quote == source.chunk_text


async def test_out_of_corpus_model_output_is_explicit_refusal():
    async def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "claims": [], "citations": [], "refusal_reason": "insufficient_evidence",
        })])

    class Retriever:
        def __init__(self):
            self.passages = {}

    deps = DocumentAgentDeps(
        CurrentUser(uuid4(), "test@example.com"), uuid4(), Retriever(), GroundingValidator()
    )
    result = await create_agent(FunctionModel(respond)).run("weather on Mars", deps=deps)
    assert result.output.citations == []
    assert result.output.answer.startswith("The filing corpus does not contain enough evidence")


async def test_retrieval_stops_in_time_to_finish_and_correct():
    calls = []
    source = SourcePassage(
        id=uuid4(), document_id=uuid4(), chunk_text="Services revenue increased.",
        ticker="AAPL", company="Apple", fiscal_year=2024, filing_type="10-K",
        filing_date="2024-11-01", source_url="https://www.sec.gov/filing",
    )

    async def respond(messages, info):
        calls.append(messages)
        if info.function_tools:
            return ModelResponse(parts=[ToolCallPart("read_chunk", {"chunk_id": str(source.id)})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "claims": [{"text": source.chunk_text, "citation_ids": [1]}],
            "citations": [{"id": 1, "chunk_id": str(source.id),
                           "quote": "Invalid quote" if len(calls) == 5 else source.chunk_text}],
            "refusal_reason": None,
        })])

    deps = DocumentAgentDeps(
        CurrentUser(uuid4(), "test@example.com"), uuid4(),
        SimpleNamespace(passages={source.id: source}), GroundingValidator(),
    )
    result = await create_agent(FunctionModel(respond)).run(
        "question", deps=deps, usage_limits=UsageLimits(request_limit=6, tool_calls_limit=5)
    )
    assert len(calls) == 6
    assert result.usage.tool_calls == 4
    assert result.output.citations[0].quote == source.chunk_text


def test_generation_fails_fast_without_gemini_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        create_gemini_model()
