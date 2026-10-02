"""Conversion outputs and loader manifests; mock the external parser."""

import json
import sys
from types import SimpleNamespace

import pytest

from app.ingest import convert_to_docling_json as converter


@pytest.fixture
def conversion(monkeypatch, tmp_path):
    downloads = tmp_path / "downloads"
    source = downloads / "2025" / "filing.htm"
    source.parent.mkdir(parents=True)
    source.write_text("<h1>Revenue</h1>")
    entry = {"local_path": "2025\\filing.htm", "accession_number": "test-filing"}
    download_manifest = downloads / "manifest.json"
    download_manifest.write_text(json.dumps({"filings": [entry]}))
    docling = tmp_path / "docling"
    markdown = tmp_path / "markdown"
    monkeypatch.setattr(converter, "DOWNLOADS_DIR", downloads)
    monkeypatch.setattr(converter, "DOWNLOAD_MANIFEST", download_manifest)
    monkeypatch.setattr(converter, "DOCLING_DIR", docling)
    monkeypatch.setattr(converter, "OUTPUT_MANIFEST", docling / "manifest.json")
    monkeypatch.setattr(converter, "MARKDOWN_DIR", markdown)
    monkeypatch.setattr(converter, "MARKDOWN_MANIFEST", markdown / "manifest.json")

    class Document:
        def save_as_json(self, path):
            path.write_text("{}")

        def export_to_markdown(self):
            return "# Revenue"

    class Parser:
        def convert(self, path):
            return SimpleNamespace(document=Document())

    monkeypatch.setitem(
        sys.modules,
        "docling.document_converter",
        SimpleNamespace(DocumentConverter=Parser),
    )
    return docling, markdown, Parser


def test_conversion_writes_both_matching_manifests(conversion):
    docling, markdown, _ = conversion
    manifest = converter.convert_all()
    markdown_manifest = json.loads((markdown / "manifest.json").read_text())
    assert manifest["converted_count"] == 1
    assert manifest["filings"][0]["docling_path"] == "2025/filing.json"
    assert markdown_manifest["filings"][0]["markdown_path"] == "2025/filing.md"
    assert markdown_manifest["filings"][0]["accession_number"] == "test-filing"
    assert (docling / "2025/filing.json").exists()
    assert (markdown / "2025/filing.md").read_text() == "# Revenue\n"


def test_failed_conversion_is_excluded_from_both_manifests(conversion, monkeypatch):
    docling, markdown, parser = conversion

    def fail(self, path):
        raise ValueError("invalid filing")

    monkeypatch.setattr(parser, "convert", fail)
    with pytest.raises(SystemExit):
        converter.convert_all()
    for directory in (docling, markdown):
        manifest = json.loads((directory / "manifest.json").read_text())
        assert manifest["filings"] == []
        assert manifest["failed_count"] == 1
