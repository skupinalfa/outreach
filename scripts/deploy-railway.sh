#!/usr/bin/env bash
# Deploy coldmail (backend + frontend + Postgres) to Railway.
#
# Prerequisites:
#   - Railway CLI: `brew install railway` (macOS) or https://docs.railway.app/develop/cli
#   - Logged in:   `railway login`
#   - Python 3 (only used to generate a Fernet key if $FERNET_KEY is not preset)
#   - OpenSSL     (session-secret generation)
#
# Usage:
#   bash outreach/scripts/deploy-railway.sh
#
# Override any of these before running to skip prompts / reuse values:
#   PROJECT_NAME=coldmail
#   BACKEND_SERVICE=backend
#   FRONTEND_SERVICE=frontend
#   POSTGRES_SERVICE=Postgres      # Railway's default name for the Postgres plugin
#   FERNET_KEY=...                 # if unset, one is generated (SAVE IT)
#   SESSION_SECRET=...             # if unset, `openssl rand -hex 32`

set -euo pipefail

PROJECT_NAME="${PROJECT_NAME:-coldmail}"
BACKEND_SERVICE="${BACKEND_SERVICE:-backend}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-frontend}"
POSTGRES_SERVICE="${POSTGRES_SERVICE:-Postgres}"
#FERNET_KEY="QG4XrNg86yc0zgd4qDi9digQ5WDevw9dnGoumnFNbCE="
# ---------------------------------------------------------------------------
# 0. Locate outreach/
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTREACH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ ! -d "$OUTREACH_DIR/backend" || ! -d "$OUTREACH_DIR/frontend" ]]; then
  echo "error: expected backend/ and frontend/ next to $SCRIPT_DIR" >&2
  exit 1
fi
echo "==> outreach dir: $OUTREACH_DIR"

# ---------------------------------------------------------------------------
# 1. Preflight
# ---------------------------------------------------------------------------
command -v railway >/dev/null 2>&1 || {
  echo "error: railway CLI not installed. brew install railway  (or see docs.railway.app)" >&2
  exit 1
}
if ! railway whoami >/dev/null 2>&1; then
  echo "error: not logged in. Run: railway login" >&2
  exit 1
