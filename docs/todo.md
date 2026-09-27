# Document Copilot — implementation checklist

Work **in this order**. Do not skip ahead to the LLM or pretty chat UI until the layer below it is real.

**Start with the database, then the backend, then the frontend.**

- **Database first** because auth, chats, filings, chunks, embeddings, and citations all live in Supabase. Without a project and a schema, nothing else can persist.
- **Backend second** because it owns schema (Alembic), token verification, retrieval, grounding, and OpenAI. The browser must never hold the service-role key or call OpenAI.
- **Frontend last (for each slice)** because it is a thin SPA: session, chat UI, citations. Build UI against a working API contract, not against stubs you will throw away.

The architecture already encodes this sequence (`docs/architecture.md` → Implementation Sequence). This file turns that into a working checklist against the client brief.

Mark items `[x]` as you finish them. Keep the current phase until its "done when" is true.

---



## Phase 0 — Accounts, env, local tools

Goal: you can run empty services and talk to a hosted Supabase project.

- [x] Install Python 3.12+, `uv`, Node 20+, `pnpm` (see root `README.md`)
- [x] Create a hosted Supabase project (free tier is enough). Follow `docs/guides/supabase-setup.md`
- [x] Copy credentials into `backend/.env` from `backend/.env.example` (`SUPABASE_*`, `DATABASE_URL` **session pooler** (`:5432`) — the direct connection is IPv6-only and unreachable from WSL2; transaction pooler (`:6543`) is still rejected)
- [x] Copy public credentials into `frontend/.env` from `frontend/.env.example` (`VITE_*` only — never `service_role`)
- [x] Create an GEMINI API key; put it in `backend/.env` (needed from Phase 5 onward)
- [ ] Auth: Email provider on; for local dev, disable "Confirm email" so sign-up works without inbox access
- [ ] Confirm `data/download.py` `USER_AGENT` is set to a real contact email before hitting EDGAR

**Done when:** both `.env` files exist locally, are gitignored, and the Supabase project is healthy.

---



## Phase 1 — Scaffold backend + schema (database via Alembic)

Goal: FastAPI boots, settings fail fast, and Supabase has the product tables.

Backend

