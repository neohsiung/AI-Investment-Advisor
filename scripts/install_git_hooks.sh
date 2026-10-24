#!/usr/bin/env bash
# Install versioned git hooks from .githooks/ into the shared hooks dir (covers every worktree).
# 把 .githooks/ 的 hook 複製到共用的 hooks 目錄（所有 worktree 共用）。
#
# Copies instead of setting core.hooksPath: hooksPath would bypass .git/hooks/pre-commit, which the
# pre-commit framework owns (detect-secrets + gitleaks). Copies instead of symlinking: the hermes lane runner
# rewrites .git/hooks/pre-push on each claim, and writing through a symlink would edit the tracked file.
# 用複製而不是 core.hooksPath（會讓 pre-commit framework 的掃描失效），也不用 symlink（hermes runner 重寫時會改到版控檔）。
#
#   scripts/install_git_hooks.sh          # install; refuses to overwrite a different existing hook
#   scripts/install_git_hooks.sh --force  # overwrite (the old one is kept as <hook>.prev)
# No `set -e` (dev-standard §6): every failure is an explicit branch with a message.
repo=$(git rev-parse --show-toplevel) || { echo "not in a git repo"; exit 1; }
hooks="$(git rev-parse --git-common-dir)/hooks"
force=0; [ "${1:-}" = "--force" ] && force=1
rc=0
for src in "$repo"/.githooks/*; do
  name=$(basename "$src"); dst="$hooks/$name"
  if [ -f "$dst" ] && cmp -s "$src" "$dst"; then echo "$name: already current"; continue; fi
  if [ -f "$dst" ] && [ "$force" -ne 1 ]; then
    echo "$name: $dst differs from .githooks/$name; diff it, then rerun with --force"; rc=1; continue
  fi
  if [ -f "$dst" ]; then cp "$dst" "$dst.prev"; fi
  if cp "$src" "$dst" && chmod +x "$dst"; then echo "$name: installed -> $dst"; else echo "$name: copy failed"; rc=1; fi
done
exit "$rc"
