"""Ingest pipeline: convert → chunk → embed → load into Supabase.

Each stage is a runnable module (from backend/):
    uv run python -m app.ingest.load_source_documents
    uv run python -m app.ingest.chunk_documents
    uv run python -m app.ingest.embed_and_load_chunks --smoke

convert_to_docling_json needs a docling-capable environment — see its
docstring for the exact invocation.
"""
