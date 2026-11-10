#!/usr/bin/env bash
# check_leaked_secrets.sh — 比對「git 公開歷史裡的舊金鑰」與「目前正在用的金鑰」。
#
# 用途：DD-2026-1026-leaked-secrets-rotation 的第一步。判斷歷史上外洩的值
#       今天還有沒有在用；沒在用就不必換，在用才換。
# 不會印出任何值：每一組只印一行「名稱: 相同 | 不同 | 不存在」。
#       不 echo 值、不寫暫存檔、關閉 xtrace；值只放在 shell 變數裡，結束即消失。
# 在哪裡跑：主 checkout（有 .env 與正式容器），由創辦人執行：
#       bash scripts/check_leaked_secrets.sh
# 唯讀：只做 git show、讀 .env、讀容器的環境變數；不改任何東西。
# 歷史值在執行時從 git 歷史讀，本檔不含任何金鑰。

set +x
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
DB_CONTAINER="${DB_CONTAINER:-advisor_prod_db}"

# 從 stdin 的 KEY=VALUE 文字取出指定變數的值，只輸出值本身。
# 處理：行首 export、等號前後空白、單雙引號包住的值、未加引號時行尾 " # 註解"、CR。
pick() {
  sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$1[[:space:]]*=//p" | head -1 | tr -d '\r' | awk '{
    s = $0; sub(/^[ \t]+/, "", s); q = substr(s, 1, 1)
    if (q == "\"" || q == "\047") { s = substr(s, 2); i = index(s, q); if (i > 0) s = substr(s, 1, i - 1) }
    else { sub(/[ \t]+#.*$/, "", s); sub(/[ \t]+$/, "", s) }
    print s }'
}

# 自測用：LEAKED_SECRETS_LIB_ONLY=1 source 本檔只載入函式，不執行比對
if [ "${LEAKED_SECRETS_LIB_ONLY:-0}" = "1" ]; then return 0 2>/dev/null || exit 0; fi

# --- 歷史值（來自公開歷史） ---
hist_prod_db_pass="$(git -C "$ROOT" show 96d32f00:config/production.env 2>/dev/null | pick DB_PASS)"
hist_bak_db_pass="$(git -C "$ROOT" show 3a7be7f0:.env.bak-20260711 2>/dev/null | pick DB_PASS)"
hist_crypto_key="$(git -C "$ROOT" show 96d32f00:src/utils/crypto_utils.py 2>/dev/null \
  | sed -n 's/.*_KEY *= *b\{0,1\}["'"'"']\([A-Za-z0-9_=-]\{40,\}\)["'"'"'].*/\1/p' | head -1)"

# 歷史值讀不到就停下來：讀不到會被誤判成「不存在」，讓人以為不用換金鑰
missing=0
for pair in "production.env DB_PASS:$hist_prod_db_pass" "env.bak DB_PASS:$hist_bak_db_pass" "crypto_utils _KEY:$hist_crypto_key"; do  # pragma: allowlist secret
  if [ -z "${pair#*:}" ]; then echo "錯誤: 讀不到歷史值 ${pair%%:*}（git 歷史不完整？淺層 clone 請先 git fetch --unshallow）" >&2; missing=1; fi
done
[ "$missing" -eq 0 ] || exit 2

# --- 目前值 ---
cur_db_pass=""
cur_app_key=""
cur_llm_key=""
if [ -r "$ENV_FILE" ]; then
  cur_db_pass="$(pick DB_PASS < "$ENV_FILE")"
  cur_app_key="$(pick APP_SECRET_KEY < "$ENV_FILE")"
  cur_llm_key="$(pick LLM_CREDENTIAL_KEY < "$ENV_FILE")"
fi
cont_db_pass=""
if command -v docker >/dev/null 2>&1; then
  cont_db_pass="$(docker exec "$DB_CONTAINER" sh -c 'printf %s "$POSTGRES_PASSWORD"' 2>/dev/null || true)"
fi

# 比對：任一邊空 → 不存在；相等 → 相同；否則 不同
cmp_one() {
  if [ -z "$2" ] || [ -z "$3" ]; then
    echo "$1: 不存在"
  elif [ "$2" = "$3" ]; then
    echo "$1: 相同"
  else
    echo "$1: 不同"
  fi
}

echo "== 歷史 DB 密碼 vs 目前 =="
cmp_one "production.env(96d32f00) DB_PASS vs .env DB_PASS" "$hist_prod_db_pass" "$cur_db_pass"
cmp_one "production.env(96d32f00) DB_PASS vs 容器 POSTGRES_PASSWORD" "$hist_prod_db_pass" "$cont_db_pass"
cmp_one ".env.bak-20260711(3a7be7f0) DB_PASS vs .env DB_PASS" "$hist_bak_db_pass" "$cur_db_pass"
cmp_one ".env.bak-20260711(3a7be7f0) DB_PASS vs 容器 POSTGRES_PASSWORD" "$hist_bak_db_pass" "$cont_db_pass"
echo "== 歷史加密金鑰 vs 目前 =="
cmp_one "crypto_utils(96d32f00) _KEY vs .env APP_SECRET_KEY" "$hist_crypto_key" "$cur_app_key"
cmp_one "crypto_utils(96d32f00) _KEY vs .env LLM_CREDENTIAL_KEY" "$hist_crypto_key" "$cur_llm_key"

# 解讀提示（不含值）
echo "-- 「相同」= 歷史外洩值仍在用，照 DD 的換金鑰步驟處理。「不同」= 現在的值不是歷史值，但不代表舊值已失效：仍要照 DD A.5 用舊密碼連線驗證一次，確認被拒絕。「不存在」= 讀不到（檢查 .env 路徑或容器名稱）。"
