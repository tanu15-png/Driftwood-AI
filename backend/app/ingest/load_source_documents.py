# /// script
# requires-python = ">=3.12"
# ///
"""Load converted Markdown filings into the source_documents table.

Reads data/markdown/manifest.json, loads each .md file it points to, and
upserts one source_documents row per filing, keyed on the unique
accession_number. Re-running only refreshes the markdown content — safe
to run after reconverting the corpus.

Run from the repo root with the backend env so `app.*` imports resolve:
    cd backend && uv run ../data/load_source_documents.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

DATA_DIR = Path(__file__).resolve().parent
BACKEND_DIR = DATA_DIR.parent / "backend"
MARKDOWN_DIR = DATA_DIR / "markdown"
MANIFEST_PATH = MARKDOWN_DIR / "manifest.json"

sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.database.models import SourceDocument  # noqa: E402

COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
}


def upsert_documents() -> dict:
    if not MANIFEST_PATH.exists():
        sys.exit(f"No markdown manifest at {MANIFEST_PATH}. Run data/convert_to_markdown.py first.")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = manifest["filings"]
    if not entries:
        sys.exit("Manifest has no filings — nothing to load.")

    engine = create_engine(settings.sqlalchemy_database_url)
    inserted, updated = 0, 0
    with Session(engine) as session:
        for entry in entries:
            markdown_path = MARKDOWN_DIR / entry["markdown_path"]
            if not markdown_path.exists():
                sys.exit(f"Missing markdown file for {entry['accession_number']}: {markdown_path}")
            markdown = markdown_path.read_text(encoding="utf-8")

            document = session.execute(
                select(SourceDocument).where(
                    SourceDocument.accession_number == entry["accession_number"]
                )
            ).scalar_one_or_none()

            if document is None:
                document = SourceDocument(
                    ticker=entry["ticker"],
                    company=COMPANY_NAMES[entry["ticker"]],
                    filing_type=entry["form"],
                    filing_date=entry["filing_date"],
                    fiscal_year=int(entry["report_date"][:4]),
                    accession_number=entry["accession_number"],
                    source_url=entry["source_url"],
                    markdown=markdown,
                )
                session.add(document)
                inserted += 1
            elif document.markdown != markdown:
                document.markdown = markdown
                updated += 1
        session.commit()
    engine.dispose()

    print(
        f"Loaded {len(entries)} filing(s) into source_documents "
        f"({inserted} inserted, {updated} updated, "
        f"{len(entries) - inserted - updated} unchanged)."
    )
    return {"inserted": inserted, "updated": updated}


if __name__ == "__main__":
    upsert_documents()
