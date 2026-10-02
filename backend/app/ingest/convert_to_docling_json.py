# /// script
# requires-python = ">=3.12"
# ///
"""Convert downloaded 10-K HTML filings to docling DoclingDocuments.

For every .htm/.html file under data/downloads/<year>/ this writes:

  data/docling/<year>/<same-stem>.json   DoclingDocument.save_as_json() output
  data/markdown/<year>/<same-stem>.md    export_to_markdown() output
  data/docling/manifest.json             download manifest + docling paths
  data/markdown/manifest.json            same successful filings + Markdown paths

The JSON documents (not the Markdown) are the input for docling's native
chunkers, per the docling chunking docs.

Needs `docling` importable, which the backend venv cannot provide (its
docling import crashes on the torch/Python combo) — run it with the
dedicated docling env, from backend/ so the app package resolves:

    cd backend && ~/.venvs/docling-tools/bin/python -m app.ingest.convert_to_docling_json
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from app.ingest.paths import (
    DOCLING_DIR,
    DOWNLOADS_DIR,
    MARKDOWN_DIR,
    MARKDOWN_MANIFEST,
)

DOWNLOAD_MANIFEST = DOWNLOADS_DIR / "manifest.json"
OUTPUT_MANIFEST = DOCLING_DIR / "manifest.json"

HTML_SUFFIXES = {".htm", ".html"}


def convert_all() -> dict:
    from docling.document_converter import DocumentConverter

    if not DOWNLOAD_MANIFEST.exists():
        raise SystemExit(f"No download manifest at {DOWNLOAD_MANIFEST}. Run data/download.py first.")

    downloads_manifest = json.loads(DOWNLOAD_MANIFEST.read_text(encoding="utf-8"))
    entries = downloads_manifest["filings"]

    html_files = sorted(
        path
        for path in DOWNLOADS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in HTML_SUFFIXES
    )
    print(f"Found {len(html_files)} HTML file(s), {len(entries)} manifest entr(ies).")
    if not html_files:
        raise SystemExit(f"No HTML files under {DOWNLOADS_DIR}. Run data/download.py first.")

    converter = DocumentConverter()

    converted: dict[str, str] = {}
    failures: list[dict[str, str]] = []
    for i, source in enumerate(html_files, 1):
        relative = source.relative_to(DOWNLOADS_DIR)
        json_target = DOCLING_DIR / relative.with_suffix(".json")
        md_target = MARKDOWN_DIR / relative.with_suffix(".md")
        json_target.parent.mkdir(parents=True, exist_ok=True)
        md_target.parent.mkdir(parents=True, exist_ok=True)

        start = time.monotonic()
        try:
            result = converter.convert(source)
            document = result.document
            document.save_as_json(json_target)
        except Exception as error:  # noqa: BLE001 - keep converting the rest on failure
            failures.append({"local_path": str(relative), "error": str(error)})
            print(f"[{i}/{len(html_files)}] FAILED  {relative}: {error}")
            continue

        md_target.write_text(document.export_to_markdown() + "\n", encoding="utf-8")
        converted[str(relative)] = str(json_target.relative_to(DOCLING_DIR))
        print(
            f"[{i}/{len(html_files)}] OK ({time.monotonic() - start:.1f}s)  "
            f"{relative} -> docling/{json_target.relative_to(DOCLING_DIR)}"
        )

    # The download manifest uses Windows separators on some machines; the
    # converted map is keyed on POSIX-style paths from rglob, so match loosely.
    manifest = {
        "source": "SEC EDGAR",
        "converted_at_utc": datetime.now(UTC).isoformat(),
        "form": downloads_manifest.get("form"),
        "downloaded_count": downloads_manifest.get("downloaded_count"),
        "converted_count": len(converted),
        "failed_count": len(failures),
        "converter": "docling",
        "format": "docling_document_json",
        "filings": [],
    }
    for entry in entries:
        downloaded = entry["local_path"].replace("\\", "/")
        output_path = converted.get(downloaded)
        if output_path is None:
            continue
        manifest["filings"].append({**entry, "docling_path": output_path})

    OUTPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # The document loader must consume the same successful conversion set
    # as the chunker, rather than a manifest from a separate Markdown run.
    markdown_manifest = {
        **manifest,
        "format": "markdown",
        "filings": [
            {
                **entry,
                "markdown_path": Path(entry["docling_path"]).with_suffix(".md").as_posix(),
            }
            for entry in manifest["filings"]
        ],
    }
    MARKDOWN_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MARKDOWN_MANIFEST.write_text(
        json.dumps(markdown_manifest, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"Converted {len(converted)} file(s) to {DOCLING_DIR} "
        f"({len(failures)} failed). Manifest: {OUTPUT_MANIFEST}"
    )
    if failures:
        raise SystemExit(1)
    return manifest


if __name__ == "__main__":
    convert_all()
