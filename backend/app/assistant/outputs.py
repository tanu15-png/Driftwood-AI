"""Model claims reference evidence; display text and sources come from the server."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourcePassage(BaseModel):
    id: UUID
    document_id: UUID
    chunk_text: str
    ticker: str
    company: str
    fiscal_year: int
    filing_type: str
    filing_date: str
    source_url: str
    page: int | None = None
    section: str | None = None


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1, le=30)
    chunk_id: UUID
    quote: str = Field(min_length=1, max_length=2000)


class GroundedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    citation_ids: list[int] = Field(min_length=1, max_length=10)


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[GroundedClaim] = Field(max_length=20)
    citations: list[Citation] = Field(max_length=30)
    refusal_reason: Literal["insufficient_evidence", "investment_advice"] | None

    @property
    def answer(self) -> str:
        if self.refusal_reason == "insufficient_evidence":
            return "The filing corpus does not contain enough evidence to answer this question."
        if self.refusal_reason == "investment_advice":
            return "I can explain the filings, but I cannot provide stock picks or investment advice."
        parts = []
        for claim in self.claims:
            text = claim.text.strip()
            markers = " ".join(f"[{id_}]" for id_ in claim.citation_ids)
            # A marker appended to a table row can be parsed as an extra cell.
            separator = "\n\n" if any(line.lstrip().startswith("|") for line in text.splitlines()) else " "
            parts.append(f"{text}{separator}{markers}")
        return "\n\n".join(parts)
