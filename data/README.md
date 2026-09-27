Data
Local data artifacts for development live here.

downloads/ holds raw source files fetched from SEC EDGAR, grouped by year.
Downloaded payloads are gitignored because the corpus can get large.
Fetch a sample corpus with uv run data/download.py

markdown/ holds the docling-converted Markdown for each download, mirroring
the downloads/ layout plus its own manifest.json with a markdown_path per
filing. Convert with any environment that has docling importable:
    ~/.venvs/docling-tools/bin/python data/convert_to_markdown.py

load_source_documents.py upserts every converted filing into the
source_documents table, keyed on accession_number — safe to re-run:
    cd backend && .venv/bin/python ../data/load_source_documents.py