- [x] `cd backend && uv sync` then add locked stack deps (`fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `httpx`, `structlog`, `openai`, `supabase`, `pydantic-ai`, `sqlalchemy`, `alembic`, `psycopg[binary]`, `pgvector`; dev: `pytest`, `ruff`)
- [x] `app/config.py` — pydantic-settings; fail fast if required env is missing; never `os.getenv` / `load_dotenv` in app code
- [x] `app/main.py` — FastAPI app, CORS from `ALLOWED_ORIGINS`, health route
- [x] `uv run alembic init alembic`; `env.py` imports SQLAlchemy metadata and `settings.DATABASE_URL` (direct/session URL only)
- [x] `app/database/models/` package — `profiles`, `chat_threads`, `chat_messages`, `message_citations`, `source_documents`, `document_chunks` (one file per model + constants)
- [x] First reviewed migration: `vector` extension, tables, `vector(1536)`, generated `tsvector`, HNSW + GIN indexes, RLS + policies, grants (`alembic/versions/2026_09_25-0001_initial_schema.py`; written, reviewed, and applied)
- [x] `uv run alembic upgrade head` against the hosted project
- [x] `app/database/supabase.py` — user-scoped vs service-role clients

**Done when:** `uv run uvicorn app.main:app --reload` starts, `/health` works, and the six tables exist in Supabase with `pgvector` enabled.

Do **not** create production tables in the dashboard. Alembic is the source of truth.

---



## Phase 2 — Scaffold frontend + auth (thin vertical slice)

Goal: an analyst can sign in with email and hit a protected backend route.

Frontend scaffold

- [x] `cd frontend && pnpm create vite . --template react-ts` (or equivalent), Tailwind + shadcn, React Router (Vite + React 19 scaffold; Tailwind v4 via `@tailwindcss/vite`; shadcn initialized with Nova preset — `components.json`, theme tokens in `src/index.css`, first primitives in `src/components/ui/`. `react-router-dom` installed but **routes not wired yet** — `App.tsx` is still the starter template, see auth pages below)
- [x] `src/lib/env.ts` — validate `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` at boot
- [x] `src/lib/supabase.ts` — browser client (anon key only)
- [x] Sign-in / sign-up pages (email only, no SSO) — `src/pages/sign-in.tsx`, `src/pages/sign-up.tsx`; plain-password errors, sign-up handles both "confirm email on" and "off" flows
- [x] Auth gate: unauthenticated users cannot reach chat routes — `AuthProvider` (`src/lib/auth-provider.tsx`) + `RequireAuth` (`src/components/auth/RequireAuth.tsx`); router wired in `App.tsx`

Backend auth

- [x] `app/auth/dependencies.py` — verify `Authorization: Bearer <supabase JWT>` via Supabase Auth user endpoint; expose `get_current_user` (token checked against `/auth/v1/user` through the service-role client — no local JWT parsing, so revoked tokens fail immediately; unit tests in `tests/auth/test_dependencies.py`)
- [x] Reject missing/invalid tokens with `401` before any retrieval or LLM work (`HTTPBearer(auto_error=False)` + explicit 401s with `WWW-Authenticate: Bearer`; verification happens before any DB, retrieval, or LLM work)
- [x] Create/read `profiles` row for the authenticated user (first sign-in inserts via service role — profiles RLS is intentionally select-own-only; stale email updates in place)

Glue

- [x] `src/lib/http.ts` + `src/lib/api.ts` — `fetch` wrapper, base URL, bearer injection, timeouts, typed errors (network vs HTTP)
- [x] One protected probe endpoint (e.g. `GET /me`) so you can prove the JWT round-trip in the browser — `backend/app/auth/routes.py` + placeholder chat page at `/` calling it

**Done when:** you can sign up, sign in, and see your user from FastAPI in the browser. Chat UI can still be empty.

---



## Phase 3 — Chat persistence + streaming stub

Goal: threads and messages persist per user; the UI streams *something* from FastAPI. No real retrieval yet.

Backend

- [ ] `app/database/chats.py` — create/list/get threads; list messages; enforce owner (`403` on other users' threads)
- [ ] REST: list/create threads, load message history
- [ ] `POST /chat/stream` — AI SDK-compatible stream of a **stub** assistant reply
- [ ] Persist user + assistant messages only after a successful stub turn
- [ ] `app/chat/messages.py` — AI SDK UI messages ↔ internal types

Frontend

- [ ] Chat routes and thread sidebar (own conversations only)
- [ ] `useChat` + `DefaultChatTransport` pointed at FastAPI `/chat/stream` (not a Vite/Next route)
- [ ] Empty states, loading/streaming status, auth/network error messages

**Done when:** a signed-in analyst can start a thread, send a message, see a streamed stub reply, refresh, and still see history.

---



## Phase 4 — Corpus intake (ingestion before retrieval)

Goal: sample 10-Ks are parsed, chunked, embedded, and stored so search has something to search.

- [ ] Run `uv run data/download.py` from repo root; confirm `data/downloads/` + `manifest.json` (payloads stay gitignored)
- [ ] `backend/ingest/` — HTML/filing → normalized Markdown → `source_documents` (ticker, company, form type, filing date, year, accession, source URL)
- [ ] Chunker: stable chunk index, page/section metadata, token count, metadata JSON (ticker, year, page, section, offsets)
- [ ] Embeddings via configured OpenAI model/dimensions; write `document_chunks.embedding`
- [ ] Populate generated `search_vector` (or confirm the generated column works)
- [ ] Idempotent re-ingest (re-run does not duplicate filings)
- [ ] Unit tests for parse/chunk (no network); optional `@pytest.mark.integration` for a live embed write

**Done when:** Apple / Amazon / Alphabet / Microsoft / NVIDIA sample 10-Ks exist as documents + chunks in Supabase, with embeddings and full-text vectors.

---



## Phase 5 — Hybrid retrieval (no LLM yet)

Goal: a question returns ranked, citable passages. Test this without OpenAI generation.

- [ ] Embed the query with the same embedding model as ingest
- [ ] `app/retrieval/queries.py` — `pgvector` similarity over `document_chunks.embedding`
- [ ] Postgres full-text search over `document_chunks.search_vector`
- [ ] `app/retrieval/fusion.py` — Reciprocal Rank Fusion in Python
- [ ] `app/retrieval/retriever.py` — fetch chunks + source metadata + optional neighbor chunks
- [ ] Bounded agent tools later: `search_filings`, `read_chunk`, `read_surrounding_chunks` (no generated SQL)
- [ ] Unit tests with fixture rankings; one integration test against the ingested corpus

**Done when:** you can retrieve relevant passages for a question like "Apple iPhone vs Services revenue mix" without calling the chat model.

---



## Phase 6 — Grounded assistant (PydanticAI + citations)

Goal: answers come only from retrieved passages; citations are validated in code, not just in the prompt.

- [ ] `app/assistant/outputs.py` — `GroundedAnswer`, `Citation`, `SourcePassage`
- [ ] `app/assistant/deps.py` — `DocumentAgentDeps` (user, thread, retriever, validator)
- [ ] `app/assistant/instructions.md` — answer only from passages; cite every factual claim; refuse if evidence is missing; no stock picks or investment advice
- [ ] `app/assistant/agent.py` — PydanticAI agent with typed deps/output and retrieval tools
- [ ] `app/grounding/validator.py` — every citation maps to a retrieved chunk; model cannot cite what was not retrieved; insufficient evidence is an explicit, cited-empty refusal
- [ ] Failed validation → controlled error, not a polished unsupported answer
- [ ] `app/chat/orchestrator.py` — one turn: auth context → retrieve → generate → validate → stream → persist messages, citations, usage
- [ ] Stream text deltas, then structured citation/source parts, in AI SDK format
- [ ] Unit tests: citation extraction, grounding pass/fail, "not in corpus" path (mock LLM; still assert the grounding contract)

**Done when:** a live question returns a streamed answer with citations that match stored chunks, and an out-of-corpus question refuses instead of inventing.

---



## Phase 7 — Trust UI (what the analyst actually needs)

Goal: the analyst can verify every claim in one click.

- [ ] Render citations: company, filing, date, page/section
- [ ] Click a citation → show underlying passage excerpt
- [ ] Insufficient-evidence state is visually distinct from a sourced answer
- [ ] Distinguish 401 / 403 / 404 / 422 / 502 / 500 and network/CORS in the UI
- [ ] Thread titles / timestamps good enough for "see my past conversations"

**Done when:** you can answer one sample brief question end-to-end in the browser and open the cited passage without leaving the app.

---



## Phase 8 — Client-brief evaluation (definition of done)

The product is not "chat works." It is "intake is faster and answers are trustworthy." Use the ten example questions in `docs/client-breif.md`.

For each question:

- [ ] 1. Apple 2021–2025 revenue mix (iPhone, Services, Mac, iPad, Wearables)
- [ ] 2. Amazon AWS vs NA / International income and margin
- [ ] 3. NVIDIA Data Center demand, concentration, supply constraints
- [ ] 4. Microsoft Azure / AI infrastructure / cloud capacity language over time
- [ ] 5. Alphabet Search, YouTube, Network, subscriptions/devices, Cloud trends
- [ ] 6. Risk-factor language changes (AI, cloud, export controls, supply chain, regulation)
- [ ] 7. Apple + NVIDIA supplier / third-party manufacturing language over time
- [ ] 8. Capex and purchase commitments (MSFT, GOOGL, AMZN, NVDA)
- [ ] 9. Geographic revenue exposures, latest 10-K + YoY changes
- [ ] 10. "Did generative AI improve margins?" — evidence only; refuse inference beyond filings

Pass bar for each: sourced, page/filing cited, passage visible, no invented numbers, no stock recommendations.

Also:

- [ ] Domain-gated login is "Driftwood email" in spirit for the pilot (email auth is enough; no SSO)
- [ ] Corpus stays SEC filings only — no news, no alt data
- [ ] Backend tests: ingest, retrieval, citations, grounding (`pytest -m "not integration"` stays green)

**Done when:** a pilot analyst can run those questions for a week and you would believe a "saves ≥3 hours/week" report.

---



## Phase 9 — Hosting (after the product works locally)

- [ ] Railway: FastAPI (Uvicorn) service with backend env vars
- [ ] Railway: static Vite frontend with `VITE_*` public env
- [ ] CORS / `ALLOWED_ORIGINS` set to the real frontend origin
- [ ] Re-enable email confirmation if you disabled it for local signup
- [ ] Confirm Alembic has been applied to the project the production backend uses
- [ ] Smoke: sign in → ask a cited question → open a passage

**Done when:** the five-analyst pilot can use the hosted URL without touching your laptop.

---



## Explicitly out of scope (do not put on the board)

- Trading recommendations or stock picks
- News, social, or alternative data
- Analysis not grounded in the corpus
- Multi-tenant / external clients
- Billing, plans, paywalls
- Native mobile app
- Next.js, SSR, or frontend OpenAI calls
- A second vector database besides Supabase `pgvector`

---



## Suggested cadence (if you want a weekly rhythm)


| Week | Focus                                        |
| ---- | -------------------------------------------- |
| 1    | Phases 0–2: project, schema, sign-in, `/me`  |
| 2    | Phase 3–4: stub chat + ingest sample 10-Ks   |
| 3    | Phase 5–6: hybrid retrieval + grounded agent |
| 4    | Phase 7–8: trust UI + ten brief questions    |
| 5    | Phase 9 + pilot hardening                    |


Start **Phase 0 + Phase 1** next: hosted Supabase, `backend/.env`, FastAPI + Alembic, first migration. The frontend waits until `/health` and tables exist.