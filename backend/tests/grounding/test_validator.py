from uuid import uuid4

import pytest

from app.assistant.outputs import Citation, GroundedAnswer, GroundedClaim, SourcePassage
from app.grounding.validator import GroundingError, GroundingValidator


@pytest.fixture
def source():
    return SourcePassage(
        id=uuid4(), document_id=uuid4(), chunk_text="Revenue was $10 million.\nServices grew.",
        ticker="AAPL", company="Apple Inc.", fiscal_year=2025, filing_type="10-K",
        filing_date="2025-10-31", source_url="https://www.sec.gov/filing",
    )


def supported(source):
    return GroundedAnswer(
        claims=[GroundedClaim(text="Revenue was $10 million.", citation_ids=[1])],
        citations=[Citation(id=1, chunk_id=source.id, quote="Revenue was $10 million.")],
        refusal_reason=None,
    )


def test_valid_claims_render_server_citations_and_canonical_sources(source):
    answer = supported(source)
    assert GroundingValidator().validate(answer, {source.id: source}) == [source]
    assert answer.answer == "Revenue was $10 million. [1]"


@pytest.mark.parametrize("fault", [
    "unknown_chunk", "fabricated_quote", "empty_quote", "duplicate_id",
    "unknown_reference", "unused_citation", "inline_marker", "empty_claim",
    "duplicate_reference", "no_claims", "no_citations", "refusal_with_claims",
])
def test_rejects_invalid_grounding(source, fault):
    answer = supported(source)
    if fault == "unknown_chunk":
        answer.citations[0].chunk_id = uuid4()
    elif fault == "fabricated_quote":
        answer.citations[0].quote = "Revenue was $100 million."
    elif fault == "empty_quote":
        answer.citations[0].quote = "  "
    elif fault == "duplicate_id":
        answer.citations.append(answer.citations[0])
    elif fault == "unknown_reference":
        answer.claims[0].citation_ids = [2]
    elif fault == "unused_citation":
        answer.citations.append(answer.citations[0].model_copy(update={"id": 2}))
    elif fault == "inline_marker":
        answer.claims[0].text += " [99]"
    elif fault == "empty_claim":
        answer.claims[0].text = "  "
    elif fault == "duplicate_reference":
        answer.claims[0].citation_ids = [1, 1]
    elif fault == "no_claims":
        answer.claims = []
    elif fault == "no_citations":
        answer.citations = []
    else:
        answer.refusal_reason = "insufficient_evidence"
    with pytest.raises(GroundingError):
        GroundingValidator().validate(answer, {source.id: source})


@pytest.mark.parametrize("reason", ["insufficient_evidence", "investment_advice"])
def test_refusal_has_fixed_text_and_no_citations(source, reason):
    answer = GroundedAnswer(claims=[], citations=[], refusal_reason=reason)
    assert GroundingValidator().validate(answer, {source.id: source}) == []
    assert "[" not in answer.answer


def test_quotes_allow_whitespace_differences(source):
    answer = supported(source)
    answer.citations[0].quote = "million. Services grew."
    assert GroundingValidator().validate(answer, {source.id: source}) == [source]
