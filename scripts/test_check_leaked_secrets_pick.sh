#!/usr/bin/env bash
# check_leaked_secrets.sh 的 pick() 自測：假 .env，只用虛構的值，不碰任何歷史真值。
# 用法：bash scripts/test_check_leaked_secrets_pick.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
LEAKED_SECRETS_LIB_ONLY=1 . "$HERE/check_leaked_secrets.sh"

fail=0
check() { # 名稱 內容 期望值
  printf '%b' "$2" > "$TMP/env"
  got="$(pick FAKE_KEY < "$TMP/env")"
  if [ "$got" = "$3" ]; then echo "ok: $1"; else echo "FAIL: $1"; fail=1; fi
}
check "plain"                "FAKE_KEY=fake-value-1\n"                       "fake-value-1"
check "export"               "export FAKE_KEY=fake-value-2\n"                "fake-value-2"
check "double quotes"        "FAKE_KEY=\"fake-value-3\"\n"                   "fake-value-3"
check "single quotes"        "FAKE_KEY='fake-value-4'\n"                     "fake-value-4"
check "trailing comment"     "FAKE_KEY=fake-value-5   # note\n"              "fake-value-5"
check "quoted + comment"     "export FAKE_KEY=\"fake-value-6\" # note\n"     "fake-value-6"
check "spaces around ="      "FAKE_KEY = fake-value-7\n"                     "fake-value-7"
check "CRLF"                 "FAKE_KEY=fake-value-8\r\n"                     "fake-value-8"
check "hash inside quotes"   "FAKE_KEY=\"fake#value-9\"\n"                   "fake#value-9"
check "missing key"          "OTHER=x\n"                                     ""
[ "$fail" -eq 0 ] && echo "ALL OK" || echo "SOME FAILED"
exit $fail
