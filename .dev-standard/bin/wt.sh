#!/bin/bash
# 由 dev-standard v0.6.1 產生，請勿手改；要改請改 dev-standard 的 components/wt，再跑 sync.py update
# wt.sh — 一個任務一個 worktree（來由：hermes scripts/dev/wt.sh，DD-2026-1008-agent-workflow）
#
#   wt.sh new <branch> [base]    從 base（預設 origin/main）開 <WT_ROOT>/<branch>
#   wt.sh list
#   wt.sh rm <branch> [--force]  移除 worktree 與本地分支（未合進 origin/main 的要 --force）
#
# 為什麼：在主要 checkout 上切分支，會讓正在跑的東西（cron、dev server、另一個 session）踩到別的版本，
# 兩個 session 的改動也會混在同一棵樹（hermes 2026-10-08 實際發生）。
#
# 設定（環境變數，或 repo 的 .dev-standard/wt.env）：
#   DEV_WT_REPO   主要 checkout（預設：目前 repo 的主要 worktree）
#   DEV_WT_ROOT   worktree 放哪（預設：<repo 所在目錄>/<repo 名>-wt）
#   new 之後若 repo 有可執行的 .dev-standard/wt-post-new.sh，會以 <worktree 路徑> <主要 checkout> 呼叫它
#   （hermes 用它註冊產生檔的 merge driver）。
set -euo pipefail

top=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's#/\.git$##') || true
REPO="${DEV_WT_REPO:-$top}"
[ -n "$REPO" ] || { echo "❌ 不在 git repo 裡，也沒設 DEV_WT_REPO" >&2; exit 2; }
if [ -f "$REPO/.dev-standard/wt.env" ]; then
  # shellcheck disable=SC1091
  . "$REPO/.dev-standard/wt.env"
fi
WT_ROOT="${DEV_WT_ROOT:-$(dirname "$REPO")/$(basename "$REPO")-wt}"

cmd="${1:-}"; shift || true
case "$cmd" in
  new)
    branch="${1:?branch 名稱，例：feat/xxx}"; base="${2:-origin/main}"
    dir="$WT_ROOT/${branch//\//-}"
    git -C "$REPO" fetch -q origin
    mkdir -p "$WT_ROOT"
    git -C "$REPO" worktree add -q -b "$branch" "$dir" "$base"
    hook="$REPO/.dev-standard/wt-post-new.sh"
    if [ -x "$hook" ]; then
      "$hook" "$dir" "$REPO" || echo "❌ wt-post-new.sh 失敗，照它的訊息手動補做" >&2
    fi
    echo "✅ $dir  （$branch ← $base）"
    echo "   在那裡開 session：cd $dir && claude"
    ;;
  list)
    git -C "$REPO" worktree list
    ;;
  rm)
    branch="${1:?branch 名稱}"; force="${2:-}"
    dir="$WT_ROOT/${branch//\//-}"
    git -C "$REPO" fetch -q origin
    if [ "$force" != "--force" ] && ! git -C "$REPO" merge-base --is-ancestor "$branch" origin/main 2>/dev/null; then
      echo "❌ $branch 還沒合進 origin/main —— 確定不要了加 --force" >&2; exit 1
    fi
    git -C "$REPO" worktree remove ${force:+--force} "$dir"
    git -C "$REPO" branch -D "$branch" >/dev/null && echo "✅ 已移除 $dir 與本地分支 $branch"
    ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
