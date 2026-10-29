#!/usr/bin/env bash
# Code sync for `./start.sh upgrade`, sourced by start.sh.
# upgrade 的程式碼同步：由 start.sh 引用。
#
# The production checkout is a bind mount that sits on a detached HEAD at origin/main
# (see AGENTS.md), where `git pull` fails with "You are not currently on a branch".
# On a branch we fast-forward as before; on a detached HEAD we move to origin/main only
# when the current commit is already part of origin/main's history, so a commit that
# exists only on this box is never dropped. Nothing is merged, reset or stashed.
# 正式環境是 detached HEAD，`git pull` 在那裡一定失敗。分支上照舊快轉；detached 時
# 只在目前 commit 已在 origin/main 歷史內才前進，不會丟掉只存在本機的 commit。

function advisor_sync_code {
    if ! git fetch --quiet origin; then
        echo "❌ git fetch origin failed — not touching the checkout."
        return 1
    fi

    if git symbolic-ref -q HEAD >/dev/null; then
        if ! git pull --ff-only; then
            echo "⚠️  git pull --ff-only failed (local changes or diverged history). Please resolve manually or stash."
            return 1
        fi
        return 0
    fi

    # --is-ancestor: 0 = yes, 1 = no, anything else = git itself failed (e.g. no origin/main ref).
    local rc=0
    git merge-base --is-ancestor HEAD origin/main || rc=$?
    if [ "$rc" -eq 1 ]; then
        echo "❌ Detached HEAD $(git rev-parse --short HEAD) is not part of origin/main's history — refusing to move."
        echo "   Compare with: git log --oneline origin/main..HEAD"
        return 1
    elif [ "$rc" -ne 0 ]; then
        echo "❌ Could not compare HEAD with origin/main (git exit $rc) — is there a refs/remotes/origin/main? HEAD is unchanged."
        return 1
    fi
    if ! git checkout --quiet --detach origin/main; then
        echo "❌ Could not move to origin/main (local edits in the way). Resolve manually; HEAD is unchanged."
        return 1
    fi
    echo "Moved detached HEAD to origin/main ($(git rev-parse --short HEAD))."
}
