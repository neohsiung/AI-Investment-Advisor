# 由 dev-standard v0.6.1 產生，請勿手改；要改請改 dev-standard 的 components/pr-checks，再跑 sync.py update
"""風險級：依改動路徑算出「至少是哪一級」，並解析 PR 第一行宣告。純函式，不碰網路。

規則（STANDARD.md 風險級合併表）：
  computed ＝ max(各路徑的級, classifier 的級)。R3 與 R2 的路徑樣式寫在 repo 的 .dev-standard/risk.json。
  宣告低於 computed ⇒ 檢查不過（訊息列出把級數推高的路徑）；宣告高於 computed 放行（保守）。
  合併、reviewer、R3 拒絕一律看 effective ＝ max(宣告, computed)，不信任宣告。
樣式用 fnmatch：`*` 會跨 `/`，所以 `.github/*` 涵蓋更深的路徑。
"""
from __future__ import annotations

import fnmatch
import re

ORDER = ["R0", "R1", "R2", "R3"]
# 通用的 R2：閘門本身、規則檔、hook、CI。repo 自己的另寫在 risk.json 的 r2_globs。
BUILTIN_R2 = [".dev-standard/*", ".github/*", ".claude/*", ".githooks/*", ".automerge-off",
              "AGENTS.md", "CLAUDE.md", "*/AGENTS.md", "*/CLAUDE.md"]
# 通用的禁區：憑證不由 PR 動。repo 自己的另寫在 risk.json 的 forbidden（regex）。
BUILTIN_FORBIDDEN = [r"(^|/)\.env$", r"(^|/)\.env\.(?!example$|sample$|template$)",
                     r"(^|/)(credentials|secrets?)[^/]*\.(json|ya?ml|txt)$"]
# 檢查工具本身：PR 改到它，就不能用 PR 自己的程式替自己評級或放行 ⇒ 一律視為 R3、要人合併。
# classifier 腳本的路徑另外從 risk.json 的 classifier argv 取。
RISK_FILE = ".dev-standard/risk.json"
TOOL_GLOBS = [".dev-standard/bin/pr_checks/*", ".dev-standard/risk.json",
              ".github/workflows/pr-checks.yml"]   # CI 跑的是 PR 自己的 workflow
LIST_KEYS = ("r2_globs", "r3_globs", "outward_globs", "forbidden", "trusted_authors", "ci_ignore")
KNOWN_KEYS = set(LIST_KEYS) | {"classifier", "require_issue_ref"}


class ConfigError(ValueError):
    """risk.json 壞了：工具失敗，不是「沒有設定」。"""


def lv_max(a: str, b: str) -> str:
    return a if ORDER.index(a) >= ORDER.index(b) else b


def _is_repo_file_arg(a: str) -> bool:
    """看起來像 repo 內相對路徑的參數：不是選項、不是絕對路徑、不跳出 repo，且有目錄或副檔名。"""
    # 一定要有「/」（scripts/x.py、./tool）：python3.11、node.exe 這類帶點的直譯器名不能被當成腳本；有空白的是行內程式碼
    return (not a.startswith("-") and not a.startswith("/") and ".." not in a.split("/")
            and "/" in a and not any(ch.isspace() for ch in a))


def load_config(data) -> dict:
    """驗 risk.json 的內容並補預設。未知的鍵、型別不對都丟 ConfigError（打錯字不能默默變成沒設定）。"""
    if not isinstance(data, dict):
        raise ConfigError("risk.json 最外層必須是物件")
    bad = sorted(k for k in data if k not in KNOWN_KEYS and not k.startswith("_"))
    if bad:
        raise ConfigError("risk.json 有不認得的鍵：" + "、".join(bad)
                          + "（允許：" + "、".join(sorted(KNOWN_KEYS)) + "；註解用 _ 開頭的鍵）")
    cfg: dict = {}
    for k in LIST_KEYS:
        v = data.get(k, [])
        if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
            raise ConfigError(f"risk.json 的 {k} 必須是非空字串清單")
        cfg[k] = list(v)
    for rx in cfg["forbidden"]:
        try:
            re.compile(rx)
        except re.error as e:
            raise ConfigError(f"risk.json 的 forbidden 有不合法的 regex {rx!r}：{e}")
    c = data.get("classifier")
    if c is not None and not (isinstance(c, list) and c and all(isinstance(x, str) and x for x in c)):
        raise ConfigError("risk.json 的 classifier 必須是 argv 字串清單（不是 shell 字串），例：[\"python3\", \"scripts/lane.py\"]")
    if c is not None:
        # 改到 classifier 的 PR 要算成改工具（R3），工具只能從 argv 認出檔案。
        # 規則：腳本路徑之前不准有任何選項（擋 -c／-m／-e 與 -cCODE、-xc、--eval= 等黏寫），最多兩個前綴字（例：uv run）。
        idx = next((i for i, a in enumerate(c) if _is_repo_file_arg(a)), None)
        if idx is None or idx > 2 or any(a.startswith("-") for a in c[:idx]):
            raise ConfigError("risk.json 的 classifier 要寫成「直譯器（可省）＋ repo 內的腳本」，腳本前面不能有任何選項，"
                              "例：[\"python3\", \"scripts/dev/lane_risk.py\"]；-c／-m 行內形式認不出檔案，改到它的 PR 不會被當成改工具")
    cfg["classifier"] = c
    rq = data.get("require_issue_ref", False)
    if not isinstance(rq, bool):
        raise ConfigError("risk.json 的 require_issue_ref 必須是 true／false")
    cfg["require_issue_ref"] = rq
    return cfg


