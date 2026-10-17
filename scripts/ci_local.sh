#!/usr/bin/env bash
# ci_local.sh — run the cheap CI gates locally BEFORE pushing, so a PR does not fail on a step we could have run.
# 在推送前本機先跑 CI 中便宜的幾道關卡，避免 PR 才發現失敗。
#
# Mirrors .github/workflows/ci-cd.yml (lab job): Alembic upgrade+check on a THROWAWAY Postgres, Bandit, wiki links.
# The full pytest run is separate (it takes ~18 min): `PY=... $PY -m pytest tests/unit tests/invariants -q`.
# Never touches the production database: it starts its own container on an unused port and removes it on exit.
#
# Usage: scripts/ci_local.sh            (uses .venv/bin/python; override with PY=/path/to/python)
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
PORT="${CI_LOCAL_PG_PORT:-55433}"
NAME="ci_local_pg_$$"
fail=0

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== 1/3 Alembic upgrade + check (throwaway Postgres on :$PORT) =="
if ! command -v docker >/dev/null; then echo "SKIP: docker not available"; else
  docker run -d --name "$NAME" -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=portfolio \
    -p "$PORT:5432" pgvector/pgvector:pg16 >/dev/null || { echo "FAIL: could not start postgres"; exit 1; }
  for _ in $(seq 1 40); do docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
  sleep 3
  export DB_TYPE=postgres DB_HOST=localhost DB_PORT="$PORT" DB_USER=postgres DB_PASS=postgres DB_NAME=portfolio REDIS_HOST=localhost REDIS_PORT=6379
  ALEMBIC="$(dirname "$PY")/alembic"
  if "$ALEMBIC" upgrade head >/tmp/ci_local_alembic.log 2>&1 && "$ALEMBIC" check >>/tmp/ci_local_alembic.log 2>&1; then
    echo "OK"
  else
    echo "FAIL (see /tmp/ci_local_alembic.log)"; grep -E "ERROR|New upgrade operations" /tmp/ci_local_alembic.log | cut -c1-220 | head -5; fail=1
  fi
fi

echo "== 2/3 Bandit (medium+ severity) =="
if "$PY" -m bandit --version >/dev/null 2>&1; then
  "$PY" -m bandit -r src/ -ll -q >/tmp/ci_local_bandit.log 2>&1 && echo "OK" || { echo "FAIL (see /tmp/ci_local_bandit.log)"; tail -5 /tmp/ci_local_bandit.log; fail=1; }
else echo "SKIP: bandit not installed in $PY"; fi

echo "== 3/3 Wiki link integrity =="
"$PY" .agent/skills/wiki-maintainer/scripts/verify_wiki_links.py >/tmp/ci_local_wiki.log 2>&1 && echo "OK" || { echo "FAIL (see /tmp/ci_local_wiki.log)"; tail -5 /tmp/ci_local_wiki.log; fail=1; }

[ "$fail" -eq 0 ] && echo "ci_local: all gates passed" || echo "ci_local: FAILED"
exit "$fail"
