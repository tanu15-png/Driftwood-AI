# Document Copilot — implementation checklist

Work **in this order**. Do not skip ahead to the LLM or pretty chat UI until the layer below it is real.

**Start with the database, then the backend, then the frontend.**

- **Database first** because auth, chats, filings, chunks, embeddings, and citations all live in Supabase. Without a project and a schema, nothing else can persist.
- **Backend second** because it owns schema (Alembic), token verification, retrieval, grounding, and Gemini. The browser must never hold the service-role key or call Gemini.
- **Frontend last (for each slice)** because it is a thin SPA: session, chat UI, citations. Build UI against a working API contract, not against stubs you will throw away.

The architecture already encodes this sequence (`docs/architecture.md` → Implementation Sequence). This file turns that into a working checklist against the client brief.

Mark items `[x]` as you finish them. Keep the current phase until its "done when" is true.

## Verification — 2026-10-02

- Phases 1–3: implemented. Hosted database is at `0003_local_embeddings`; frontend production build and lint pass. The live auth/chat test now exercises the Phase 6 assistant: temporary accounts sign in, `/me` verifies real tokens, missing/invalid tokens return 401, another user's thread returns 403, grounded answers stream, and persisted messages reload. Temporary accounts and profiles were removed after the test.
- Phase 4: all 25 source filings are in Supabase (five each for AAPL, AMZN, GOOGL, MSFT, NVDA). Rebuilding with BGE's tokenizer produced 11,900 hybrid passages and 28,076 hierarchical chunks. The 59 passages above the 480-token target fit the hard content limit of 510; the maximum is 500. All 11,900 passages have embeddings and generated search vectors after migration `0003_local_embeddings`; initial CPU embedding took 3,197.7 seconds (about 53 minutes).
- The user requested a switch to local Hugging Face embeddings after Gemini quota failures. BAAI/bge-small-en-v1.5 is installed via FastEmbed CPU ONNX; its model and Rust tokenizer are downloaded. Local inference produces 384-dimensional vectors. Normal ingestion/retrieval use cached files only; no Gemini API key or embedding quota is needed.
- Phase 5: complete. Live hybrid retrieval finds Apple iPhone/Services revenue passages with filing URLs; ticker filtering, exact chunk reads, and surrounding chunks pass. All stored chunks record the local BGE model and 384 dimensions. Full filing re-ingestion and smoke mode preserve existing chunk IDs.
- Phase 6: implemented and live-verified with Gemini `gemini-3.5-flash-lite`. Typed claims/citations, a per-turn evidence ledger, exact quote validation, explicit refusals, validated SSE, and atomic message/citation/usage persistence replace the stub. Apple FY2024 sales produces stored, citable evidence; the Mars weather question refuses with no citations or sources. Gemini 2.5 Flash returned 404 for this key's new-user account, so the configured default is the available 3.5 Flash-Lite model. `GEMINI_API_KEY` replaces the previous generation-key setting; embeddings remain local.
- Browser interaction has not been manually verified during this audit; frontend verification covers TypeScript compilation, production build, and lint.
- Backend validation: 111 unit tests passed; three corpus integration tests and the live Gemini/auth/chat integration test passed. Ruff and `git diff --check` pass. The live tests cover generation/refusal, real auth and grounded chat persistence, local vector normalization, chunk re-ingestion, and full-corpus retrieval.

## Verification — 2026-10-03

