from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.assistant.agent import create_agent, create_gemini_model
from app.assistant.deps import DocumentAgentDeps
from app.auth.dependencies import CurrentUser
from app.config import settings
from app.grounding.validator import GroundingError, GroundingValidator


async def test_output_validator_is_enforced_by_real_agent():
    output = {
        "claims": [{"text": "Invented revenue.", "citation_ids": [1]}],
        "citations": [{"id": 1, "chunk_id": str(uuid4()), "quote": "Invented quote."}],
        "refusal_reason": None,
    }

    async def respond(messages, info):
        assert "Use only passages" in info.instructions
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    class Retriever:
        def __init__(self):
            self.passages = {}

    deps = DocumentAgentDeps(
        CurrentUser(uuid4(), "test@example.com"), uuid4(), Retriever(), GroundingValidator()
    )
    with pytest.raises(GroundingError, match="not retrieved"):
        await create_agent(FunctionModel(respond)).run("question", deps=deps)


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


def test_generation_fails_fast_without_gemini_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        create_gemini_model()
