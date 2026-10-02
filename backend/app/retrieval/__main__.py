"""Run hybrid retrieval without invoking a chat model."""

import argparse
import asyncio
import json

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.retrieval.retriever import hybrid_search


async def search(args: argparse.Namespace) -> None:
    engine = create_async_engine(settings.sqlalchemy_database_url)
    try:
        async with AsyncSession(engine) as session:
            passages = await hybrid_search(
                session,
                args.query,
                ticker=args.ticker,
                fiscal_year=args.year,
                top_k=args.limit,
                with_neighbors=args.neighbors,
            )
            print(json.dumps(passages, indent=2, ensure_ascii=False))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--ticker")
    parser.add_argument("--year", type=int)
    parser.add_argument("--limit", type=int, default=10, choices=range(1, 101))
    parser.add_argument("--neighbors", action="store_true")
    asyncio.run(search(parser.parse_args()))


if __name__ == "__main__":
    main()
