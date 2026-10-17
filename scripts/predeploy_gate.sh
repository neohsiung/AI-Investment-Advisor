#!/usr/bin/env bash
# Pre-deploy gate: nothing reaches the production containers unless these checks pass.
# 部署前閘門：以下檢查全數通過，程式碼才可上線到正式容器。
#
# Why: ./src and ./config are bind-mounted into the production containers, and start.sh used to build and
# restart without running any test. A malformed settings_schema.yaml therefore went live and evicted 7 of
# 8 active tickers (2026-10-16).
#
# Checks: (1) tracked files clean, (2) HEAD is on main/tag (or ALLOW_BRANCH_DEPLOY=1), (3) every config/*.yaml
# parses, (4) alembic has a single head, (5) config + invariants + deploy tests pass.
# Override (audited): FORCE_DEPLOY=1 skips ALL checks; ALLOW_BRANCH_DEPLOY=1 skips only check (2).
set -u
cd "$(dirname "$0")/.."

PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
AUDIT="backups/deploy_audit.log"; mkdir -p backups
SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
audit() { echo "$(date -u +%FT%TZ) sha=$SHA branch=$BRANCH user=$(id -un) $*" >> "$AUDIT"; }
fail() { echo "❌ predeploy gate: $*" >&2; audit "result=FAIL reason=\"$*\""; exit 1; }

if [ "${FORCE_DEPLOY:-0}" = "1" ]; then
    echo "⚠️  FORCE_DEPLOY=1 — predeploy gate SKIPPED (audited)."
    audit "result=FORCED"
    exit 0
fi

echo "=== predeploy gate ($BRANCH @ $SHA) ==="

# (1) tracked files must be clean: what runs in production must be what is committed.
if ! git diff --quiet || ! git diff --cached --quiet; then
    fail "tracked files have uncommitted changes — commit or stash first"
fi

# (2) deploy only from main or an exact tag.
if [ "${ALLOW_BRANCH_DEPLOY:-0}" != "1" ]; then
    git fetch -q origin main 2>/dev/null || true
    if git merge-base --is-ancestor HEAD origin/main 2>/dev/null || git describe --exact-match --tags HEAD >/dev/null 2>&1; then
        :
    else
        fail "HEAD ($BRANCH) is not contained in origin/main and is not a tag (set ALLOW_BRANCH_DEPLOY=1 to deploy a branch knowingly)"
    fi
else
    echo "⚠️  ALLOW_BRANCH_DEPLOY=1 — deploying branch '$BRANCH' (audited)."
fi

# (3) all config YAML must parse (a malformed label once crashed the quality gate in production).
"$PY" - <<'PYEOF' || fail "a config/*.yaml file does not parse"
import glob, sys, yaml
bad = []
for f in sorted(glob.glob("config/**/*.yaml", recursive=True)):
    try:
        yaml.safe_load(open(f, encoding="utf-8"))
    except Exception as e:
        bad.append(f"{f}: {e}")
if bad:
    print("\n".join(bad)); sys.exit(1)
print("config YAML OK")
PYEOF

# (4) a single alembic head (no divergent migration branches).
if "$PY" -c "import alembic" >/dev/null 2>&1; then
    HEADS="$("$PY" -m alembic heads 2>/dev/null | grep -c '(head)')"
    [ "$HEADS" = "1" ] || fail "alembic has $HEADS heads (expected 1)"
    echo "alembic single head OK"
else
    echo "⚠️  alembic not importable here — head check skipped"
fi

# (5) config + invariants + deploy tests.
"$PY" -m pytest tests/unit/config tests/invariants tests/unit/deploy -q -p no:cacheprovider \
    || fail "config/invariants/deploy tests failed"

audit "result=PASS"
echo "✅ predeploy gate passed"
