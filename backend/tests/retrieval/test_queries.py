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
    assert params["query"] == query
    assert query not in str(statement)
    assert params["ticker"] is None
    assert params["fiscal_year"] == 2024
