"""Retrieve, generate and validate before exposing any assistant text."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException
from pydantic_ai.exceptions import (
    ModelAPIError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.usage import UsageLimits
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.agent import MAX_MODEL_REQUESTS, MAX_TOOL_CALLS
from app.assistant.deps import DocumentAgentDeps, DocumentRetriever
from app.assistant.outputs import GroundedAnswer, SourcePassage
from app.assistant.runtime import AssistantRuntime
from app.auth.dependencies import CurrentUser
from app.chat import messages
from app.database import chats
from app.database.models import ChatMessage, ChatThread, MessageCitation, MessageRole
from app.embeddings import MODEL_TOKEN_LIMIT, QUERY_INSTRUCTION
from app.grounding.validator import GroundingError, GroundingValidator

logger = structlog.get_logger(__name__)


@dataclass
class PreparedTurn:
    answer: GroundedAnswer
    sources: list[SourcePassage]
    usage: dict[str, Any]


async def prepare_turn(
    session: AsyncSession, user: CurrentUser, thread_id: UUID,
    question: str, runtime: AssistantRuntime,
) -> PreparedTurn:
    count = await asyncio.to_thread(
        runtime.embed_model.tokenizer.count_tokens, QUERY_INSTRUCTION + question
    )
    if count > MODEL_TOKEN_LIMIT - 2:
        raise HTTPException(422, "Question exceeds the local embedding token limit.")
    retriever = DocumentRetriever(session, runtime.embed_model)
    validator = GroundingValidator()
    deps = DocumentAgentDeps(user, thread_id, retriever, validator)
    try:
        history = await chats.list_messages(session, thread_id)
        initial = await retriever.search(question)
        if not initial:
            answer = GroundedAnswer(claims=[], citations=[], refusal_reason="insufficient_evidence")
            return PreparedTurn(answer, [], {"input_tokens": 0, "output_tokens": 0, "requests": 0})
        context = [{"role": str(row.role), "text": row.content[:1500]} for row in history[-12:]]
        prompt = json.dumps({
            "question": question, "conversation_context": context,
            "initial_passages": [p.model_dump(mode="json") for p in initial],
        }, ensure_ascii=False)
        result = await runtime.agent.run(
            prompt, deps=deps,
            usage_limits=UsageLimits(request_limit=MAX_MODEL_REQUESTS, tool_calls_limit=MAX_TOOL_CALLS),
        )
        sources = validator.validate(result.output, retriever.passages)
        usage = result.usage
        return PreparedTurn(result.output, sources, {
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
            "requests": usage.requests, "tool_calls": usage.tool_calls,
            "model": str(runtime.agent.model.model_name),
        })
    except GroundingError as exc:
        logger.warning("grounding_rejected", reason=str(exc))
        raise HTTPException(502, "Grounding validation failed; no answer was produced.") from exc
    except (ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded) as exc:
        provider_status = getattr(exc, "status_code", None)
        logger.warning("generation_failed", error_type=type(exc).__name__, status_code=provider_status)
        if isinstance(exc, UsageLimitExceeded):
            logger.warning("assistant_limit_exceeded", reason=str(exc))
        detail = "Gemini answer generation failed; please retry later."
        if provider_status == 429:
            detail = "Gemini rate limit or quota exhausted. Wait before retrying, or check the Gemini project's quota and billing."
        elif provider_status == 404:
            detail = "The configured Gemini model is unavailable. Check GEMINI_MODEL in backend/.env."
        elif provider_status in (401, 403):
            detail = "Gemini rejected the backend credentials or permissions. Check GEMINI_API_KEY and its project access."
        elif isinstance(exc, UnexpectedModelBehavior):
            detail = "Gemini did not return a valid grounded answer within the correction limit. Please retry or narrow the question."
        elif isinstance(exc, UsageLimitExceeded):
            detail = "The question exceeded the assistant's request or tool-call limit. Try a narrower question."
        raise HTTPException(502, detail) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Filing retrieval is temporarily unavailable.") from exc


def sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def citation_parts(turn: PreparedTurn) -> list[dict[str, Any]]:
    return [
        {"type": "source-url", "sourceId": str(source.id), "url": source.source_url,
         "title": f"{source.ticker} {source.filing_type} FY{source.fiscal_year}"}
        for source in turn.sources
    ] + [
        {"type": "data-citations", "id": "citations",
         "data": [c.model_dump(mode="json") for c in turn.answer.citations]},
        {"type": "data-sources", "id": "sources",
         "data": [s.model_dump(mode="json") for s in turn.sources]},
        {"type": "data-grounding", "id": "grounding",
         "data": {"status": turn.answer.refusal_reason or "supported"}},
    ]


async def stream_turn(
    session: AsyncSession, thread: ChatThread, user_ui_message: dict[str, Any],
    question: str, assistant_id: UUID, turn: PreparedTurn,
) -> AsyncIterator[str]:
    yield sse({"type": "start", "messageId": str(assistant_id)})
    yield sse({"type": "start-step"})
    yield sse({"type": "text-start", "id": "answer"})
    for start in range(0, len(turn.answer.answer), 120):
        yield sse({"type": "text-delta", "id": "answer", "delta": turn.answer.answer[start:start+120]})
        await asyncio.sleep(0)
    yield sse({"type": "text-end", "id": "answer"})
    parts = citation_parts(turn)
    for part in parts:
        yield sse(part)
    ui_message = messages.assistant_ui_message(assistant_id, turn.answer.answer)
    ui_message["parts"].extend(parts)
    ui_message["metadata"] = {"usage": turn.usage}
    assistant_row = ChatMessage(
        id=assistant_id, thread_id=thread.id, role=MessageRole.ASSISTANT,
        content=turn.answer.answer, ui_message=ui_message,
    )
    user_row = ChatMessage(
        thread_id=thread.id, role=MessageRole.USER, content=question, ui_message=user_ui_message,
    )
    sources = {source.id: source for source in turn.sources}
    citations = [MessageCitation(
        message_id=assistant_id, chunk_id=c.chunk_id,
        document_id=sources[c.chunk_id].document_id, page=sources[c.chunk_id].page,
        section=sources[c.chunk_id].section, excerpt=c.quote,
    ) for c in turn.answer.citations]
    try:
        await chats.persist_turn(session, thread, user_row, assistant_row, citations)
    except SQLAlchemyError:
        await session.rollback()
        yield sse({"type": "error", "errorText": "The answer could not be saved; please retry."})
        yield "data: [DONE]\n\n"
        return
    yield sse({"type": "finish-step"})
    yield sse({"type": "finish", "messageMetadata": {"usage": turn.usage}})
    yield "data: [DONE]\n\n"
