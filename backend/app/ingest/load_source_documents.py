# /// script
# requires-python = ">=3.12"
# ///
"""Load converted Markdown filings into the source_documents table.

Reads data/markdown/manifest.json, loads each .md file it points to, and
upserts one source_documents row per filing, keyed on the unique
accession_number. Re-running only refreshes the markdown content — safe
to run after reconverting the corpus.

Run with the backend env (paths resolve relative to the repo root, which is
the script's grandparent directory):
    cd backend && uv run python -m app.ingest.load_source_documents
"""

from __future__ import annotations

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import SourceDocument
from app.ingest.paths import COMPANY_NAMES, MARKDOWN_DIR, MARKDOWN_MANIFEST


def upsert_documents() -> dict:
    if not MARKDOWN_MANIFEST.exists():
        raise SystemExit(
            f"No markdown manifest at {MARKDOWN_MANIFEST}. Run app.ingest.convert_to_docling_json first."
        )

    manifest = json.loads(MARKDOWN_MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["filings"]
    if not entries:
        raise SystemExit("Manifest has no filings — nothing to load.")

    engine = create_engine(settings.sqlalchemy_database_url)
    inserted, updated = 0, 0
    with Session(engine) as session:
        for entry in entries:
            markdown_path = MARKDOWN_DIR / entry["markdown_path"]
            if not markdown_path.exists():
                raise SystemExit(
                    f"Missing markdown file for {entry['accession_number']}: {markdown_path}"
                )
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
