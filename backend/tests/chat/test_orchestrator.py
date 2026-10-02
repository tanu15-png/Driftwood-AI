import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy.exc import SQLAlchemyError

from app.assistant.agent import create_agent
from app.assistant.outputs import Citation, GroundedAnswer, GroundedClaim, SourcePassage
from app.assistant.runtime import AssistantRuntime
from app.auth.dependencies import CurrentUser
from app.chat import orchestrator
from app.chat.orchestrator import PreparedTurn, prepare_turn, stream_turn


@pytest.fixture
def source():
    return SourcePassage(
        id=uuid4(), document_id=uuid4(), chunk_text="Services revenue increased.",
        ticker="AAPL", company="Apple", fiscal_year=2025, filing_type="10-K",
        filing_date="2025-10-31", source_url="https://www.sec.gov/filing",
    )


def answer(source):
    return GroundedAnswer(
        claims=[GroundedClaim(text="Services revenue increased.", citation_ids=[1])],
        citations=[Citation(id=1, chunk_id=source.id, quote=source.chunk_text)],
        refusal_reason=None,
    )


@pytest.mark.parametrize("kind", ["supported", "empty", "refuse", "fabricated"])
async def test_turn_retrieval_generation_and_contract(monkeypatch, source, kind):
    output = answer(source)
    if kind == "refuse":
        output = GroundedAnswer(claims=[], citations=[], refusal_reason="insufficient_evidence")
    elif kind == "fabricated":
        output.citations[0].chunk_id = uuid4()
    calls = []

    async def respond(messages, info):
        calls.append(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

    class Retriever:
        def __init__(self):
            self.passages = {source.id: source}

        async def search(self, question):
            return [] if kind == "empty" else [source]

    monkeypatch.setattr(orchestrator, "DocumentRetriever", lambda *args: Retriever())
    monkeypatch.setattr(orchestrator.chats, "list_messages", AsyncMock(return_value=[]))
    runtime = AssistantRuntime(create_agent(FunctionModel(respond)), SimpleNamespace(
        tokenizer=SimpleNamespace(count_tokens=lambda text: 10)
    ))
    args = (None, CurrentUser(uuid4(), "test@example.com"), uuid4(), "question", runtime)
    if kind == "fabricated":
        with pytest.raises(HTTPException) as exc:
            await prepare_turn(*args)
        assert exc.value.status_code == 502
        return
    result = await prepare_turn(*args)
    assert result.sources == ([source] if kind == "supported" else [])
    assert bool(result.answer.citations) == (kind == "supported")
    assert len(calls) == (0 if kind == "empty" else 1)


@pytest.mark.parametrize("interrupt", [False, True])
async def test_stream_persists_citations_before_success_or_skips_on_disconnect(monkeypatch, source, interrupt):
    persist = AsyncMock()
    monkeypatch.setattr(orchestrator.chats, "persist_turn", persist)
    stream = stream_turn(
        None, SimpleNamespace(id=uuid4()), {"role": "user"}, "question", uuid4(),
        PreparedTurn(answer(source), [source], {"requests": 1}),
    )
    if interrupt:
        for _ in range(4):
            await anext(stream)
        await stream.aclose()
        persist.assert_not_awaited()
    else:
        events = [e async for e in stream]
        persist.assert_awaited_once()
        args = persist.call_args.args
        assert args[4][0].chunk_id == source.id
        assert args[3].ui_message["metadata"]["usage"] == {"requests": 1}
        assert "data-citations" in args[3].ui_message["parts"][2]["type"]
        assert json.loads(events[-2][6:])["type"] == "finish"


async def test_database_failure_sends_error_without_success(monkeypatch, source):
    monkeypatch.setattr(orchestrator.chats, "persist_turn", AsyncMock(side_effect=SQLAlchemyError()))
    session = SimpleNamespace(rollback=AsyncMock())
    events = [e async for e in stream_turn(
        session, SimpleNamespace(id=uuid4()), {}, "question", uuid4(),
        PreparedTurn(answer(source), [source], {}),
    )]
    session.rollback.assert_awaited_once()
    assert any('"type": "error"' in e for e in events)
    assert not any('"type": "finish"' in e for e in events)
