Data
Local data artifacts for development live here. The pipeline code that
produces and consumes them lives in `backend/app/ingest/` — this directory
holds payloads (gitignored) and only two standalone scripts (`download.py`,
`convert_to_markdown.py`).

downloads/ holds raw source files fetched from SEC EDGAR, grouped by year.
Downloaded payloads are gitignored because the corpus can get large.
Fetch a sample corpus with uv run data/download.py

docling/ holds docling DoclingDocument JSON for each download, mirroring the
downloads/ layout plus its own manifest.json with a docling_path per filing.
These JSON documents (not the Markdown) are the input for docling's native
chunkers. Convert with any environment that has docling importable:
    cd backend && ~/.venvs/docling-tools/bin/python -m app.ingest.convert_to_docling_json

markdown/ holds the docling-converted Markdown for each download, mirroring
the downloads/ layout plus its own manifest.json with a markdown_path per
filing. Written by convert_to_docling_json.py from the same conversion pass.

chunks/ holds chunk JSONL produced by app.ingest.chunk_documents:
    chunks_hybrid.jsonl         HybridChunker, token-aware (this gets embedded)
    chunks_hierarchical.jsonl   HierarchicalChunker, one chunk per element

Pipeline (run from backend/ in this order; every stage is safe to re-run):
  1. ~/.venvs/docling-tools/bin/python -m app.ingest.convert_to_docling_json
     (docling conversion must run in the dedicated env — the backend venv's
     docling import crashes on its torch/Python combo)
  2. uv run python -m app.ingest.load_source_documents
  3. uv run python -m app.ingest.chunk_documents
  4. uv run python -m app.ingest.embed_and_load_chunks --smoke
     (embeds ONE chunk and prints the inserted row back — verify before cost)
  5. uv run python -m app.ingest.embed_and_load_chunks

Page numbers: SEC 10-K HTML files have no real page structure, so docling
emits no page provenance for them and document_chunks.page stays NULL
(verified with docling 2.129). The column remains for PDF ingestion later.
