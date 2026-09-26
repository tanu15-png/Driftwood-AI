# Backend — Document Copilot API

FastAPI service that owns auth verification, retrieval, LLM orchestration, and chat persistence.

## Setup

Prereqs: Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
cd backend
cp .env.example .env   # fill in Supabase + API keys
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

Integration tests (live OpenAI/Supabase) run with `uv run pytest -m integration`.

## More

- Setup details: [docs/guides/backend-setup.md](../docs/guides/backend-setup.md)
- Conventions: [AGENTS.md](AGENTS.md)
- Architecture: [docs/architecture.md](../docs/architecture.md)
