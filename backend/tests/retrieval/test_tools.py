from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.retrieval import tools


async def test_tools_enforce_bounds_before_io() -> None:
    session = AsyncMock()
    with pytest.raises(ValueError, match="limit"):
        await tools.search_filings(session, "revenue", limit=21)
    with pytest.raises(ValueError, match="window"):
        await tools.read_surrounding_chunks(session, uuid4(), window=4)
    session.execute.assert_not_called()


async def test_missing_chunk_returns_empty() -> None:
    with patch.object(tools, "_fetch_chunks", AsyncMock(return_value={})):
        assert await tools.read_chunk(AsyncMock(), uuid4()) is None
        assert await tools.read_surrounding_chunks(AsyncMock(), uuid4()) == []
