from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.retrieval.queries import dense_search, full_text_search


async def test_dense_filters_are_bound_before_limit() -> None:
    chunk_id = uuid4()
    session = AsyncMock()
    session.execute.return_value = [SimpleNamespace(id=chunk_id)]
    assert await dense_search(session, [0.1], ticker="aapl", fiscal_year=2025) == [
        chunk_id
    ]
    statement, params = session.execute.call_args.args
    assert params["ticker"] == "AAPL"
    assert params["fiscal_year"] == 2025
    assert str(statement).index("s.ticker = :ticker") < str(statement).index("LIMIT")


async def test_fts_query_is_bound_and_scoped() -> None:
    session = AsyncMock()
    session.execute.return_value = []
    query = "revenue'; DROP TABLE source_documents; --"
    assert await full_text_search(session, query, fiscal_year=2024) == []
    statement, params = session.execute.call_args.args
    assert params["keyword_query"] == "revenue | drop | table | source | documents"
    assert query not in str(statement)
    assert params["ticker"] is None
    assert params["fiscal_year"] == 2024


async def test_fts_searches_keywords_without_question_filler() -> None:
    session = AsyncMock()
    session.execute.return_value = []
    await full_text_search(
        session, "Please show Apple's iPhone vs Services revenue mix", ticker="aapl"
    )
    statement, params = session.execute.call_args.args
    assert params["keyword_query"] == "apple | iphone | services | revenue | mix"
    assert params["ticker"] == "AAPL"
    assert "websearch_to_tsquery" not in str(statement)
    assert "to_tsquery('english', :keyword_query)" in str(statement)
    assert str(statement).index("s.ticker = :ticker") < str(statement).index("LIMIT")


async def test_fts_skips_queries_with_no_keywords() -> None:
    session = AsyncMock()
    assert await full_text_search(session, "Please tell me what it is") == []
    session.execute.assert_not_awaited()
