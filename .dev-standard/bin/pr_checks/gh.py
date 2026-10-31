# 由 dev-standard v0.6.1 產生，請勿手改；要改請改 dev-standard 的 components/pr-checks，再跑 sync.py update
"""外殼：用 gh 取 PR 資料、合併、留言。決策不在這裡。

整個套件只有這個檔起子行程，且只有三處：`_run`（gh）、`_git_head`（唯讀的 `git rev-parse HEAD`）與 `run_classifier`（risk.json 指定的 argv）。
`_run` 只放行固定形狀的子命令（唯讀的 pr view／pr list／api GET，與合併、留言各一種），其餘一律丟 GhError：
合併永遠是 `pr merge N --merge --match-head-commit <40 位 sha> --delete-branch`，沒有 --squash、沒有 --auto。
任何一次 gh 失敗都丟例外（run.py 轉成非 0），不會變成「通過」。
"""
from __future__ import annotations

import base64
import json
import re
import subprocess

from pr_checks import checks, risk

TIMEOUT = 60
FILES_API_CAP = 3000   # GitHub 的 PR files API 最多回 3000 筆，到這個數就無法確認拿到全部
CLASSIFIER_TIMEOUT = 120
LIST_LIMIT = 1000
SHA40 = re.compile(r"^[0-9a-f]{40}$")
# 每種放行的子命令：位置參數個數、允許的旗標（True＝帶值）、必備旗標
SHAPES = {
    ("pr", "view"): (1, {"--json": True, "--repo": True}, ()),
    ("pr", "list"): (0, {"--state": True, "--limit": True, "--json": True, "--repo": True}, ()),
    ("pr", "merge"): (1, {"--merge": False, "--match-head-commit": True, "--delete-branch": False, "--repo": True},
                      ("--merge", "--match-head-commit", "--delete-branch")),
    ("pr", "comment"): (1, {"--body": True, "--repo": True}, ("--body",)),
    ("api", None): (1, {"--paginate": False, "--jq": True}, ()),
}


class GhError(RuntimeError):
    pass


def _validate(args):
    a = list(args)
    key = (a[0], a[1]) if a[:1] == ["pr"] and len(a) > 1 else (a[0], None) if a[:1] == ["api"] else None
    if key not in SHAPES:
        raise GhError(f"不放行的 gh 子命令：{a[:2]}")
    npos, flags, required = SHAPES[key]
    rest = a[2:] if key[1] else a[1:]
    pos, seen, i = [], {}, 0
    while i < len(rest):
        t = rest[i]
        if t.startswith("-"):
            if t not in flags:
                raise GhError(f"gh {' '.join(a[:2])} 不放行旗標 {t!r}")
            if flags[t]:
                if i + 1 >= len(rest):
                    raise GhError(f"旗標 {t} 缺值")
                seen[t] = rest[i + 1]
                i += 2
            else:
                seen[t] = True
                i += 1
        else:
            pos.append(t)
            i += 1
    if len(pos) != npos:
        raise GhError(f"gh {' '.join(a[:2])} 的位置參數應有 {npos} 個，實際 {len(pos)}")
    for r in required:
        if r not in seen:
            raise GhError(f"gh {' '.join(a[:2])} 缺必備旗標 {r}")
    if key[0] == "pr" and key[1] != "list" and not pos[0].isdigit():
        raise GhError("PR 編號必須是數字")
    if key == ("pr", "merge") and not SHA40.match(str(seen["--match-head-commit"])):
        raise GhError("--match-head-commit 必須是完整 40 位小寫 sha")
    if key == ("api", None) and pos[0].startswith("-"):
        raise GhError("gh api 第一個參數必須是端點")


def _run(args, check=True):
    """唯一呼叫 gh 的地方。失敗（含逾時、找不到 gh）一律丟 GhError，不回傳假結果。"""
    _validate(args)
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GhError(f"gh 無法執行（{' '.join(args[:3])}…）：{e}")
    if check and r.returncode != 0:
        raise GhError(f"gh 失敗（{' '.join(args[:3])}…）：{r.stderr.strip()}")
    return r


