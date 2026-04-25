#!/bin/bash
# Security audit script for third-party tools/plugins
# Based on .agent/skills/audit-plugin/SKILL.md

TARGET=$1

if [ -z "$TARGET" ]; then
    echo "Usage: $0 <local_path_or_repo_url>"
    exit 1
fi

# 1. Prepare target
if [[ "$TARGET" == https://* ]]; then
    AUDIT_DIR="/tmp/_audit_target_$(date +%s)"
    echo "Cloning $TARGET to $AUDIT_DIR..."
    git clone --depth 1 "$TARGET" "$AUDIT_DIR" || exit 1
    TARGET_PATH="$AUDIT_DIR"
else
    TARGET_PATH="$TARGET"
fi

echo "=== Starting Security Audit: $TARGET_PATH ==="

# 2a. Telemetry
echo "--- 2a. Telemetry / Analytics ---"
grep -r "telemetry\|analytics\|track\|phone.home\|beacon\|segment\|mixpanel\|amplitude" \
  "$TARGET_PATH" --include="*.ts" --include="*.js" --include="*.sh" --include="*.py" \
  -l 2>/dev/null

# 2b. Endpoints / Keys
echo "--- 2b. External Endpoints & API Keys ---"
grep -r "https://.*supabase\|https://.*firebase\|https://.*segment\|https://.*sentry" \
  "$TARGET_PATH" -h 2>/dev/null | sort -u | head -20
grep -r "eyJ[a-zA-Z0-9_-]\{20,\}\|sk-[a-zA-Z0-9]\{20,\}\|pk_\|sb_publishable" \
  "$TARGET_PATH" -h --include="*.ts" --include="*.sh" --include="*.json" 2>/dev/null | head -10

# 2c. Outbound
echo "--- 2c. Outbound Network Calls ---"
grep -r "fetch(\|axios\.\|curl \|wget \|http\.request\|urllib\.request" \
  "$TARGET_PATH" --include="*.ts" --include="*.js" --include="*.sh" --include="*.py" \
  -l 2>/dev/null

# 2d. Hidden Dirs
echo "--- 2d. Hidden Directory Access ---"
grep -r '~\/\.[a-zA-Z]\|HOME\/\.' \
  "$TARGET_PATH" --include="*.sh" --include="*.ts" -h 2>/dev/null | \
  grep -v "node_modules\|#" | sort -u | head -20

# 2e. Gate Logic
echo "--- 2e. Telemetry Gate Logic ---"
if [ -f "$TARGET_PATH/scripts/resolvers/preamble.ts" ]; then
    grep -n "off\|telemetry\|_TEL" "$TARGET_PATH/scripts/resolvers/preamble.ts" 2>/dev/null | head -30
else
    echo "No standard preamble found."
fi

echo "=== Audit Complete ==="
