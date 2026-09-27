# /// script
# requires-python = ">=3.12"
# ///
"""Convert downloaded 10-K HTML filings to Markdown with docling.

Reads every .htm/.html file under data/downloads/<year>/, converts it to
Markdown, writes it to data/markdown/<year>/ with the same filename (but
.md), and emits data/markdown/manifest.json mirroring the downloads
manifest with the converted output paths added.

Needs `docling` importable. Run either with the backend dev env
(cd backend && uv run ../data/convert_to_markdown.py) or a standalone
env that has docling installed.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from docling.document_converter import DocumentConverter

DATA_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = DATA_DIR / "downloads"
MARKDOWN_DIR = DATA_DIR / "markdown"
DOWNLOAD_MANIFEST = DOWNLOADS_DIR / "manifest.json"
OUTPUT_MANIFEST = MARKDOWN_DIR / "manifest.json"

HTML_SUFFIXES = {".htm", ".html"}


def convert_all() -> dict:
    if not DOWNLOAD_MANIFEST.exists():
        sys.exit(f"No download manifest at {DOWNLOAD_MANIFEST}. Run data/download.py first.")

    downloads_manifest = json.loads(DOWNLOAD_MANIFEST.read_text(encoding="utf-8"))
    entries = downloads_manifest["filings"]

    html_files = sorted(
        path
        for path in DOWNLOADS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in HTML_SUFFIXES
    )
    print(f"Found {len(html_files)} HTML file(s), {len(entries)} manifest entr(ies).")
    if not html_files:
        sys.exit(f"No HTML files under {DOWNLOADS_DIR}. Run data/download.py first.")

    converter = DocumentConverter()

    converted = {}
    failures = []
    for i, source in enumerate(html_files, 1):
        relative = source.relative_to(DOWNLOADS_DIR)
        target = MARKDOWN_DIR / relative.with_suffix(".md")
        target.parent.mkdir(parents=True, exist_ok=True)

        start = time.monotonic()
        try:
            result = converter.convert(source)
            markdown = result.document.export_to_markdown()
        except Exception as error:  # noqa: BLE001 - keep converting the rest on failure
            failures.append({"local_path": str(relative), "error": str(error)})
            print(f"[{i}/{len(html_files)}] FAILED  {relative}: {error}")
            continue

        target.write_text(markdown + "\n", encoding="utf-8")
        converted[str(relative)] = str(target.relative_to(MARKDOWN_DIR))
        print(f"[{i}/{len(html_files)}] OK ({time.monotonic() - start:.1f}s)  {relative} -> {target.relative_to(MARKDOWN_DIR)}")

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
        "filings": [],
    }
    for entry in entries:
        downloaded = entry["local_path"].replace("\\", "/")
        output_path = converted.get(downloaded)
        if output_path is None:
            continue
        manifest["filings"].append({**entry, "markdown_path": output_path})

    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        f"Converted {len(converted)} file(s) to {MARKDOWN_DIR} "
        f"({len(failures)} failed). Manifest: {OUTPUT_MANIFEST}"
    )
    if failures:
        sys.exit(1)
    return manifest


if __name__ == "__main__":
    convert_all()