def norm(path: str) -> str:
    p = path.strip()
    while p.startswith("./"):
        p = p[2:]
    return p


def _match(p: str, pats) -> bool:
    return any(fnmatch.fnmatch(p, pat) for pat in pats)


def is_outward(path: str, cfg: dict) -> bool:
    return _match(norm(path), cfg["outward_globs"])


def is_tool_path(path: str, cfg: dict) -> bool:
    """path 是不是檢查工具本身：pr_checks 程式、risk.json、risk.json 指定的 classifier 腳本。"""
    p = norm(path)
    return _match(p, TOOL_GLOBS) or p in {norm(a) for a in (cfg.get("classifier") or [])}


def tool_changed(paths, cfg: dict) -> list:
    return sorted({norm(p) for p in paths if p.strip() and is_tool_path(p, cfg)})


def classify_path(path: str, cfg: dict) -> str:
    p = norm(path)
    if is_tool_path(p, cfg) or _match(p, cfg["r3_globs"]):
        return "R3"
    if _match(p, BUILTIN_R2 + cfg["r2_globs"] + cfg["outward_globs"]):
        return "R2"
    return "R0" if p.endswith(".md") else "R1"


def classify(paths, cfg: dict, classifier_level=None) -> tuple:
    """回傳 (computed, {級: [路徑]})。classifier_level 是外部 classifier 的結論（或 None）；
    它只會把級往上抬，路徑樣式判出的 R3 不會被 classifier 壓低。"""
    by: dict = {}
    top = "R0"
    for raw in paths:
        if not raw.strip():
            continue
        lv = classify_path(raw, cfg)
        by.setdefault(lv, []).append(norm(raw))
        top = lv_max(top, lv)
    if classifier_level is not None:
        top = lv_max(top, classifier_level)
    return top, by


_FORMS = [
    re.compile(r"^\s*(?P<risk>R[0-3])(?![0-9A-Za-z])"),                                          # R2、R2：說明
    re.compile(r"^\s*[ABC]\s*\(\s*(?P<risk>R[0-3])\s*\)"),                                        # B (R2)
    re.compile(r"^\s*風險級\s*[／/]\s*車道\s*[:：]\s*(?P<risk>R[0-3])\s*[／/]\s*[ABC](?![A-Za-z])"),  # 範本
]


def declared_level(body: str):
    """PR 第一個非空行要是 R0–R3（或 `B (R2)` 這種寫法）；否則回 None。"""
    for line in body.lstrip("﻿").splitlines():
        if line.strip():
            for rx in _FORMS:
                m = rx.match(line)
                if m:
                    return m.group("risk")
            return None
    return None


def effective(declared, computed: str) -> str:
    """合併決定用的級：宣告與算出來的取高。宣告只能把級往上抬，不能壓低。"""
    return computed if declared is None else lv_max(declared, computed)


def check(paths, body: str, cfg: dict, classifier_level=None) -> tuple:
    """回傳 (通過?, 訊息)。"""
    computed, by = classify(paths, cfg, classifier_level)
    declared = declared_level(body)
    if declared is None:
        return False, f"PR 第一行要寫風險級 R0–R3；依路徑應至少為 {computed}"
    if ORDER.index(declared) < ORDER.index(computed):
        high = [p for lv in ORDER[ORDER.index(declared) + 1:] for p in by.get(lv, [])]
        why = ("、".join(high[:10]) + ("…" if len(high) > 10 else "")) if high else "classifier 的判定"
        return False, f"PR 第一行寫 {declared}，依路徑應至少為 {computed}：{why}"
    note = "" if declared == computed else f"（宣告 {declared} 高於算出的 {computed}，保守，放行）"
    return True, f"風險級 {effective(declared, computed)}{note}"
