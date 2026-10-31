# 由 dev-standard v0.6.2 產生，請勿手改；要改請改 dev-standard 的 components/pr-checks，再跑 sync.py update
"""七項 PR 檢查＋CI＋R2 reviewer 條件。純函式，不碰網路、不起子行程。

資料由 gh.py 取得，決策在 merge.py。repo 差異全在 PR.cfg（來自 .dev-standard/risk.json）。
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

from pr_checks import risk

MAX_BODY = 100_000
BAD_ACCEPT = re.compile(r"驗收.*(沒過|驗不了)")
DERIVED = re.compile(r"(?m)^DERIVED[:：][^\n]*$")
GENERAL = re.compile(r"通用\s*[？?：:]\s*(?:是|否)(?!\s*[／｜|]\s*[是否])")
ISSUE = re.compile(r"(?i)\b(?:refs|closes)\s+[\w./-]*#\d+")
NO_ISSUE = re.compile(r"(?i)no-issue")
OK_CI = ("SUCCESS", "SKIPPED", "NEUTRAL")


@dataclass
class PR:
    number: int
    head_sha: str
    title: str
    body: str
    files: list
    draft: bool
    mergeable: bool
    cfg: dict
    classifier_level: object = None          # classifier 的結論 R0–R3，沒設 classifier 為 None
    ci: list = field(default_factory=list)   # [(名稱, 結論)]
    comments: list = field(default_factory=list)  # [(作者, 內文)]
    other_pr_files: dict = field(default_factory=dict)  # {PR 編號: [檔]}
    automerge_off: bool = False
    trusted: tuple = ()
    base: object = None                      # PR 的 base 分支；None＝不明
    default_branch: object = None            # repo 預設分支；None＝不明（不明就不自動合併）
    bootstrap: bool = False                  # base 還沒有 risk.json，暫用本 PR 加入的版本


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


def declared(pr: PR):
    return risk.declared_level(pr.body)


def computed(pr: PR) -> str:
    return risk.classify(pr.files, pr.cfg, pr.classifier_level)[0]


def effective(pr: PR) -> str:
    """合併決定用的級：宣告與路徑算出的取高。"""
    return risk.effective(declared(pr), computed(pr))


def has_marker(pr: PR, kind: str) -> bool:
    """受信任作者在當前 head 上留的獨立一行 `<kind> <sha 前 7 碼以上>`。head 一變就失效。"""
    for author, text in pr.comments:
        if author not in pr.trusted:
            continue
        for sha in re.findall(rf"^{re.escape(kind)}[ \t]+([0-9a-fA-F]{{7,40}})[ \t]*$", text, re.M):
            if pr.head_sha.lower().startswith(sha.lower()):
                return True
    return False


def check_scope(pr):
    ok = has_marker(pr, "SCOPE: OK")
    return Result("1-範圍相符", ok, "" if ok else f"缺 `SCOPE: OK {pr.head_sha[:8]}` 留言（說明與改動對得上，head 變了要重留）")


def check_risk(pr):
    ok, msg = risk.check(pr.files, pr.body, pr.cfg, pr.classifier_level)
    if ok and not pr.cfg["r3_globs"] and not pr.cfg["classifier"]:
        msg += "；警告：risk.json 的 r3_globs 與 classifier 都是空的，R3 只能靠宣告"
    return Result("2-風險級", ok, msg)


def check_files(pr):
    pats = risk.BUILTIN_FORBIDDEN + pr.cfg["forbidden"]
    bad = [f for f in pr.files if any(re.search(p, risk.norm(f)) for p in pats)]
    m = re.search(r"^範圍：(.+)$", pr.body, re.M)
    if m:
        globs = [g.strip() for g in re.split(r"[,，]", m.group(1)) if g.strip()]
        bad += [f for f in pr.files if not any(fnmatch.fnmatch(f, g) for g in globs)]
    bad = sorted(set(bad))
    return Result("3-檔案範圍", not bad, "" if not bad else "不在允許範圍：" + "、".join(bad))


def check_outward(pr):
    hit = [f for f in pr.files if risk.is_outward(f, pr.cfg)]
    d = declared(pr)
    if hit and d not in ("R2", "R3"):
        return Result("4-對外影響", False, "改到對外／上架／部署檔，宣告至少 R2：" + "、".join(hit))
    return Result("4-對外影響", True)


def check_conflict(pr):
    mine = set(pr.files)
    clash = {n: sorted(mine & set(fs)) for n, fs in pr.other_pr_files.items() if mine & set(fs)}
    return Result("5-無衝突", not clash, "" if not clash else "與其他開著的 PR 改同檔：" + str(clash))


def check_derived(pr):
    lines = DERIVED.findall(pr.body)
    if not lines:
        return Result("6-DERIVED", False, "PR 內文缺 `DERIVED:` 行")
    if not any(GENERAL.search(x) for x in lines):
        return Result("6-DERIVED", False, "DERIVED 行沒有填好的 `通用：是|否`（範本的 <是｜否> 佔位不算）")
    return Result("6-DERIVED", True)


def check_refs(pr):
    """選用（risk.json 的 require_issue_ref）：有 Refs／Closes #N，或寫 no-issue。"""
    if not pr.cfg["require_issue_ref"]:
        return None
    ok = bool(ISSUE.search(pr.body) or NO_ISSUE.search(pr.body))
    return Result("6b-Refs", ok, "" if ok else "沒有 `Refs #N` 或 `Closes #N`（沒有對應 issue 請寫 no-issue）")


def check_acceptance(pr):
    bad = BAD_ACCEPT.findall(pr.body)
    return Result("7-驗收", not bad, "" if not bad else "驗收有「沒過」或「驗不了」")


def check_ci(pr):
    states = [s.upper() for _, s in pr.ci]
    ok = bool(states) and all(s in OK_CI for s in states)
    return Result("CI 全綠", ok, "" if ok else "CI 未全綠或沒有任何檢查：" + str(pr.ci))


def check_r2_review(pr):
    if risk.ORDER.index(effective(pr)) < 2:
        return Result("R2-reviewer", True, "非 R2，不需要")
    ok = has_marker(pr, "REVIEW: PASS")
    return Result("R2-reviewer", ok, "" if ok else f"R2 缺受信任作者的 `REVIEW: PASS {pr.head_sha[:8]}` 留言")


def run_all(pr: PR, ci_mode: bool = False):
    """ci_mode：只做靜態項；不看 CI 結論、留言標記、其他 PR。"""
    if len(pr.body) > MAX_BODY:  # 超長描述不進後面的 regex（避免退化）
        return [Result("0-描述長度", False, f"描述 {len(pr.body)} 字元，超過上限 {MAX_BODY}")]
    res = [check_risk(pr), check_files(pr), check_outward(pr), check_derived(pr), check_refs(pr), check_acceptance(pr)]
    res = [r for r in res if r is not None]
    if ci_mode:
        res += [Result("1-範圍相符", True, "CI 模式略過"), Result("5-無衝突", True, "CI 模式略過")]
    else:
        res += [check_scope(pr), check_conflict(pr), check_ci(pr), check_r2_review(pr)]
    return sorted(res, key=lambda r: r.name)
