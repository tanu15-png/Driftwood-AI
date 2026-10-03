# Deploy Document Copilot on Railway

This guide uses two Railway services from the same GitHub repository: `backend`
for FastAPI and `frontend` for the React SPA. Keep the existing Supabase project
for Postgres and authentication. Gemini remains an external API; embeddings run
on the backend CPU with `BAAI/bge-small-en-v1.5`.

These are deployment instructions, not a record of a completed Railway deployment.
Settings were checked against the repository and official documentation on
2026-10-03.

## Is Docker needed?

**No Docker installation or custom Dockerfile is required for this deployment.**
Railway's Railpack builder creates the container image from the application.
It supports this project's Python/uv backend and Vite/pnpm frontend.
Start with Railpack. [Railway build configuration](https://docs.railway.com/builds/build-configuration),
[Railpack Python support](https://railpack.com/languages/python/).

A custom Dockerfile becomes useful if you need to control Linux packages,
reproduce the exact runtime locally, or bake the embedding model into the image
so a new instance does not need a model download. Those are reasons to choose
Docker later, rather than requirements of FastAPI, Supabase, or Gemini.
Railway also supports Dockerfile builds. [Dockerfile deployment](https://docs.railway.com/builds/dockerfiles).

The path below uses a persistent model cache and downloads/prepares the model
before starting FastAPI. No Dockerfile is added by following it.

## 1. Prepare the repository and Supabase

Push the intended application changes to GitHub, including `backend/uv.lock`
and `frontend/pnpm-lock.yaml`. Keep `.env`, `.venv`, `node_modules`, downloaded
filings, and model caches out of Git. Set credentials through Railway Variables.

Decide which Supabase project the deployment will use:

- **Existing populated project:** the API can retrieve its existing filings and
  embeddings. Deployment does not require re-ingesting the corpus.
- **New project:** configure Supabase Auth, apply the Alembic migrations, and
  populate the corpus separately using [backend ingestion instructions](backend/README.md#corpus-ingestion-and-retrieval).
  An empty database cannot answer filing questions.

`DATABASE_URL` must be a session-pooler connection on port `5432`, or a direct
connection with working network connectivity. This app rejects the transaction
pooler on port `6543`. Copy the connection details from your Supabase project;
URL-encode special characters in the database password.

Review migrations before targeting a populated database. In particular,
`0003_local_embeddings` clears incompatible old embeddings when upgrading from
the previous embedding schema; that upgrade needs a full re-embedding.

## 2. Create two Railway services

Create a Railway project and two services connected to the same GitHub repo.
Configure their root directories before deploying:

| Setting | Backend | Frontend |
| --- | --- | --- |
| Service name | `backend` | `frontend` |
| Root directory | `/backend` | `/frontend` |
| Builder | Railpack | Railpack |
| Watch paths | `/backend/**` | `/frontend/**` |

This is an isolated monorepo: each service builds from its own directory.
Commands below therefore run inside that service directory; do not prepend
`cd backend` or `cd frontend`. [Railway monorepo setup](https://docs.railway.com/deployments/monorepo).

## 3. Configure and deploy the backend

### Variables

Set these on the **backend service only**. Replace placeholders with real values.

| Variable | Value |
| --- | --- |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | Your project's public anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Your project's secret service-role key |
| `DATABASE_URL` | Your Supabase session/direct connection URL |
| `GEMINI_API_KEY` | Your Gemini key |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite`, or an available model verified for your key |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` |
| `EMBEDDING_CACHE_DIR` | `/models/embeddings` |
| `ALLOWED_ORIGINS` | The frontend's actual HTTPS origin, without a trailing slash |
| `RAILPACK_PYTHON_VERSION` | `3.12` |
| `RAILWAY_HEALTHCHECK_TIMEOUT_SEC` | `600` initially; adjust to measured startup time |
| `COHERE_API_KEY` | Optional; omit unless using the reranker |

If the frontend domain is not available yet, `http://localhost:5173` can be used
for the initial backend boot. Replace it with the deployed frontend origin and
redeploy the backend before testing the hosted UI. Multiple allowed origins use
a comma-separated string, for example
`https://<frontend-domain>,http://localhost:5173`.

### Embedding cache

Attach a Railway volume to the backend at **`/models`**. The application uses
`/models/embeddings` for both the ONNX model and tokenizer. Start with one backend
replica and one Uvicorn worker; extra workers load separate model instances.
Measure memory under load before increasing concurrency. A GPU is not required.

The current FastAPI lifespan calls `create_model()` in cache-only mode. Starting
Uvicorn alone on a fresh deployment will fail because the gitignored local cache
is absent. The startup command below runs the existing model preparation module
first, then launches the API. Subsequent starts can reuse downloaded files.
The bootstrap can still check remote model metadata, so allow outbound access.

Volumes are mounted at runtime, not during builds or pre-deploy commands. Prepare
the cache in the **start command**, not the migration command.
[Railway volume behavior](https://docs.railway.com/volumes).

### Build, migration, and startup commands

**Build command:**

```sh
uv sync --frozen --no-dev
```

This installs locked runtime dependencies without the development group, which
includes the heavier document-conversion tools.

**Pre-deploy command:**

```sh
uv run --no-sync alembic upgrade head
```

Alembic imports settings but does not start FastAPI or require the embedding
cache. A failed migration blocks deployment. Run one migration owner per
database; do not deploy multiple services running migrations against it at once.
[Railway pre-deploy commands](https://docs.railway.com/deployments/pre-deploy-command).

**Start command** (paste the complete line):

```sh
sh -c 'uv run --no-sync python -m app.embeddings && exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port "$PORT"'
```

The explicit shell expands Railway's `PORT`; `&&` stops startup if model
preparation fails. Do not use `--reload` in production.

Set **Healthcheck Path** to `/health`. The first model download may lengthen
startup; check logs rather than repeatedly restarting the service. Railway
routes traffic after the healthcheck succeeds. `/health` confirms the app has
started, including model initialization; it does not verify a live Gemini call
or database retrieval. [Railway healthchecks](https://docs.railway.com/deployments/healthchecks).

Deploy, generate a public HTTPS domain under Networking, and verify:

```sh
curl https://<backend-domain>/health
```

Expected response: `{"status":"ok"}`. Use this public backend URL for the browser;
a `railway.internal` hostname cannot be reached by users' browsers.

## 4. Configure and deploy the frontend

Set these on the **frontend service** before its production build:

| Variable | Value |
| --- | --- |
| `VITE_API_BASE_URL` | `https://<backend-domain>` |
| `VITE_SUPABASE_URL` | The same Supabase project's URL |
| `VITE_SUPABASE_ANON_KEY` | The same project's public anon key |
| `RAILPACK_NODE_VERSION` | `24` |
| `RAILPACK_SPA_OUTPUT_DIR` | `dist` |

Set **Build command** to `pnpm build`. Railpack detects `pnpm-lock.yaml` and
installs dependencies. Keep development dependencies available during the build:
TypeScript and Vite are needed to produce `dist`.

Leave **Start command empty**. Railpack recognizes Vite and serves the built
SPA with Caddy, including client-side route fallback. Setting a custom start
command disables that automatic static-site path. Do not deploy `pnpm dev` or
`pnpm preview` as the production web server.
[Railpack Node and Vite SPA deployment](https://railpack.com/languages/node/).

Generate the frontend's public HTTPS domain. Set backend `ALLOWED_ORIGINS` to
that exact origin and redeploy the backend. In Supabase Auth's URL configuration,
set the Site URL to the frontend URL and configure allowed redirect URLs for
any confirmation/recovery flows you use.
[Supabase redirect configuration](https://supabase.com/docs/guides/auth/redirect-urls).

Vite embeds `VITE_*` values into JavaScript at **build time**. Changing these
variables requires rebuilding/redeploying the frontend. They are public:
never put the Gemini key, database URL, or service-role key in this service.
[Vite environment variables](https://vite.dev/guide/env-and-mode).

## 5. Verify the deployed application

1. Open the frontend and sign in with a user from the configured Supabase project.
2. Confirm threads load, then ask a specific filing question such as
   "What drove Apple's Services sales growth in fiscal 2024?"
3. Check the streamed answer, citation sidebar, and original SEC link.
4. Refresh and reopen the conversation to check persisted history.
5. Open a conversation URL directly and refresh it to check SPA route fallback.
6. Ask an out-of-corpus question and confirm the insufficient-evidence state.
7. Delete a temporary conversation and confirm it disappears after refresh.

Use the existing corpus in Supabase. Model-cache preparation only downloads
embedding software; it does not load filings. Do not run full corpus conversion
or embedding ingestion on every API startup.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Backend fails before serving requests | Required backend variables, migration logs, and model bootstrap logs |
| Model/tokenizer cache missing | `/models` volume, `EMBEDDING_CACHE_DIR`, and complete startup command |
| Deployment healthcheck times out | Listen on `0.0.0.0:$PORT`; inspect download time and memory usage |
| UI cannot reach backend | Public HTTPS API URL, frontend rebuild, and exact backend CORS origin |
| Refreshed conversation URL returns 404 | Frontend SPA mode and absence of a custom start command |
| Supabase connection fails | Correct project/password and reachable session-pooler port `5432` |
| Authentication fails | Both services use the same Supabase project and the correct public key |
| Gemini returns quota/model errors | Key quota and model availability; Docker does not change API quota |
| Answers lack filing evidence | Confirm corpus loading in the target database and inspect retrieval |
| Process exits from memory pressure | Railway memory metrics; use one worker and adjust allocated resources |

For later releases, push changes to the connected branch. Review database
migrations before deployment, and rebuild the frontend whenever its API URL or
public auth configuration changes. An application rollback does not undo
database migrations.
