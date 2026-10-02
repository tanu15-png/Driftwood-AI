# Backend — Document Copilot API

FastAPI service that owns auth verification, retrieval, LLM orchestration, and chat persistence.

## Setup

Prereqs: Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
cd backend
cp .env.example .env   # fill in Supabase credentials and GEMINI_API_KEY
uv sync
```

All env vars are defined in `app/config.py` — the single source of truth.

## Run

```bash
uv run uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/health`

## Database migrations

Schema changes flow: edit `app/database/models.py` → generate → review → apply.

```bash
uv run alembic revision --autogenerate -m "describe change"   # review output in alembic/versions/
uv run alembic upgrade head
```

`DATABASE_URL` must keep session state: use the **session pooler** (`pooler.supabase.com:5432`, IPv4 — required on IPv6-less networks like default WSL2) or the direct connection (`db.<ref>.supabase.co`, IPv6). Never the transaction pooler (`:6543`) — config fails fast on it.

## Tests & lint

```bash
uv run pytest -m "not integration"   # fast suite: no network, no DB
uv run ruff check .
```

Integration tests (Gemini generation, local model/Supabase, plus Cohere when configured) run with `uv run pytest -m integration`.
The live chat test creates temporary confirmed accounts, checks auth and saved
grounded streaming history and an out-of-corpus refusal, then removes those accounts and their profiles without
sending confirmation emails. Corpus integration tests require a full chunk load.

Phase 4–5 verification on 2026-10-02: 82 unit tests and four live integration tests passed.
The hosted corpus contains 11,900 embedded passages across 25 filings, with
generated full-text search vectors for every passage. The initial CPU embedding
pass took about 53 minutes on the development machine.

## More

- Setup details: [docs/guides/backend-setup.md](../docs/guides/backend-setup.md)
- Conventions: [AGENTS.md](AGENTS.md)
- Architecture: [docs/architecture.md](../docs/architecture.md)
- Retrieval and grounding with Mermaid: [pipeline](../docs/retrieval-and-grounding.md)

## Grounded chat

Set `GEMINI_API_KEY` in `.env`; `GEMINI_MODEL` defaults to `gemini-3.5-flash-lite`.
API startup fails if the generation key or prepared local embedding cache is
missing. Model clients live in application state and are reused between turns.

Phase 6 generates typed claims with Gemini through PydanticAI, checks every
citation against retrieved chunks and verbatim quotes, then streams validated
text plus citation/source/status parts. Unsupported questions and investment
advice produce explicit refusals with no citations. Messages, normalized
citations, and usage metadata commit atomically before the successful stream
finish. The frontend citation viewer is planned for phase 7.

Phase 6 verification on 2026-10-02: 111 unit tests pass, as do the three corpus
integration tests and the live Gemini/auth/chat integration test. The live chat
test checks Apple FY2024 sales with persisted source quotes and a citation-empty
out-of-corpus refusal. See [todo.md](../docs/todo.md) for the checklist.

## Corpus ingestion and retrieval

Embeddings run locally on CPU using `BAAI/bge-small-en-v1.5` through FastEmbed's
ONNX runtime. Corpus passages and questions use the same model and 384 dimensions.
No embedding API key is required. `python -m app.embeddings` downloads the model and tokenizer
into `backend/.cache/embeddings` (gitignored); retain this directory between runs.
Ingestion and retrieval load only cached files, so they can run without internet
access to Hugging Face after setup. Supabase still requires a database connection.

Run these commands from `backend/`:

```bash
uv sync
uv run python -m app.embeddings
uv run alembic upgrade head
uv run python -m app.ingest.load_source_documents
uv run python -m app.ingest.chunk_documents
uv run python -m app.ingest.embed_and_load_chunks --smoke
uv run python -m app.ingest.embed_and_load_chunks
uv run python -m app.retrieval "Apple iPhone vs Services revenue mix" --ticker AAPL --neighbors
uv run pytest tests/retrieval/test_integration.py -m integration
```

Smoke mode updates one chunk without removing other chunks. Full loads upsert
by filing and chunk index, preserve IDs, and remove obsolete indices per filing.
Each filing commits atomically. SEC HTML pages and character offsets remain null;
`doc_item_refs` retain Docling source anchors. Chunking uses the model's tokenizer
with a 480-token target. Inference rejects inputs above 510 tokens instead of
silently truncating them (the model also needs two special tokens).
Retrieval applies ticker/year filters before candidate limits, fuses vector and
full-text rankings with RRF, and returns passage text and filing metadata. It
runs CPU embeddings and the optional Cohere reranker. The standalone retrieval CLI does not invoke generation.
`app/retrieval/tools.py` bounds search results to 20 and context windows to three
chunks on either side for future assistant integration.

Before loading documents, run `app.ingest.convert_to_docling_json` in the
dedicated Docling environment described in `data/README.md`. It writes both the
Docling and Markdown manifests from the same successful conversions.

Migration `0003_local_embeddings` changes the vector column from 1536 to 384
dimensions and clears the incompatible embeddings while retaining passage text
and IDs. Re-chunk and fully re-embed the corpus after applying it. Downgrading
also requires a full re-embedding with the previous model.

FastEmbed supplies model download, ONNX inference, pooling, and normalization;
implementing these correctly is more than a small helper. It is used for every
ingestion and semantic query. Its CPU runtime adds ONNX Runtime and model/cache
dependencies; it does not add a database or require a GPU. Hugging Face Hub
downloads the tokenizer once; the Rust `tokenizers` library counts exact tokens
without relying on this environment's incompatible PyTorch/Transformers import.
