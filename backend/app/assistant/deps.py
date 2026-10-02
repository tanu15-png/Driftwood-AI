"""Each turn owns its evidence ledger; tools cannot replace source metadata."""

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.outputs import SourcePassage
from app.auth.dependencies import CurrentUser
from app.embeddings import LocalEmbeddingModel
from app.grounding.validator import GroundingValidator
from app.retrieval import tools


@dataclass
class DocumentRetriever:
    session: AsyncSession
    embed_model: LocalEmbeddingModel
    passages: dict[UUID, SourcePassage] = field(default_factory=dict)

    def remember(self, rows: list[dict]) -> list[SourcePassage]:
        passages = []
        for row in rows:
            meta = row["metadata"]
            passage = SourcePassage(
                id=row["id"], document_id=row["document_id"],
                chunk_text=row["chunk_text"], page=meta.get("page"),
                section=meta.get("section"), ticker=meta["ticker"],
                company=meta["company"], fiscal_year=meta["fiscal_year"],
                filing_type=meta["filing_type"], filing_date=meta["filing_date"],
                source_url=meta["source_url"],
            )
            self.passages[passage.id] = passage
            passages.append(passage)
        return passages

    async def search(
        self, query: str, ticker: str | None = None, fiscal_year: int | None = None
    ) -> list[SourcePassage]:
        rows = await tools.search_filings(
            self.session, query, limit=10, ticker=ticker, fiscal_year=fiscal_year,
            embed_model=self.embed_model,
        )
        return self.remember(rows)

    async def neighbors(self, chunk_id: UUID, window: int = 1) -> list[SourcePassage]:
        if chunk_id not in self.passages:
            return []
        return self.remember(
            await tools.read_surrounding_chunks(self.session, chunk_id, window=window)
        )


@dataclass
class DocumentAgentDeps:
    user: CurrentUser
    thread_id: UUID
    retriever: DocumentRetriever
    validator: GroundingValidator