fi
command -v openssl >/dev/null 2>&1 || {
  echo "error: openssl not installed (needed to generate SESSION_SECRET)" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# 2. Generate one-time secrets
# ---------------------------------------------------------------------------
if [[ -z "${FERNET_KEY:-}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    FERNET_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || true)"
  fi
  if [[ -z "${FERNET_KEY:-}" ]]; then
    # Fallback: 32-byte random, url-safe base64 (Fernet key format).
    FERNET_KEY="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=' | cut -c1-43)="
  fi
  echo "==> Generated FERNET_KEY (SAVE THIS — losing it bricks encrypted credentials):"
  echo "    $FERNET_KEY"
fi
SESSION_SECRET="${SESSION_SECRET:-$(openssl rand -hex 32)}"

# ---------------------------------------------------------------------------
# 3. Link or create Railway project
# ---------------------------------------------------------------------------
cd "$OUTREACH_DIR"
if ! railway status >/dev/null 2>&1; then
  echo "==> No Railway project linked. Choose one:"
  echo "     1) Create a new project (\"$PROJECT_NAME\")"
  echo "     2) Link to an existing project"
  read -r -p "     Choice [1/2]: " choice
  case "${choice:-1}" in
    2) railway link ;;
    *) railway init --name "$PROJECT_NAME" ;;
  esac
fi
echo "==> Project status:"
railway status || true

# ---------------------------------------------------------------------------
# 4. Ensure Postgres plugin is present
#
# NOTE: every `railway` call in this section closes stdin (`< /dev/null`) so
# an unexpected interactive prompt from the CLI fails fast instead of hanging
# forever. See PR-INTERNAL comment: some `railway add` code paths still open
# a TUI when they detect a TTY.
# ---------------------------------------------------------------------------
if railway variables --service "$POSTGRES_SERVICE" </dev/null >/dev/null 2>&1; then
  echo "==> Postgres service already provisioned"
else
  echo "==> Adding Postgres plugin"
  if ! railway add --database postgres </dev/null; then
    if ! railway add -d postgres </dev/null; then
      echo "!! Failed to add Postgres. Create it manually in the Railway dashboard" >&2
      echo "   (New → Database → Add PostgreSQL) then re-run this script." >&2
      exit 1
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 5. Ensure backend + frontend services exist
# ---------------------------------------------------------------------------
ensure_service() {
  local name="$1"
  if railway variables --service "$name" </dev/null >/dev/null 2>&1; then
    echo "==> Service \"$name\" already exists"
    return 0
  fi
  echo "==> Creating service \"$name\""
  if ! railway add --service "$name" </dev/null; then
    echo "!! Failed to auto-create service \"$name\"." >&2
    echo "   Open the Railway dashboard, click New → Empty Service, name it" >&2
    echo "   \"$name\", then re-run this script." >&2
    exit 1
  fi
  # Verify the service actually shows up before we try to set variables on it.
  if ! railway variables --service "$name" </dev/null >/dev/null 2>&1; then
    echo "!! Service \"$name\" reported created but is not visible to the CLI." >&2
    echo "   Check the Railway dashboard and re-run." >&2
    exit 1
  fi
}
ensure_service "$BACKEND_SERVICE"
ensure_service "$FRONTEND_SERVICE"

# ---------------------------------------------------------------------------
# 5b. One-time manual step — set each service's Root Directory in the UI.
#
# Reason: outreach/ is a monorepo (backend/ + frontend/) so Railway needs to
# know which subdirectory to build. The Root Directory is a service-level
# setting that the Railway CLI does not expose (dashboard / GraphQL API only).
# Without this, Railpack analyses the outreach/ root and fails with:
#   "Railpack could not determine how to build the app"
#
# Skip the pause once the settings are in place by running with
# ROOT_DIR_CONFIGURED=1.
# ---------------------------------------------------------------------------
if [[ "${ROOT_DIR_CONFIGURED:-0}" != "1" ]]; then
  cat <<EOF

──────────────────────────────────────────────────────────────────────────
ONE-TIME MANUAL STEP — set Root Directory for each service.

  Open the Railway dashboard → project "$PROJECT_NAME", then for BOTH
  services below click the service → Settings → set "Root Directory":

    • $BACKEND_SERVICE  →  backend
    • $FRONTEND_SERVICE →  frontend

  (This tells Railway which subdirectory of the uploaded repo to build.
  The setting is persisted on the service — you only do this once.)

  Re-run this script with ROOT_DIR_CONFIGURED=1 to skip this pause
  next time, e.g. \`ROOT_DIR_CONFIGURED=1 bash $0\`.
──────────────────────────────────────────────────────────────────────────

EOF
  read -r -p "Press ENTER once both Root Directories are set to continue… " _ </dev/tty
fi

# ---------------------------------------------------------------------------
# 6. Write per-service railway.json (start command with migrations for backend)
# ---------------------------------------------------------------------------
echo "==> Writing backend/railway.json (start command runs alembic upgrade)"
cat > "$OUTREACH_DIR/backend/railway.json" <<'JSON'
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "startCommand": "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/api/v1/health",
    "healthcheckTimeout": 60,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
JSON

echo "==> Writing frontend/railway.json"
cat > "$OUTREACH_DIR/frontend/railway.json" <<'JSON'
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" }
}
JSON

# ---------------------------------------------------------------------------
# 7. Backend env vars
#    DATABASE_URL is built from the Postgres plugin's individual vars so it
#    carries the SQLAlchemy driver prefix (postgresql+psycopg://). Railway's
#    ${{ Service.VAR }} references are interpolated at deploy time.
# ---------------------------------------------------------------------------
echo "==> Setting backend variables"
railway variables --service "$BACKEND_SERVICE" </dev/null \
  --set "FERNET_KEY=$FERNET_KEY" \
  --set "SESSION_SECRET=$SESSION_SECRET" \
  --set "COOKIE_SECURE=true" \
  --set "DATABASE_URL=postgresql+psycopg://\${{${POSTGRES_SERVICE}.PGUSER}}:\${{${POSTGRES_SERVICE}.PGPASSWORD}}@\${{${POSTGRES_SERVICE}.PGHOST}}:\${{${POSTGRES_SERVICE}.PGPORT}}/\${{${POSTGRES_SERVICE}.PGDATABASE}}"

# ---------------------------------------------------------------------------
# 8. Deploy backend
#
# Pass the subdirectory as an explicit positional PATH so Railway CLI uploads
# only that directory, not the whole outreach/ repo. The service's Root
# Directory setting (step 5b) tells Railway's server-side builder to build
# from that upload's root.
# ---------------------------------------------------------------------------
echo "==> Deploying backend (upload path: $OUTREACH_DIR/backend)"
if ! railway up "$OUTREACH_DIR/backend" \
       --service "$BACKEND_SERVICE" --detach --ci </dev/null; then
  echo ""
  echo "!! Backend deploy failed. Common causes:"
  echo "   - Root Directory not set on \"$BACKEND_SERVICE\" (Railway dashboard →"
  echo "     the service → Settings → Root Directory → \"backend\")."
  echo "   - Railway CLI too old — upgrade with: brew upgrade railway"
  exit 1
fi

echo "==> Generating backend public domain"
(cd "$OUTREACH_DIR/backend" && \
   (railway domain --service "$BACKEND_SERVICE" --port 8000 </dev/null 2>/dev/null \
    || railway domain --service "$BACKEND_SERVICE" </dev/null 2>/dev/null || true))

# Extract the backend public URL (best-effort — Railway CLI output format varies).
BACKEND_HOST=""
if BACKEND_HOST=$(railway variables --service "$BACKEND_SERVICE" --kv </dev/null 2>/dev/null | \
                   awk -F= '/^RAILWAY_PUBLIC_DOMAIN=/{print $2}' | tr -d '"'); then :; fi
BACKEND_URL=""
[[ -n "$BACKEND_HOST" ]] && BACKEND_URL="https://$BACKEND_HOST"

# ---------------------------------------------------------------------------
# 9. Frontend env vars
#    NEXT_PUBLIC_API_URL is baked into the frontend at build time, so if we
#    don't yet have the backend URL, tell the user to run this script again
#    (idempotent) after the backend deploy completes.
# ---------------------------------------------------------------------------
if [[ -n "$BACKEND_URL" ]]; then
  echo "==> Backend URL detected: $BACKEND_URL"
  railway variables --service "$FRONTEND_SERVICE" </dev/null \
    --set "NEXT_PUBLIC_API_URL=$BACKEND_URL" \
    --set "INTERNAL_API_URL=$BACKEND_URL"
else
  echo "!! Could not auto-detect backend URL. Set NEXT_PUBLIC_API_URL + INTERNAL_API_URL"
  echo "   on the frontend service in the Railway dashboard, then re-run this script."
fi

# ---------------------------------------------------------------------------
# 10. Deploy frontend
# ---------------------------------------------------------------------------
echo "==> Deploying frontend (upload path: $OUTREACH_DIR/frontend)"
if ! railway up "$OUTREACH_DIR/frontend" \
       --service "$FRONTEND_SERVICE" --detach --ci </dev/null; then
  echo ""
  echo "!! Frontend deploy failed. Common causes:"
  echo "   - Root Directory not set on \"$FRONTEND_SERVICE\" (Railway dashboard →"
  echo "     the service → Settings → Root Directory → \"frontend\")."
  echo "   - Railway CLI too old — upgrade with: brew upgrade railway"
  exit 1
fi

echo "==> Generating frontend public domain"
(cd "$OUTREACH_DIR/frontend" && \
   (railway domain --service "$FRONTEND_SERVICE" --port 3000 </dev/null 2>/dev/null \
    || railway domain --service "$FRONTEND_SERVICE" </dev/null 2>/dev/null || true))

FRONTEND_HOST=""
if FRONTEND_HOST=$(railway variables --service "$FRONTEND_SERVICE" --kv </dev/null 2>/dev/null | \
                    awk -F= '/^RAILWAY_PUBLIC_DOMAIN=/{print $2}' | tr -d '"'); then :; fi
FRONTEND_URL=""
[[ -n "$FRONTEND_HOST" ]] && FRONTEND_URL="https://$FRONTEND_HOST"

# ---------------------------------------------------------------------------
# 11. Update backend CORS_ORIGINS to allow the frontend domain, then redeploy
# ---------------------------------------------------------------------------
if [[ -n "$FRONTEND_URL" ]]; then
  echo "==> Updating backend CORS_ORIGINS to include $FRONTEND_URL"
  railway variables --service "$BACKEND_SERVICE" </dev/null \
    --set "CORS_ORIGINS=[\"$FRONTEND_URL\"]"
  echo "==> Redeploying backend to pick up new CORS_ORIGINS"
  railway redeploy --service "$BACKEND_SERVICE" --yes </dev/null 2>/dev/null \
    || railway up "$OUTREACH_DIR/backend" --service "$BACKEND_SERVICE" --detach --ci </dev/null
else
  echo "!! Could not auto-detect frontend URL. Manually set CORS_ORIGINS on"
  echo "   the backend to include the frontend URL, then redeploy the backend."
fi

# ---------------------------------------------------------------------------
# 12. Summary
# ---------------------------------------------------------------------------
cat <<EOF

===========================================
Deploy submitted. Track progress with: railway logs --service $BACKEND_SERVICE

  Backend:  ${BACKEND_URL:-<check Railway dashboard>}
  Frontend: ${FRONTEND_URL:-<check Railway dashboard>}
  Postgres: $POSTGRES_SERVICE

FERNET_KEY (save this in a password manager — NOT recoverable):
  $FERNET_KEY

Next steps:
  1. Visit the frontend URL → you'll be redirected to /bootstrap to set the master password.
  2. Log in, open Settings, fill in Hunter / OpenAI / SMTP / IMAP / sender identity.
  3. Verify health: curl -sf ${BACKEND_URL:-<backend-url>}/api/v1/health

Re-run this script any time — it's idempotent for env vars, and \`railway up\`
just triggers a new deploy of the current source.
EOF
