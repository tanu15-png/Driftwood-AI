"""Converted filing intake and repeat loads, without network or a database."""

import json
from unittest.mock import MagicMock

import pytest

from app.ingest import load_source_documents as loader


@pytest.fixture
def intake(monkeypatch, tmp_path):
    entry = {
        "ticker": "AAPL",
        "form": "10-K",
        "filing_date": "2025-10-31",
        "report_date": "2025-09-27",
        "accession_number": "0000320193-25-000079",
        "source_url": "https://example.com/filing.htm",
        "markdown_path": "filing.md",
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"filings": [entry]}))
    (tmp_path / "filing.md").write_text("# Revenue\nServices grew.")
    monkeypatch.setattr(loader, "MARKDOWN_MANIFEST", manifest)
    monkeypatch.setattr(loader, "MARKDOWN_DIR", tmp_path)
    engine = MagicMock()
    session = MagicMock()
    monkeypatch.setattr(loader, "create_engine", lambda url: engine)
    monkeypatch.setattr(loader, "Session", lambda engine: session)
    session.__enter__.return_value = session
    return session, engine


def test_new_filing_keeps_source_metadata(intake):
    session, engine = intake
    session.execute.return_value.scalar_one_or_none.return_value = None
    assert loader.upsert_documents() == {"inserted": 1, "updated": 0}
    document = session.add.call_args.args[0]
    assert document.ticker == "AAPL"
    assert document.fiscal_year == 2025
    assert document.accession_number == "0000320193-25-000079"
    assert document.source_url == "https://example.com/filing.htm"
    assert document.markdown == "# Revenue\nServices grew."
    session.commit.assert_called_once()
    engine.dispose.assert_called_once()


def test_unchanged_filing_is_not_duplicated(intake):
    session, _ = intake
    document = MagicMock(markdown="# Revenue\nServices grew.")
    session.execute.return_value.scalar_one_or_none.return_value = document
    assert loader.upsert_documents() == {"inserted": 0, "updated": 0}
    session.add.assert_not_called()


def test_changed_filing_updates_existing_row(intake):
    session, _ = intake
    document = MagicMock(markdown="old content")
    session.execute.return_value.scalar_one_or_none.return_value = document
    assert loader.upsert_documents() == {"inserted": 0, "updated": 1}
    assert document.markdown == "# Revenue\nServices grew."
    session.add.assert_not_called()