- Phase 7's five implementation tasks are complete: citation/filing metadata, in-app quote and passage inspection, distinct refusal states, status-specific errors, and thread titles/timestamps. Stream authentication and new-thread draft/history ordering are fixed.
- Backend: 124 unit tests passed (4 integration tests deselected), including automatic title generation and preserving an existing title. Ruff passes. Keyword retrieval was separately live-verified against Supabase after the previous change.
- Frontend: strict TypeScript check (`pnpm exec tsc --noEmit --strict -p tsconfig.app.json`), production build, and lint pass. Manual browser acceptance remains pending because no browser tool or installed browser is available in this environment; see the Phase 7 smoke checklist. No frontend test runner or runtime dependency was added.
- Follow-up 502 repair: reproduced `UsageLimitExceeded` on the live Apple sales question. Retrieval tools now stop with two requests reserved for output/correction; grounding failures use one bounded correction attempt with validation unchanged. Provider quota/model/credential errors have safe, specific messages. The error banner uses the latest AI SDK error state instead of a separate stale copy. Verification: 133 unit tests, live Gemini/auth/chat answer-and-refusal integration, Ruff, frontend production build, and lint pass. User browser feedback also confirms an Alphabet citation and in-app filing excerpt render; the remaining refresh/refusal browser checks are still pending.
- Light-layout/source-sidebar/delete update: 140 backend unit tests pass. The live chat integration test passes for sourced answers, refusals, ownership-protected deletion, missing/deleted-thread responses, and cascading removal of messages/citations; temporary accounts are cleaned up. Strict frontend TypeScript and production build pass. The new layout's visual browser review remains pending.

---



## Phase 0 — Accounts, env, local tools

Goal: you can run empty services and talk to a hosted Supabase project.

- [x] Install Python 3.12+, `uv`, Node 20+, `pnpm` (see root `README.md`)
- [x] Create a hosted Supabase project (free tier is enough). Follow `docs/guides/supabase-setup.md`
- [x] Copy credentials into `backend/.env` from `backend/.env.example` (`SUPABASE_*`, `DATABASE_URL` **session pooler** (`:5432`) — the direct connection is IPv6-only and unreachable from WSL2; transaction pooler (`:6543`) is still rejected)
- [x] Copy public credentials into `frontend/.env` from `frontend/.env.example` (`VITE_*` only — never `service_role`)
- [x] Download the local embedding model/tokenizer with `uv run python -m app.embeddings`; no embedding API key required (user-requested Hugging Face switch on 2026-10-02).
- [ ] Auth: Email provider on; for local dev, disable "Confirm email" so sign-up works without inbox access
- [ ] Confirm `data/download.py` `USER_AGENT` is set to a real contact email before hitting EDGAR

**Done when:** both `.env` files exist locally, are gitignored, and the Supabase project is healthy.

---



## Phase 1 — Scaffold backend + schema (database via Alembic)

Goal: FastAPI boots, settings fail fast, and Supabase has the product tables.

Backend

