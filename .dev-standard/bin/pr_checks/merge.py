# 由 dev-standard v0.11.0 產生，請勿手改；要改請改 dev-standard 的 components/pr-checks，再跑 sync.py update
"""合併決定（純函式）與稽核表。決定看 effective 風險級（宣告與路徑取高），不信任宣告。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pr_checks import checks, risk


BOOTSTRAP_WARN = "bootstrap：base 還沒有 risk.json，暫用本 PR 版本；本 PR 一律要人合併"


@dataclass
class Decision:
    action: str  # merge | refuse | ci-only
    reason: str = ""


def needs_human(pr):
    """這個 PR 一定要人合併的理由；不需要就回 None。順序固定：bootstrap、改到檢查工具本身、R3。
    本機合併（decide）與 GitHub 端的 r3-gate 共用這一份判斷。"""
    if pr.bootstrap:
        return "要人合併：" + BOOTSTRAP_WARN
    changed = risk.tool_changed(pr.files, pr.cfg)
    if changed:
        return ("要人合併：PR 改了檢查工具本身（" + "、".join(changed[:5]) + ("…" if len(changed) > 5 else "")
                + "），不能用 PR 自己的程式替它放行")
    if checks.effective(pr) == "R3":
        src = "宣告" if checks.declared(pr) == "R3" else "依路徑"
        return f"R3：要人合併（{src}判定為 R3）"
    return None


def decide(results, pr) -> Decision:
    """順序固定：熔斷開關、要人合併（needs_human）、base 非預設分支、draft、不可合併、任一項不過。"""
    if pr.automerge_off:
        return Decision("refuse", ".automerge-off 存在，停止自動合併")
    why = needs_human(pr)
    if why:
        return Decision("refuse", why)
    if not pr.base or pr.base != pr.default_branch:
        return Decision("refuse", f"base 分支 {pr.base or '不明'} 不是預設分支 {pr.default_branch or '不明'}：只自動合併到預設分支")
    if pr.draft:
        return Decision("refuse", "draft PR")
    if not pr.mergeable:
        return Decision("refuse", "GitHub 回報不可合併（衝突或狀態未定）")
    bad = [r for r in results if not r.ok]
    if bad:
        return Decision("refuse", "未通過：" + "、".join(r.name for r in bad))
    return Decision("merge")


def merge_command(number, sha):
    """永遠 merge commit，不 squash、不 --auto（私有免費 repo 沒有分支保護，--auto 等於立刻合）。"""
    return ["gh", "pr", "merge", str(number), "--merge", "--match-head-commit", sha, "--delete-branch"]


def retro_note(pr) -> dict:
    """受信任作者的 `RETRO:` 留言，每行 `欄位：值`。只讀文字。"""
    note = {}
    for author, text in pr.comments:
        if author in pr.trusted and text.startswith("RETRO:"):
            for line in text.splitlines()[1:]:
                m = re.match(r"(卡在哪步|該改什麼|提案|數字)：(.+)", line.strip())
                if m:
                    note[m.group(1)] = m.group(2)
    return note


def retro_comment(pr, failed_names, note):
    """合併後留言五行，固定順序。「卡在哪步」等由開 PR 的 session 用 `RETRO:` 留言補，沒有就寫無。"""
    stuck = "、".join(failed_names) if failed_names else "無"
    note = note or {}
    return "\n".join([
        f"發生什麼：PR #{pr.number}「{pr.title}」七項檢查全過，腳本合併（head {pr.head_sha[:8]}，風險級 {checks.effective(pr)}）",
        f"卡在哪步：{note.get('卡在哪步', stuck)}",
        f"該改什麼：{note.get('該改什麼', '無')}",
        f"提案：{note.get('提案', '無')}",
        f"數字：{note.get('數字', '無')}",
    ])


def render(results, decision):
    lines = ["| 檢查 | 結果 | 說明 |", "|---|---|---|"]
    lines += [f"| {r.name} | {'過' if r.ok else '不過'} | {r.detail} |" for r in results]
    lines.append(f"\n決定：{decision.action}" + (f"（{decision.reason}）" if decision.reason else ""))
    return "\n".join(lines)
