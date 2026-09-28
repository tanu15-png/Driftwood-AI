"""Shared filesystem constants for the ingest pipeline.

All corpus artifacts live under the repo-root data/ directory; this module is
the single place that knows where those are, so ingest scripts stay independent
of their own location.
"""

from __future__ import annotations

from pathlib import Path

# backend/app/ingest/paths.py -> repo root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
MARKDOWN_DIR = DATA_DIR / "markdown"
DOCLING_DIR = DATA_DIR / "docling"
CHUNKS_DIR = DATA_DIR / "chunks"

MARKDOWN_MANIFEST = MARKDOWN_DIR / "manifest.json"
DOCLING_MANIFEST = DOCLING_DIR / "manifest.json"

COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
}