- [x] Backend scaffold and locked dependencies (`fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `httpx`, `structlog`, `supabase`, `pydantic-ai`, `sqlalchemy`, `alembic`, `psycopg[binary]`, `pgvector`; dev: `pytest`, `ruff`). Local embeddings use `fastembed`, `huggingface-hub`, and `tokenizers`; Gemini generation belongs to Phase 6.
- [x] `app/config.py` — pydantic-settings; fail fast if required env is missing; never `os.getenv` / `load_dotenv` in app code
- [x] `app/main.py` — FastAPI app, CORS from `ALLOWED_ORIGINS`, health route
- [x] `uv run alembic init alembic`; `env.py` imports SQLAlchemy metadata and `settings.DATABASE_URL` (direct/session URL only)
- [x] `app/database/models/` package — `profiles`, `chat_threads`, `chat_messages`, `message_citations`, `source_documents`, `document_chunks` (one file per model + constants)
- [x] First reviewed migration: `vector` extension, tables, `vector(1536)`, generated `tsvector`, HNSW + GIN indexes, RLS + policies, grants (`alembic/versions/2026_09_25-0001_initial_schema.py`; written, reviewed, and applied)
- [x] `uv run alembic upgrade head` against the hosted project — including reviewed `0003_local_embeddings`: preserve chunk text/IDs, clear incompatible Gemini vectors, change to `vector(384)`, and rebuild the HNSW index.
- [x] `app/database/supabase.py` — user-scoped vs service-role clients

**Done when:** `uv run uvicorn app.main:app --reload` starts, `/health` works, and the six tables exist in Supabase with `pgvector` enabled.

Do **not** create production tables in the dashboard. Alembic is the source of truth.

---



## Phase 2 — Scaffold frontend + auth (thin vertical slice)

Goal: an analyst can sign in with email and hit a protected backend route.

Frontend scaffold

- [x] Vite + React 19 + TypeScript scaffold, Tailwind v4 via `@tailwindcss/vite`, shadcn with Nova preset, and React Router. `App.tsx` wires sign-in, sign-up, and protected chat routes; theme tokens and UI primitives are present.
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
- [x] Protected `GET /me` probe — `backend/app/auth/routes.py`; the frontend API client exposes `api.me()`. The root route now shows the chat UI rather than the former placeholder probe page.

**Done when:** you can sign up, sign in, and see your user from FastAPI in the browser. Chat UI can still be empty.

---



## Phase 3 — Chat persistence + streaming stub

Goal: threads and messages persist per user; the UI streams *something* from FastAPI. No real retrieval yet.

Backend

- [x] `app/database/chats.py` — create/list/get threads; list messages; enforce owner (`403` on other users' threads; unknown threads are `404`)
- [x] REST: list/create threads, load message history (`GET /threads`, `POST /threads`, `GET /threads/{id}/messages`)
- [x] `POST /chat/stream` — AI SDK-compatible stream of a **stub** assistant reply (UI message stream v1 SSE: `start`/`text-start`/`text-delta`/`text-end`/`finish`/`[DONE]` + `x-vercel-ai-ui-message-stream: v1` header)
- [x] Persist user + assistant messages only after a successful stub turn (both rows commit in one transaction inside the stream generator, after the last byte is yielded; client disconnects skip it)
- [x] `app/chat/messages.py` — AI SDK UI messages ↔ internal types (`from_ui_message` validates user turns only; raw UI message stored in JSONB for replay)

Frontend

- [x] Chat routes and thread sidebar (own conversations only) — `/` (new-chat screen) + `/t/:threadId`; sidebar lists backend threads, most recent first
- [x] `useChat` + `DefaultChatTransport` pointed at FastAPI `/chat/stream` (not a Vite/Next route) — bearer token resolved per request via `prepareSendMessagesRequest` + `authHeaders`; `threadId` sent in the body; per-thread panel keyed by `threadId`
- [x] Empty states, loading/streaming status, auth/network error messages — empty-thread prompt, "thinking…"/"Streaming…" status, typed banners distinguishing 401/403/404/network, stream Retry + Stop

**Done when:** a signed-in analyst can start a thread, send a message, see a streamed stub reply, refresh, and still see history.

---



## Phase 4 — Corpus intake (ingestion before retrieval)

Goal: sample 10-Ks are parsed, chunked, embedded, and stored so search has something to search.

- [x] Run `uv run data/download.py` from repo root; confirm `data/downloads/` + `manifest.json` (payloads stay gitignored) — 25 10-Ks on disk (5 tickers × FY2021–2025) with manifest
- [x] `backend/ingest/` — HTML/filing → normalized Markdown → `source_documents` (ticker, company, form type, filing date, year, accession, source URL) — implemented as `app/ingest/convert_to_docling_json.py` (docling HTML → `DoclingDocument` JSON + Markdown, needs the dedicated docling env) + `app/ingest/load_source_documents.py` (upsert keyed on accession_number); 25/25 rows loaded and verified. `data/convert_to_markdown.py` + `data/download.py` remain the only data/ scripts (download + standalone Markdown conversion)
- [x] Chunker: stable chunk index, section metadata, exact model token counts, and metadata JSON — `app/ingest/chunk_documents.py` uses HybridChunker at 480 BGE tokens and Docling source-item anchors. SEC HTML has no reliable pages or character offsets, so those fields stay NULL; complete output files replace prior files only after a successful run.
- [x] Full local BGE embedding load — `app/ingest/embed_and_load_chunks.py`: all 11,900 passages from 25 filings loaded with CPU inference, 384 dimensions, batched DB upserts, and model/dimensions recorded in metadata. Re-chunking and loading followed migration `0003_local_embeddings`; Gemini quota failures no longer apply.
- [x] Confirm generated `search_vector` works — live SQL verifies 11,900 chunks, 11,900 embeddings, and 11,900 generated tsvectors.
- [x] Idempotent source-document re-ingest — live run 2026-10-02: 0 inserted, 0 updated, 25 unchanged. Fixed the loader's broken manifest constant import; conversion now emits both manifests from the same successful filings. Unit tests cover conversion output/failure manifests, new filing metadata, unchanged filings, and updated Markdown.
- [x] Verify full chunk re-ingest preserves IDs and smoke mode preserves other chunks — live integration test passed in `tests/ingest/test_embed_and_load_chunks.py` after the full corpus load.
- [x] Unit tests for converted filing intake, chunk metadata, token-limit enforcement, vector dimensions, query instruction, and non-truncating token counts (no network). Real CPU model and chunk re-ingest tests are marked `integration`; no embedding API key is required.

**Done when:** Apple / Amazon / Alphabet / Microsoft / NVIDIA sample 10-Ks exist as documents + chunks in Supabase, with embeddings and full-text vectors.

---



## Phase 5 — Hybrid retrieval (no LLM yet)

Goal: a question returns ranked, citable passages. Test this without Gemini generation.

- [x] Embed the query with the same local BGE model as ingest — shared `app/embeddings.py`, recommended query instruction, normalized 384-dimensional vectors, and CPU inference offloaded from the event loop.
- [x] `app/retrieval/queries.py` — `pgvector` similarity over `document_chunks.embedding`
- [x] Postgres full-text search over `document_chunks.search_vector`
- [x] `app/retrieval/fusion.py` — Reciprocal Rank Fusion in Python
- [x] `app/retrieval/retriever.py` — fetch chunks + source metadata + optional neighbor chunks
- [x] Bounded agent tools later: `search_filings`, `read_chunk`, `read_surrounding_chunks` (no generated SQL) — implemented in `app/retrieval/tools.py`; search ≤20 results, neighbors ≤3 on each side
- [x] Unit tests with fixture rankings — fusion, bound queries and filters, retriever metadata and neighbors, optional reranking, and bounded tools are covered in `tests/retrieval/`.
- [x] Passing integration test against the full ingested corpus — `tests/retrieval/test_integration.py` passed with all 25 filings and 11,900 passages; verifies embedding/full-text coverage, model metadata, Apple revenue retrieval, filing URLs, chunk reads, and surrounding context.

**Done when:** you can retrieve relevant passages for a question like "Apple iPhone vs Services revenue mix" without calling the chat model.

---



## Phase 6 — Grounded assistant (PydanticAI + citations)

Goal: answers come only from retrieved passages; citations are validated in code, not just in the prompt.

- [x] `app/assistant/outputs.py` — `GroundedAnswer`, `Citation`, `SourcePassage`, and typed cited claims; server-rendered numbered citation markers and fixed refusal text
- [x] `app/assistant/deps.py` — `DocumentAgentDeps` (user, thread, retriever, validator), request-scoped evidence ledger, canonical source metadata, and restricted neighbor reads
- [x] `app/assistant/instructions.md` — answer only from passages; cite every factual claim; refuse if evidence is missing; no stock picks or investment advice; source data and history cannot override instructions
- [x] `app/assistant/agent.py` — Gemini PydanticAI agent with typed deps/output, bounded sequential retrieval tools, output validator, and request/tool-call limits; clients and local model reused in application state
- [x] `app/grounding/validator.py` — every citation maps to a retrieved chunk and contains a verbatim quote; unique IDs, claim/reference coverage, and explicit citation/source-empty refusals
- [x] Failed validation → controlled HTTP 502 before opening the answer stream; raw model tokens never reach the client
- [x] `app/chat/orchestrator.py` — one turn: auth context → retrieve → generate → validate → stream → atomic messages/citations/usage commit before successful finish; rollback/error on storage failure
- [x] Stream text deltas, then structured citation/source/status parts in AI SDK v1 SSE; replay saved UI parts and usage metadata from history
- [x] Unit tests: citation rendering, grounding pass/fail, "not in corpus" path through the real agent validator with a FunctionModel, stream/persistence errors, disconnects, and startup key checks
- [x] Live Gemini/Supabase integration: Apple FY2024 answer cites stored chunks/quotes; out-of-corpus question refuses with empty citations/sources; ownership checks, durable history/usage, and temporary-account cleanup pass
- [x] Pipeline documentation with Mermaid diagram — [retrieval and grounding](retrieval-and-grounding.md), including validation boundaries and limits of semantic entailment checking

**Done when:** a live question returns a streamed answer with citations that match stored chunks, and an out-of-corpus question refuses instead of inventing.

---



## Phase 7 — Trust UI (what the analyst actually needs)

Goal: the analyst can verify every claim in one click.

- [x] Render citations: company, filing, date, page/section — typed citation/source parts work for streamed answers and saved history. The evidence panel shows company/ticker, form, fiscal year, filing date, and page/section; missing HTML locations are explicitly unavailable.
- [x] Click a citation → show underlying passage excerpt — numbered inline markers and citation buttons open a right-hand source sidebar (drawer on smaller screens); inspect the exact quote, full passage with the quote highlighted, or original SEC filing without inserting evidence between answers.
- [x] Insufficient-evidence state is visually distinct from a sourced answer — amber refusal cards with explicit insufficient-evidence / investment-advice labels, versus cited-evidence answers. Older messages without grounding parts do not receive a sourced-answer label.
- [x] Distinguish 401 / 403 / 404 / 422 / 502 / 500 and network/CORS in the UI — shared error mapping for history/sidebar requests and the authenticated AI SDK transport; also covers retrieval outages (503). Retry and Dismiss clear the stream error banner.
- [x] Thread titles / timestamps good enough for "see my past conversations" — the first successful turn names an untitled conversation from its question (whitespace normalized, 80 characters); existing titles are preserved. Sidebar shows local last-updated timestamps and refreshes after successful turns.
- [x] User-requested ChatGPT-style light layout — full-width white workspace, gray collapsible conversation sidebar, centered answers, rounded multiline composer, and responsive navigation/source drawers.
- [x] Delete conversations — sidebar delete control and confirmation dialog; authenticated backend ownership checks and cascading message/citation removal. Deleting the active conversation stops its stream and returns to the new-chat screen.
- [x] Highlighted original SEC links — citation quotes generate encoded text-fragment links to the actual filing in a new tab, with a plain-link fallback and a best-effort notice. Works for streamed answers and saved history; browser matching is not guaranteed.
- Verification: strict TypeScript, production build, and lint pass. Checked link encoding and the downloaded Apple FY2024 Services sentence; link normalization accounts for the conversion-added space before `®`. Browser scroll/highlight behavior remains unverified.
- [ ] Manual highlighted-link check: open an Apple FY2024 Services citation in a browser supporting text fragments, confirm the original filing highlights the matching sentence, and verify “Open without highlighting”. Also check that unmatched table text still opens the filing normally.

Implementation also fixes missing bearer authentication on `/chat/stream`, waits
for history before sending a new-thread draft, and clears the navigation draft
after sending so refreshing cannot resend it.

- [ ] Manual browser smoke check: sign in, ask “What was Apple's iPhone versus Services revenue mix in fiscal 2024?”, click a numbered citation, inspect the quote/full passage, refresh and reopen the citation, and confirm the conversation title/timestamp. Ask “What is the weather on Mars today?” and confirm the distinct insufficient-evidence state. Implementation is ready; this environment has no browser tool or installed browser, so this check has not been performed.
- [ ] Visual review of the new light layout on desktop/mobile: open and close the source sidebar, switch conversations, and cancel/confirm deletion of a disposable chat.

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
- Next.js, SSR, or frontend Gemini calls
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


Current: Phase 7 implementation is complete; the manual browser smoke check above remains pending. After it passes, proceed to Phase 8's client-brief evaluation. Phase 6 passed live generation, grounding, refusal, streaming, and persistence checks with Gemini and local BGE embeddings.