def run_classifier(argv, files, cwd=None) -> str:
    """跑 risk.json 的 classifier（argv 清單，不經 shell）。改動檔一行一個走 stdin。
    輸出第一行要含恰好一個 R0–R3；其他一律當工具失敗，不當成「沒意見」。"""
    try:
        r = subprocess.run(list(argv), input="\n".join(files) + "\n", capture_output=True, text=True,
                           timeout=CLASSIFIER_TIMEOUT, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GhError(f"classifier 無法執行（{argv[0]}）：{e}")
    if r.returncode != 0:
        raise GhError(f"classifier 失敗（{argv[0]}，exit {r.returncode}）：{r.stderr.strip()[:300]}")
    first = (r.stdout.strip().splitlines() or [""])[0]
    found = set(re.findall(r"(?<![0-9A-Za-z])(R[0-3])(?![0-9A-Za-z])", first))
    if len(found) != 1:
        raise GhError(f"classifier 輸出看不懂（要含恰好一個 R0–R3）：{first!r}")
    return found.pop()


def _git_head(cwd) -> str:
    """本機 checkout 的 HEAD sha（唯讀）。classifier 在本機 checkout 裡跑，所以要知道跑的是哪一版的程式。"""
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=TIMEOUT, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GhError(f"git 無法執行：{e}")
    sha = r.stdout.strip()
    if r.returncode != 0 or not SHA40.match(sha):
        raise GhError(f"讀不到本機 HEAD：{r.stderr.strip()[:200]}")
    return sha


def require_base_checkout(base, repo=None, cwd=None) -> None:
    """本機 checkout 的 HEAD 必須等於 origin 上 base 分支的最新 commit，否則 classifier 等檢查工具跑的是舊版或 PR 的版本。"""
    tip = _run(["api", f"repos/{_slug(repo)}/branches/{base}", "--jq", ".commit.sha"]).stdout.strip()
    if not SHA40.match(tip):
        raise GhError(f"取不到 {base} 的最新 commit")
    head = _git_head(cwd)
    if head != tip:
        raise GhError(f"本機 checkout（{head[:8]}）不是 {base} 的最新（{tip[:8]}）：檢查工具要用 base 的版本跑。"
                      f"請先切到 {base} 並更新，再跑一次")


def default_branch(repo=None) -> str:
    out = _run(["api", f"repos/{_slug(repo)}", "--jq", ".default_branch"]).stdout.strip()
    if not out:
        raise GhError("取不到 repo 的預設分支")
    return out


def _slug(repo):
    return repo or "{owner}/{repo}"


def pr_files_counted(number, repo=None) -> tuple:
    """分頁取全部檔，改名的新舊路徑都算。回傳 (檔案清單, API 回的檔案筆數)；筆數一筆一個檔（改名算一個）。"""
    out = _run(["api", f"repos/{_slug(repo)}/pulls/{number}/files", "--paginate", "--jq",
                '.[] | [.filename, (.previous_filename // "")] | @tsv']).stdout
    files, n = [], 0
    for line in out.splitlines():
        n += 1
        for part in line.split("\t"):
            if part and part not in files:
                files.append(part)
    return files, n


def pr_files(number, repo=None, changed=None):
    """全部改動檔。changed 是 GitHub 回報的 changedFiles：筆數對不上，或到了 API 上限（會被截斷），就中止——
    少看到檔等於少算風險級。"""
    files, n = pr_files_counted(number, repo)
    if changed is None or not isinstance(changed, int):
        raise GhError(f"PR #{number} 取不到 changedFiles，無法確認改動檔清單完整")
    if changed >= FILES_API_CAP or n != changed:
        raise GhError(f"PR #{number} 的改動檔清單不完整（API 回 {n} 筆，PR 有 {changed} 個檔；上限 {FILES_API_CAP}）："
                      "太大的 PR 要人看，不自動評級")
    return files


def _not_found(r) -> bool:
    return "404" in r.stderr or "Not Found" in r.stderr


def automerge_off(base, repo=None) -> bool:
    """只有明確 404 才算沒有 .automerge-off；其他錯誤中止（停機開關不可 fail-open）。"""
    r = _run(["api", f"repos/{_slug(repo)}/contents/.automerge-off?ref={base}"], check=False)
    if r.returncode == 0:
        return True
    if _not_found(r):
        return False
    raise GhError(f"讀 .automerge-off 失敗：{r.stderr.strip()}")


class RiskMissing(GhError):
    """base 上沒有 risk.json（明確 404）。與其他讀取失敗分開：bootstrap 只在這種情況才可能放行。"""


def load_risk_config(base, repo=None) -> dict:
    """從 base 分支讀 .dev-standard/risk.json，不從 PR 的 checkout 讀：PR 不能在同一個改動裡拿掉 R3 樣式再去動 R3 檔。
    讀不到、不是合法 JSON、內容不合法都是工具失敗。"""
    r = _run(["api", f"repos/{_slug(repo)}/contents/.dev-standard/risk.json?ref={base}", "--jq", ".content"], check=False)
    if r.returncode != 0:
        if _not_found(r):
            raise RiskMissing(f"{base} 上沒有 .dev-standard/risk.json：先跑 sync.py update 建出來並合併")
        raise GhError(f"讀 risk.json 失敗：{r.stderr.strip()}")
    try:
        data = json.loads(base64.b64decode(r.stdout.strip().strip('"')).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise GhError(f"{base} 上的 risk.json 不是合法 JSON：{e}")
    return risk.load_config(data)


def repo_owner(repo=None) -> str:
    out = _run(["api", f"repos/{_slug(repo)}", "--jq", ".owner.login"]).stdout.strip()
    if not out:
        raise GhError("取不到 repo owner")
    return out


def fetch(number, repo=None, ci_mode=False, cfg=None, local_automerge_off=False, cwd=None) -> checks.PR:
    """cwd：base 分支 checkout 的根目錄（classifier 在這裡跑）。非 CI 模式會先確認這份 checkout 就是 base 的最新。"""
    fields = "number,title,body,headRefOid,baseRefName,isDraft,mergeable,state,changedFiles"
    if not ci_mode:
        fields += ",statusCheckRollup,comments"
    d = json.loads(_run(["pr", "view", str(number), "--json", fields] + (["--repo", repo] if repo else [])).stdout)
    if d["state"] != "OPEN":
        raise GhError(f"PR #{number} 不是 OPEN（{d['state']}）")
    base = d["baseRefName"]
    if not ci_mode:
        require_base_checkout(base, repo, cwd)
    files = pr_files(number, repo, d.get("changedFiles"))
    bootstrap = False
    if cfg is None:
        try:
            cfg = load_risk_config(base, repo)
        except RiskMissing:
            # 第一個加入 risk.json 的 PR：base 沒有、PR 自己加。暫用 PR 版本評估，但一律要人合併（tool_changed 會把它判成 R3）。
            # base 沒有且 PR 沒加＝維持工具失敗。
            if risk.RISK_FILE not in files:
                raise
            cfg = load_risk_config(d["headRefOid"], repo)
            bootstrap = True
    if risk.tool_changed(files, cfg):                     # PR 改了檢查工具：不跑 PR 版的 classifier，直接 R3、要人合併
        level = "R3"
    else:
        level = run_classifier(cfg["classifier"], files, cwd=cwd) if cfg["classifier"] else None
    dbranch = None
    others, ci, comments, off = {}, [], [], False
    trusted = tuple(cfg["trusted_authors"]) or (repo_owner(repo),)
    if not ci_mode:
        dbranch = default_branch(repo)
        lcmd = ["pr", "list", "--state", "open", "--limit", str(LIST_LIMIT), "--json", "number,changedFiles"] + (["--repo", repo] if repo else [])
        opens = json.loads(_run(lcmd).stdout)
        if len(opens) >= LIST_LIMIT:
            raise GhError(f"開著的 PR 達 {LIST_LIMIT} 筆上限，無法確認無衝突")
        for o in opens:
            if o["number"] != number:
                others[o["number"]] = pr_files(o["number"], repo, o.get("changedFiles"))
        ignore = set(cfg["ci_ignore"])
        ci = [((c.get("name") or c.get("context")), (c.get("conclusion") or c.get("state") or "PENDING"))
              for c in d.get("statusCheckRollup", []) if (c.get("name") or c.get("context")) not in ignore]
        comments = [((c.get("author") or {}).get("login", ""), c["body"]) for c in d.get("comments", [])]
        off = local_automerge_off or automerge_off(base, repo)
    return checks.PR(number=d["number"], head_sha=d["headRefOid"], title=d["title"], body=d["body"] or "", files=files,
                     draft=d["isDraft"], mergeable=d["mergeable"] == "MERGEABLE",  # UNKNOWN 當不可合併
                     cfg=cfg, classifier_level=level, ci=ci, comments=comments, other_pr_files=others,
                     automerge_off=off, trusted=trusted, base=base, default_branch=dbranch, bootstrap=bootstrap)


def merge(number, sha, repo=None):
    _run(["pr", "merge", str(number), "--merge", "--match-head-commit", sha, "--delete-branch"] + (["--repo", repo] if repo else []))


def comment(number, body, repo=None):
    _run(["pr", "comment", str(number), "--body", body] + (["--repo", repo] if repo else []))
