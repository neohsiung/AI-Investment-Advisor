#!/usr/bin/env python3
# 由 dev-standard v0.6.2 產生，請勿手改；要改請改 dev-standard 的 components/pr-checks，再跑 sync.py update
"""本機入口：取 PR 資料、跑七項檢查、印每項結果、依風險級決定能不能合併。不需要 GitHub Actions。

  python3 .dev-standard/bin/pr_checks/run.py <PR>             跑全部檢查，印表與決定（不合併）
  python3 .dev-standard/bin/pr_checks/run.py <PR> --merge     全過且規則允許才合併（gh pr merge --merge --match-head-commit …）
  python3 .dev-standard/bin/pr_checks/run.py <PR> --ci        只跑靜態項（給 workflow 用），不合併
  python3 .dev-standard/bin/pr_checks/run.py --body-file B --files-file F [--risk-file R]
                                                              離線靜態項：描述與改動檔清單都是檔案（測試與 hermes 式 CI 用）

退出碼：0 全過（--merge 時代表已合併）；1 有檢查不過，或 --merge 被規則拒絕（R3、.automerge-off…）；
2 工具失敗（gh、risk.json、classifier 壞了——不會被當成通過）；3 已合併但合併後留言失敗。
風險級設定讀 base 分支的 .dev-standard/risk.json（離線模式讀 --risk-file，預設 ./.dev-standard/risk.json）。
請在 repo 根目錄執行；根目錄有 .automerge-off 也會拒絕合併。
非 --ci 模式要求本機 checkout 的 HEAD 就是 origin 上 base 分支的最新 commit（classifier 在這裡跑，不能是 PR 的版本）；
PR 改到檢查工具本身（.dev-standard/bin/pr_checks/**、risk.json、classifier 腳本）一律當 R3：要人合併，--ci 也一樣。
bootstrap：base 還沒有 risk.json、而本 PR 加入它時，暫用本 PR 版本評估（印警告），一律要人合併、--ci 不算工具失敗；PR 沒加它則照舊是工具失敗。
PR 的 base 不是 repo 預設分支、或改動檔清單被截斷（>=3000 或筆數對不上 changedFiles）也不自動合併。
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# 不在 sys.path 之後寫頂層 from-import：免得各 repo 的 ruff（E402／RUF100）對 vendored 檔報錯
checks, gh, merge, risk = (importlib.import_module(f"pr_checks.{m}") for m in ("checks", "gh", "merge", "risk"))


def repo_root() -> Path:
    d = Path.cwd().resolve()
    for c in [d, *d.parents]:
        if (c / ".git").exists():
            return c
    return d


def offline_pr(body_file, files_file, risk_file) -> checks.PR:
    body = Path(body_file).read_text(encoding="utf-8")
    files = [l.strip() for l in Path(files_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    cfg = risk.load_config(json.loads(Path(risk_file).read_text(encoding="utf-8")))
    if risk.tool_changed(files, cfg):
        level = "R3"                                       # 改到檢查工具本身：不跑可能被改過的 classifier
    elif cfg["classifier"]:
        level = gh.run_classifier(cfg["classifier"], files, cwd=repo_root())
    else:
        level = None
    return checks.PR(number=0, head_sha="", title="", body=body, files=files, draft=False, mergeable=True,
                     cfg=cfg, classifier_level=level, trusted=tuple(cfg["trusted_authors"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pr", type=int, nargs="?")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--ci", action="store_true")
    ap.add_argument("--repo")
    ap.add_argument("--body-file")
    ap.add_argument("--files-file")
    ap.add_argument("--risk-file", default=".dev-standard/risk.json")
    a = ap.parse_args(argv)
    offline = bool(a.body_file or a.files_file)
    if offline and not (a.body_file and a.files_file):
        ap.error("離線模式要同時給 --body-file 與 --files-file")
    if offline and (a.merge or a.pr is not None):
        ap.error("離線模式不取 PR、不合併")
    if not offline and a.pr is None:
        ap.error("要給 PR 編號，或離線的 --body-file／--files-file")
    if a.merge and a.ci:
        ap.error("--ci 不合併")
    static = a.ci or offline
    try:
        if offline:
            pr = offline_pr(a.body_file, a.files_file, a.risk_file)
        else:
            local_off = (repo_root() / ".automerge-off").exists()
            pr = gh.fetch(a.pr, a.repo, ci_mode=static, local_automerge_off=local_off, cwd=str(repo_root()))
        results = checks.run_all(pr, ci_mode=static)
    except Exception as e:  # noqa: BLE001 — 取資料／讀設定／classifier 失敗＝工具失敗，回 2，絕不當成通過
        print(f"工具失敗：{e}", file=sys.stderr)
        return 2
    if pr.bootstrap:
        print("!!! " + merge.BOOTSTRAP_WARN + " !!!", file=sys.stderr)
    if static:
        print(merge.render(results, merge.Decision("ci-only")))
        return 0 if all(r.ok for r in results) else 1
    d = merge.decide(results, pr)
    print(merge.render(results, d))
    if d.action != "merge":
        return 1 if a.merge or any(not r.ok for r in results) else 0
    cmd = merge.merge_command(pr.number, pr.head_sha)
    if not a.merge:
        print("可合併。要合併請加 --merge；會執行：" + " ".join(cmd))
        return 0
    try:
        gh.merge(pr.number, pr.head_sha, a.repo)
    except gh.GhError as e:
        print(f"合併失敗：{e}", file=sys.stderr)
        return 2
    print("已合併：" + " ".join(cmd))
    try:
        gh.comment(pr.number, "合併後 retro\n\n" + merge.retro_comment(pr, [], merge.retro_note(pr)), a.repo)
    except gh.GhError as e:
        print(f"已合併，但合併後留言失敗：{e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
