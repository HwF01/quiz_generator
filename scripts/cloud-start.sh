#!/usr/bin/env bash
# Per-boot startup for the local dev stack (SQLite + in-process cache + mock LLM).
# Launches the FastAPI backend (:8000) and Next.js frontend (:3000) in the
# background, waits for readiness, then returns. Idempotent: skips a service
# that is already listening.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="/tmp/quizgen-logs"
mkdir -p "$LOG_DIR"

# A port is "up" if something accepts the connection, regardless of HTTP status
# (the backend root path returns 404, so -f would give a false negative).
port_up() { curl -s -o /dev/null "http://127.0.0.1:$1" 2>/dev/null; }

echo "== Starting backend (:8000) =="
if port_up 8000; then
  echo "backend already running"
else
  cd "$REPO_ROOT/backend"
  # setsid detaches into a new session so the server survives after this
  # start script returns and its process group is torn down.
  APP_ENV=local \
  REDIS_URL=memory:// \
  DATABASE_URL=sqlite+aiosqlite:///./quizgen.db \
  MOCK_LLM=true \
  SECRET_KEY=change-me-in-production \
  setsid ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 < /dev/null &
  echo "backend pid $!"
fi

echo "== Starting frontend (:3000) =="
if port_up 3000; then
  echo "frontend already running"
else
  cd "$REPO_ROOT/frontend"
  INTERNAL_API_URL=http://127.0.0.1:8000 \
  setsid npm run dev > "$LOG_DIR/frontend.log" 2>&1 < /dev/null &
  echo "frontend pid $!"
fi

echo "== Waiting for backend health =="
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null "http://127.0.0.1:8000/health"; then
    echo "backend healthy"; break
  fi
  sleep 1
done

echo "== Waiting for frontend =="
for _ in $(seq 1 60); do
  if port_up 3000; then echo "frontend up"; break; fi
  sleep 1
done

echo "== Startup complete (logs in $LOG_DIR) =="
