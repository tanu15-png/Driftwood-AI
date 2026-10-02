"""Reject unknown citations, fabricated quotes, and unsupported output shapes."""

import re
from collections.abc import Mapping
from uuid import UUID

from app.assistant.outputs import GroundedAnswer, SourcePassage


class GroundingError(ValueError):
    """An answer must not be streamed or stored as successful."""


def _normalize(text: str) -> str:
    return " ".join(text.split())


class GroundingValidator:
    def validate(
        self, answer: GroundedAnswer, retrieved: Mapping[UUID, SourcePassage]
    ) -> list[SourcePassage]:
        if answer.refusal_reason:
            if answer.claims or answer.citations:
                raise GroundingError("Refusals must have no claims or citations.")
            return []
        if not answer.claims or not answer.citations:
            raise GroundingError("Answers require claims and citations.")
        citations = {citation.id: citation for citation in answer.citations}
        if len(citations) != len(answer.citations):
            raise GroundingError("Citation IDs must be unique.")
        used = set()
        for claim in answer.claims:
            if not claim.text.strip() or re.search(r"\[\d+\]", claim.text):
                raise GroundingError("Claim text must be nonempty and contain no citation markers.")
            if len(set(claim.citation_ids)) != len(claim.citation_ids):
                raise GroundingError("Claim citation IDs must be unique.")
            used.update(claim.citation_ids)
        if used != citations.keys():
            raise GroundingError("Every claim must reference known citations; no unused citations.")
        passages = {}
        for citation in answer.citations:
            passage = retrieved.get(citation.chunk_id)
            if passage is None:
                raise GroundingError("Citation refers to a chunk not retrieved this turn.")
            quote = _normalize(citation.quote)
            if not quote or quote not in _normalize(passage.chunk_text):
                raise GroundingError("Citation quote must occur in the retrieved passage.")
            passages[passage.id] = passage
        return list(passages.values())
