# ColdMail — Developer Quickstart

Cold email outreach platform (single-tenant). FastAPI backend + Next.js 15 frontend + Postgres 16.
See `../specs/001-cold-email-platform/` for the specification, plan, and task list.

## Local development

Prerequisites: Docker + Docker Compose, Python 3.12, Node 20+, pnpm, `uv`.

```bash
cp .env.example .env

# Fill in the two required secrets:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # -> FERNET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                                # -> SESSION_SECRET
# Set INITIAL_MASTER_PASSWORD to whatever you want to log in with the first time.

docker compose up --build
```

- Backend at `http://localhost:8000` (API root `/api/v1`).
- Frontend at `http://localhost:3000`.
- Postgres at `localhost:5432` (user/db `coldmail`, password `coldmail` — local only).

The backend runs Alembic migrations on start.

## Running tests

Backend:
```bash
cd backend
uv sync
uv run pytest                         # unit + contract (vcrpy) + integration (testcontainers)
LIVE_INTEGRATION=1 uv run pytest -m live   # smoke against real Hunter / OpenAI / SMTP
```

Frontend:
```bash
cd frontend
pnpm install
pnpm test          # vitest units
pnpm test:e2e      # playwright — requires docker compose up
```

## Deploying to Railway

Three services in a single Railway project:
1. Postgres add-on (Railway-managed).
2. `backend` service, root `outreach/backend`, Dockerfile-based. Env:
   `DATABASE_URL` (from Postgres), `FERNET_KEY`, `SESSION_SECRET`, `INITIAL_MASTER_PASSWORD`
   (removed after first-run bootstrap).
3. `frontend` service, root `outreach/frontend`, Dockerfile-based. Env:
   `NEXT_PUBLIC_API_URL` = backend's public URL.

First backend start runs Alembic; visit the frontend URL, bootstrap the master password, log in,
open Settings, paste API keys and SMTP credentials, off you go.

## Fernet key rotation runbook

1. Provision the new key (`Fernet.generate_key()`).
2. In a one-off container with both keys available:
   ```python
   from cryptography.fernet import Fernet, MultiFernet
   old, new = Fernet(OLD_KEY), Fernet(NEW_KEY)
   mf = MultiFernet([new, old])   # new first: writes with new, still decrypts old
   ```
3. Load each settings row, `mf.rotate(ciphertext)` each `_ct` column, save.
4. Deploy with `FERNET_KEY=<new>`.
5. Retire the old key.

Manual by design — one deployment, one operator, no key-management service (see
`../specs/001-cold-email-platform/research.md` R6).

## Layout

```text
outreach/
├── docker-compose.yml
├── .env.example
├── backend/          # FastAPI + SQLAlchemy + Alembic (Python 3.12)
├── frontend/         # Next.js 15 App Router (TypeScript)
├── cold_email_pipeline.py   # reference-only; not imported by the app
└── prompt.txt        # reference-only; source content for seeded Prompt row
```
