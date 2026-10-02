"""PydanticAI boundary with bounded tools and mandatory output validation."""

import asyncio
from pathlib import Path
from typing import Annotated
from uuid import UUID

from pydantic import Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer, SourcePassage
from app.config import settings
from app.embeddings import MODEL_TOKEN_LIMIT, QUERY_INSTRUCTION


def create_gemini_model() -> GoogleModel:
    if not settings.gemini_api_key.strip():
        raise RuntimeError("GEMINI_API_KEY is required for grounded chat generation.")
    return GoogleModel(
        settings.gemini_model, provider=GoogleProvider(api_key=settings.gemini_api_key)
    )


def create_agent(model: Model) -> Agent[DocumentAgentDeps, GroundedAnswer]:
    agent = Agent(
        model, deps_type=DocumentAgentDeps, output_type=GroundedAnswer,
        instructions=Path(__file__).with_name("instructions.md").read_text(),
        retries=1, model_settings={"max_tokens": 4000},
    )

    @agent.tool(sequential=True)
    async def search_filings(
        ctx: RunContext[DocumentAgentDeps],
        query: Annotated[str, Field(min_length=1, max_length=1200)],
        ticker: str | None = None,
        fiscal_year: int | None = None,
    ) -> list[SourcePassage]:
        """Search filing passages, optionally filtering company ticker and fiscal year."""
        count = await asyncio.to_thread(
            ctx.deps.retriever.embed_model.tokenizer.count_tokens, QUERY_INSTRUCTION + query
        )
        if count > MODEL_TOKEN_LIMIT - 2:
            raise ModelRetry("Shorten the search query to fit the embedding token limit.")
        return await ctx.deps.retriever.search(query, ticker, fiscal_year)

    @agent.tool(sequential=True)
    async def read_chunk(
        ctx: RunContext[DocumentAgentDeps], chunk_id: UUID
    ) -> SourcePassage | None:
        """Read a passage already retrieved in this turn."""
        return ctx.deps.retriever.passages.get(chunk_id)

    @agent.tool(sequential=True)
    async def read_surrounding_chunks(
        ctx: RunContext[DocumentAgentDeps], chunk_id: UUID,
        window: Annotated[int, Field(ge=0, le=3)] = 1,
    ) -> list[SourcePassage]:
        """Retrieve nearby passages for a chunk already retrieved in this turn."""
        return await ctx.deps.retriever.neighbors(chunk_id, window)

    @agent.output_validator
    def validate_output(
        ctx: RunContext[DocumentAgentDeps], output: GroundedAnswer
    ) -> GroundedAnswer:
        ctx.deps.validator.validate(output, ctx.deps.retriever.passages)
        return output

    return agent
