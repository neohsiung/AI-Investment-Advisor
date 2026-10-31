#!/usr/bin/env python3
# 由 dev-standard v0.6.1 產生，請勿手改；要改請改 dev-standard 的 components/guard，再跑 sync.py update
"""guard.py — Claude Code PreToolUse 硬底線（來由：hermes hermes_guard.py 與它的測試，加上 litov 的 worktree 基底檢查；dev-standard §1、§2、§6）

CLAUDE.md／AGENTS.md 是建議，擋不住任何事；這支是擋得住的那一層（exit 2 在權限規則之前生效，bypass 也一樣）。
只擋「錯一次就有實際損失」的動作，其餘一律放行 —— 誤報會讓整條訊號被忽略（hermes 地雷 #147）。
每條「擋」都有一條長得很像但該放行的測試（tests/test_guard.py）。

通用的擋（每個 repo 都有，不用設定）：
  ① 主幹：在 main／master 上 git commit、git push 到 main／master；git worktree add -b／-B 的基底不是 origin/…
  ② 印出憑證：用文字工具讀 .env*／憑證檔；Edit／Write／Read 憑證檔
  ③ 取出憑證值：Keychain 的 -w／-g 讀值、dump-keychain -d、security export、docker compose config（沒加
     --no-env-resolution）、docker inspect 印 Env、docker exec 印環境變數 —— 這是「減速丘」不是邊界，
     真正的上限在供應商端每把 key 的額度
repo 自己的擋（.dev-standard/guard.json，缺的欄位＝不啟用；範例見 guard.example.json）：
  ④ protected_paths：R3 與正式環境的檔（regex，相對 repo 根目錄）—— 不准 Edit／Write；Bash 這邊是盡力而為（best-effort）：
     擋 > >> tee（含引號包起來的目標）、sed -i、mv、cp 的目標，擋不住 python -c／awk 等任意程式自己寫檔
  ⑤ blocked_commands：危險指令（[{"pattern": regex, "why": "…"}]，逐段比對）—— 例：重啟 gateway
  ⑥ live_tree：另一棵「正式樹」（開發 session 不該在那裡動 git 或寫帳本）。path／env／container_root、
     git_forbidden、protected_state（regex，相對正式樹）
  ⑦ exec_guard：用 AST 算 import 閉包，直接執行「碰得到下單模組」的腳本就擋（比路徑清單準，不會漂）。
     modules／calls／scripts_dir_name
  ⑧ dotenv_out_only：這些指令的 --out 只能寫成 .env* 檔名（不然繞過 ② 的檔名比對）
  ⑨ private_egress：私有目錄（待核可草稿、個資）的內容不准交給會出網的 CLI（agy、gemini、codex、curl、wget、scp、sftp、
     rsync、nc、ncat、gh、ssh；可用 clis 改）。paths（目錄，相對 repo 根目錄）、allow（目錄內可出網的檔，例 .gitkeep）。
     只看同一條管線；cd 進私有目錄或把私有路徑指給變數後，同一條指令後面的出網 CLI 一律擋。沒設 paths ＝ 關。
     擋不到的（python -c 自己開 socket、先 cp 出去再送）不在範圍。來由：litov#140。
  secret_extraction: false 可關掉 ③。

內建保護（不能設定關掉）：.dev-standard/guard.json、.claude/settings.json、.claude/settings.local.json、.claude/hooks/** 不准 Edit／Write／
  Bash 重導寫入 —— 護欄自己的設定只有人能改。
guard.json 存在但內容壞了（不是合法 JSON、型別不對、缺 pattern、regex 編不起來）時，除了 Read 一律擋（不靜默退回「沒有設定」）；
  修它請用 `!` 自己改。任何未預期的例外也 exit 2（hook 的 exit 1／逾時都是放行，所以一律走 2）。
被擋的動作要人做：回覆裡請使用者用 `!` 前綴自己執行。不要繞路。
安裝：.claude/settings.json 的 hooks.PreToolUse（sync.py wire 會幫你掛）：
  {"matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit|Read", "hooks": [{"type": "command",
   "command": "python3 \\"$CLAUDE_PROJECT_DIR\\"/.claude/hooks/guard.py"}]}
只用標準函式庫、相容 python 3.9。
"""
from __future__ import annotations

import ast
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

# 憑證檔：名字本身就是憑證的才算。docs/credentials.md、tests/test_credentials.py 這類一般檔不算（誤報會讓訊號被忽略）。
SECRET_NAME = re.compile(r"(^|/)(\.env(\.[\w.-]+)?|\.[\w-]+_credentials|credentials\.json|auth\.json|id_(rsa|ed25519|ecdsa)"
                         r"|[\w.-]+\.(pem|key|p12|pfx))$")
SECRET_OK = re.compile(r"\.(example|sample|template)$|\.pub(lic\.key)?$")
READ_VERBS = {"cat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg", "sed", "awk", "strings",
              "xxd", "od", "cut", "sort", "uniq", "diff", "bat", "nl", "tac", "cp", "base64"}
WRAPPERS = {"rtk", "proxy", "sudo", "env", "command", "time", "nice", "nohup"}
MAIN = {"main", "master"}
OPERATORS = {";", "&", "&&", "|", "||", "\n", "|&", ";;"}
OPS = {";", "&&", "||", "|", "&", ";;", "|&"}
GIT_OPT_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
DEFAULT_GIT_FORBIDDEN = ["checkout", "switch", "reset", "rebase", "merge", "stash", "commit", "cherry-pick",
                         "revert", "clean"]
SECRET_HOW = "只驗存在／長度，不印值（例：test -s <檔>、`security find-generic-password -s <名> >/dev/null; echo $?`）；需要值請使用者自己處理"
WT_HOW = "先開分支：.dev-standard/bin/wt.sh new <type>/<描述>（wt 元件）"

# 由 configure() 依 guard.json 填入；沒設 live_tree 就都是 None／空
LIVE = None                      # 正式樹的 realpath
CONTAINER_ROOT = None            # 容器內的正式樹路徑（docker exec 指令裡會出現）
GIT_FORBIDDEN = set(DEFAULT_GIT_FORBIDDEN)
PROTECTED_STATE = None           # 編譯後的 regex，相對正式樹
ORDER_MODULES = set()
ORDER_CALLS = ()
SCRIPTS_DIR = "scripts"
DOTENV_ONLY = set()
EXTERNAL_CLIS_DEFAULT = ("agy", "gemini", "codex", "curl", "wget", "scp", "sftp", "rsync", "nc", "ncat", "gh", "ssh")
EGRESS = None                    # {"clis": set, "dirs": [(完整路徑, [regex…], [祖先 regex…])], "allow": set}；None ＝ 關
SHELL_C = re.compile(r"^-[a-zA-Z]*c[a-zA-Z]*$")
SHELLS = {"bash", "sh", "zsh", "dash"}


def is_secret(path: str) -> bool:
    return bool(SECRET_NAME.search(path)) and not SECRET_OK.search(path)


def block(reason: str, how: str = "請使用者用 `!` 前綴自己執行，不要繞路") -> None:
    sys.stderr.write(f"⛔ guard：{reason}\n   → {how}\n   （dev-standard §1／§2／§6）\n")
    sys.exit(2)


# ── 設定 ────────────────────────────────────────────────────────────────────
def find_root(cwd: str) -> str:
    """往上找 .dev-standard/guard.json 或 .git（目錄或 worktree 的檔）；都沒有就用 cwd。不呼叫 git。"""
    d = os.path.abspath(cwd)
    while True:
        if os.path.exists(os.path.join(d, ".dev-standard", "guard.json")) or os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.abspath(cwd)
        d = parent


def _strs(v, what: str) -> list:
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError(f"{what} 必須是字串清單")
    return v


def _regexes(v, what: str) -> list:
    for x in _strs(v, what):
        try:
            re.compile(x)
        except re.error as e:
            raise ValueError(f"{what} 有編不起來的 regex {x!r}：{e}")
    return v


def validate_config(cfg: dict) -> None:
    """完整驗 guard.json 的型別、必備鍵、regex；任何問題丟 ValueError。缺的欄位＝不啟用，不算錯。"""
    if "protected_paths" in cfg:
        _regexes(cfg["protected_paths"], "protected_paths")
    if "blocked_commands" in cfg:
        bc = cfg["blocked_commands"]
        if not isinstance(bc, list):
            raise ValueError("blocked_commands 必須是清單")
        for i, item in enumerate(bc):
            if not isinstance(item, dict) or not isinstance(item.get("pattern"), str):
                raise ValueError(f"blocked_commands[{i}] 必須是物件且有字串 pattern")
            _regexes([item["pattern"]], f"blocked_commands[{i}].pattern")
            if "why" in item and not isinstance(item["why"], str):
                raise ValueError(f"blocked_commands[{i}].why 必須是字串")
    if "secret_extraction" in cfg and not isinstance(cfg["secret_extraction"], bool):
        raise ValueError("secret_extraction 必須是 true／false")
    if "live_tree" in cfg:
        lt = cfg["live_tree"]
        if not isinstance(lt, dict):
            raise ValueError("live_tree 必須是物件")
        for k in ("path", "env", "container_root"):
            if k in lt and not isinstance(lt[k], str):
                raise ValueError(f"live_tree.{k} 必須是字串")
        if "git_forbidden" in lt:
            _strs(lt["git_forbidden"], "live_tree.git_forbidden")
        if "protected_state" in lt:
            _regexes(lt["protected_state"], "live_tree.protected_state")
    if "exec_guard" in cfg:
        eg = cfg["exec_guard"]
        if not isinstance(eg, dict):
            raise ValueError("exec_guard 必須是物件")
        for k in ("modules", "calls"):
            if k in eg:
                _strs(eg[k], f"exec_guard.{k}")
        if "scripts_dir_name" in eg and not isinstance(eg["scripts_dir_name"], str):
            raise ValueError("exec_guard.scripts_dir_name 必須是字串")
    if "dotenv_out_only" in cfg:
        _strs(cfg["dotenv_out_only"], "dotenv_out_only")
    if "private_egress" in cfg:
        pe = cfg["private_egress"]
        if not isinstance(pe, dict):
            raise ValueError("private_egress 必須是物件")
        for k in ("clis", "paths", "allow"):
            if k in pe:
                _strs(pe[k], f"private_egress.{k}")
        for p in pe.get("paths", []):
            if not p.strip("/") or p.startswith(("/", "~")) or ".." in p.split("/"):
                raise ValueError(f"private_egress.paths 要是相對 repo 根目錄的目錄，不接受 {p!r}")


def load_config(root: str) -> dict:
    """沒有檔案＝沒有設定；有檔案卻壞了（JSON、型別、必備鍵、regex）＝擋（回傳 {"__error__": 原因}）。"""
    p = os.path.join(root, ".dev-standard", "guard.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("最外層必須是物件")
        validate_config(cfg)
        return cfg
    except (OSError, ValueError) as e:
        return {"__error__": f"{p} 讀不了或內容不合法：{e}"}


def configure(cfg: dict) -> None:
    global LIVE, CONTAINER_ROOT, GIT_FORBIDDEN, PROTECTED_STATE, ORDER_MODULES, ORDER_CALLS, SCRIPTS_DIR, DOTENV_ONLY, EGRESS
    lt = cfg.get("live_tree") or {}
    raw = (os.environ.get(lt["env"]) if lt.get("env") else None) or lt.get("path")
    LIVE = os.path.realpath(os.path.expanduser(raw)) if raw else None
    CONTAINER_ROOT = lt.get("container_root") or None
    GIT_FORBIDDEN = set(lt.get("git_forbidden") or DEFAULT_GIT_FORBIDDEN)
    ps = lt.get("protected_state") or []
    PROTECTED_STATE = re.compile("|".join(f"(?:{p})" for p in ps)) if ps else None
    eg = cfg.get("exec_guard") or {}
    ORDER_MODULES = set(eg.get("modules") or [])
    ORDER_CALLS = tuple(eg.get("calls") or [])
    SCRIPTS_DIR = eg.get("scripts_dir_name") or "scripts"
    DOTENV_ONLY = set(cfg.get("dotenv_out_only") or [])
    EGRESS = build_egress(cfg.get("private_egress") or {})


def in_live(path: str):
    """path 在正式樹裡就回傳相對路徑，否則 None。"""
    if LIVE is None:
        return None
    rp = os.path.realpath(path)
    if rp == LIVE or rp.startswith(LIVE + os.sep):
        return os.path.relpath(rp, LIVE)
    return None


def to_host(token: str, cwd: str) -> str:
    if LIVE and CONTAINER_ROOT:
        if token.rstrip("/") == CONTAINER_ROOT:
            return LIVE
        if token.startswith(CONTAINER_ROOT + "/"):
            return os.path.join(LIVE, token[len(CONTAINER_ROOT) + 1:])
    token = os.path.expanduser(token)
    return token if os.path.isabs(token) else os.path.join(cwd, token)


def current_branch(path: str) -> str:
    """讀 .git／gitdir 的 HEAD（不呼叫 git；worktree 的 .git 是指向 gitdir 的檔）。detached 或讀不到回 ""。"""
    head = None
    d = os.path.realpath(path)
    while d != os.path.dirname(d):
        g = os.path.join(d, ".git")
        if os.path.isdir(g):
            head = os.path.join(g, "HEAD")
            break
        if os.path.isfile(g):
            try:
                txt = open(g, encoding="utf-8").read().strip()
            except OSError:
                return ""
            if txt.startswith("gitdir:"):
                gd = txt.split(":", 1)[1].strip()
                head = os.path.join(gd if os.path.isabs(gd) else os.path.join(d, gd), "HEAD")
            break
        d = os.path.dirname(d)
    try:
        ref = open(head, encoding="utf-8").read().strip() if head else ""
    except OSError:
        return ""
    if not ref.startswith("ref:"):
        return ""
    name = ref.split(":", 1)[1].strip()
    return name[len("refs/heads/"):] if name.startswith("refs/heads/") else name


# ── 切字 ────────────────────────────────────────────────────────────────────
def strip_wrappers(w: list) -> list:
    while w and (w[0] in WRAPPERS or re.match(r"^\w+=", w[0])):
        w = w[1:]
    return w


def segments(cmd: str) -> list:
    """依 shell 運算子（; & && | || 換行）切段，引號裡的不切；開頭的包裝指令與變數指派去掉。"""
    lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|\n")
    lx.whitespace = " \t\r"
    lx.whitespace_split = True
    try:
        toks = list(lx)
    except ValueError:                                   # 引號沒閉合：退回粗切，寧可多看
        toks = cmd.replace("\n", " ; ").split()
    out, cur = [], []
    for t in toks + [";"]:
        if t in OPERATORS:
            cur = strip_wrappers(cur)
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    return out


def segments_with_ops(cmd: str) -> list:
    """(原始字詞, 前一個運算子, 後一個運算子)。切不開（引號不成對）回空清單 ⇒ 呼叫端當成判斷不了。
    換行當空白（跟 hermes 一樣）：heredoc 內文不會被當成獨立指令而讓變數判斷變寬鬆。"""
    try:
        lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|")
        lx.whitespace_split = True
        toks = list(lx)
    except ValueError:
        return []
    out, cur, prev = [], [], None
    for tok in toks:
        if tok in OPS:
            if cur:
                out.append((cur, prev, tok))
            cur, prev = [], tok
        else:
            cur.append(tok)
    if cur:
        out.append((cur, prev, None))
    return out


# ── ① 主幹 ──────────────────────────────────────────────────────────────────
def git_parts(w: list, cwd: str) -> tuple:
    """回傳 (git 子指令, 子指令之後的參數, git 作用的目錄)。跳過 -C／-c 等帶值的全域選項。"""
    i, target = 1, cwd
    while i < len(w) and w[i].startswith("-"):
        opt = w[i].split("=", 1)[0]
        if opt in GIT_OPT_WITH_VALUE and "=" not in w[i]:
            if opt == "-C" and i + 1 < len(w):
                target = os.path.join(target, w[i + 1])
            i += 2
        else:
            i += 1
    if i >= len(w):
        return "", [], target
    return w[i], w[i + 1:], target


def push_hits_main(args: list, target: str) -> bool:
    refs = [a for a in args if not a.startswith("-")]
    if len(refs) >= 2:                                   # git push <remote> <refspec>…
        for spec in refs[1:]:
            dst = spec.lstrip("+").split(":")[-1].replace("refs/heads/", "")
            src = spec.lstrip("+").split(":")[0]
            if dst in MAIN or (":" not in spec and src == "HEAD" and current_branch(target) in MAIN):
                return True
        return False
    # 沒給 refspec：推的是目前分支（或它的 upstream）
    if current_branch(target) in MAIN:
        return True
    try:
        r = subprocess.run(["git", "-C", target, "rev-parse", "--abbrev-ref", "@{u}"], capture_output=True, text=True)
    except OSError:
        return False
    return r.stdout.strip().split("/")[-1] in MAIN


def worktree_new_branch_base(args: list):
    """git worktree add 帶 -b／-B 時回傳 (True, 基底或 None)；沒有 -b／-B 回傳 (False, None)。（來由：litov）"""
    if not args or args[0] != "add":
        return False, None
    new_branch, pos, i = False, [], 1
    while i < len(args):
        a = args[i]
        if a in ("-b", "-B"):
            new_branch, i = True, i + 2                  # 跳過分支名
        elif a.startswith(("-b", "-B")) and not a.startswith("--"):
            new_branch, i = True, i + 1                  # -bname
        elif a.startswith("-"):
            i += 1
        else:
            pos.append(a)
            i += 1
    return new_branch, (pos[1] if len(pos) > 1 else None)


def check_trunk(segs: list, cwd: str) -> None:
    for w in segs:
        if os.path.basename(w[0]) != "git":
            continue
        sub, args, target = git_parts(w, cwd)
        if sub == "commit" and current_branch(target) in MAIN:
            block("在 main 上 commit", WT_HOW)
        if sub == "worktree":
            new_branch, base = worktree_new_branch_base(args)
            if new_branch and not (base or "").startswith("origin/"):
                block(f"git worktree add -b/-B 的基底是 {base or '（未指定，預設 HEAD）'}，不是 origin/…（本地 main 常落後 origin/main）",
                      "改用 .dev-standard/bin/wt.sh new <type>/<描述>（以 origin/main 為基底）；"
                      "或手動：git fetch origin && git worktree add -b <分支> <路徑> origin/main")
        if sub == "push" and push_hits_main(args, target):
            block("push 到 main", "push 自己的分支再開 PR")


# ── ⑥ 正式樹裡的 git（DD-2026-1025-guard-target-repo：依指令實際作用的 repo 判斷）────────────────
# 擋＝新判定 OR 舊判定，沒有讓步，所以只會更嚴。2026-10-25 三輪審查：任何「確定在正式樹外就讓舊判定讓步」
# 的模擬都被 bash 語意繞過（cd 失敗接 ;、單引號、heredoc、export 同行展開順序、$_／LINENO 等動態變數）
# ⇒ 不做讓步。暫存 clone 請用字面絕對路徑（舊判定本來就放行）。
ASSIGN = re.compile(r"^([A-Za-z_]\w*)=(.*)$", re.S)
VAR_REF = re.compile(r"\$\{(\w+)\}|\$(\w+)")
VAR_MUTATORS = re.compile(r"(?<![\w-])(unset|read|declare|typeset|eval|local|readonly|getopts|mapfile|readarray|"
                          r"source|for|select|while|until|case|let|export\s+-n)(?![\w-])|\+=|(^|[\s;&|(])\.\s")
GIT_OPT_WITH_ARG = {"-c", "--namespace", "--super-prefix", "--config-env", "--exec-path", "--list-cmds"}
SHELL_LEAD = {"then", "do", "else", "elif", "{", "!", "if", "while", "until", "time"}


def expand(token: str, env: dict):
    """展開 $VAR／${VAR}；有任何一個展開不了（未知、不確定）就回 None。"""
    bad = []

    def sub(m):
        v = env.get(m.group(1) or m.group(2))
        if v is None:
            bad.append(m.group(0))
            return ""
        return v
    out = VAR_REF.sub(sub, token)
    if bad or "$" in out or "`" in out:
        return None
    return out


def resolve(token: str, cwd, env: dict):
    """路徑 token → host 路徑；判斷不了回 None。"""
    t = expand(token, env)
    if t is None or t == "" or t.startswith("-"):
        return None
    t = os.path.expanduser(t)
    if t.startswith("~"):
        return None
    if os.path.isabs(t) or (CONTAINER_ROOT and t.rstrip("/") == CONTAINER_ROOT):
        return to_host(t, "/")
    return None if cwd is None else os.path.join(cwd, t)


def live_or_unknown(path) -> bool:
    return path is None or in_live(path) is not None


def base_env() -> dict:
    env = dict(os.environ)
    env["PWD"] = env["OLDPWD"] = None                    # hook 行程的 PWD 不是 bash session 的
    return env


def split_prefix(raw: list, env: dict, trusted: bool, certain: bool) -> tuple:
    """開頭的 `NAME=值`／`export NAME=值`／包裝指令後的指派 ⇒ (前綴, 指令字詞)。
    整段都是指派而且確定會執行（certain）時寫進 env；不確定就把那些變數設成「判斷不了」。"""
    w = list(raw)
    exported = bool(w) and w[0] == "export"
    if exported:
        w = w[1:]
    prefix = {}
    while w and ASSIGN.match(w[0]):
        k, v = ASSIGN.match(w[0]).groups()
        prefix[k] = expand(v, {**env, **prefix}) if trusted else None
        w = w[1:]
    if not w or exported:
        for k, v in prefix.items():
            env[k] = v if certain else None
    while w and (w[0] in WRAPPERS or w[0] in SHELL_LEAD):     # env GIT_DIR=… git …、then git …
        w = w[1:]
        while w and ASSIGN.match(w[0]):
            k, v = ASSIGN.match(w[0]).groups()
            prefix[k] = expand(v, {**env, **prefix}) if trusted else None
            w = w[1:]
    return prefix, w


def git_target(args: list, gcwd, env: dict, prefix: dict) -> tuple:
    """git 的引數 → (子指令, 是否作用在正式樹或判斷不了, -C 之後的目錄)。
    git 目錄：--git-dir／GIT_DIR，沒給就從 -C 之後的目錄往上找 ⇒ 看那個目錄。工作樹：--work-tree／GIT_WORK_TREE，沒給就是那個目錄。"""
    scope = {**env, **prefix}
    gdir_tok = ("GIT_DIR" in scope and scope["GIT_DIR"] is not None, scope.get("GIT_DIR"))
    work_tok = ("GIT_WORK_TREE" in scope and scope["GIT_WORK_TREE"] is not None, scope.get("GIT_WORK_TREE"))
    unknown_env = any(k in scope and scope[k] is None and k in prefix for k in ("GIT_DIR", "GIT_WORK_TREE")) \
        or any(k in env and env[k] is None for k in ("GIT_DIR", "GIT_WORK_TREE"))
    rest = list(args)
    while rest and rest[0].startswith("-"):
        o = rest[0]
        if o == "-C" and len(rest) >= 2:
            gcwd = resolve(rest[1], gcwd, env) if gcwd is not None or os.path.isabs(os.path.expanduser(rest[1])) \
                else None
            rest = rest[2:]
        elif o in ("--git-dir", "--work-tree") and len(rest) >= 2:
            (gdir_tok, work_tok) = ((True, rest[1]), work_tok) if o == "--git-dir" else (gdir_tok, (True, rest[1]))
            rest = rest[2:]
        elif o.startswith("--git-dir="):
            gdir_tok, rest = (True, o.split("=", 1)[1]), rest[1:]
        elif o.startswith("--work-tree="):
            work_tok, rest = (True, o.split("=", 1)[1]), rest[1:]
        elif o == "-c" and len(rest) >= 2 and rest[1].lower().startswith("core.worktree="):
            work_tok, rest = (True, rest[1].split("=", 1)[1]), rest[2:]
        elif o in GIT_OPT_WITH_ARG and len(rest) >= 2:
            rest = rest[2:]
        else:
            rest = rest[1:]
    sub = rest[0].rstrip(")") if rest else ""
    targets = [gcwd]                                     # 沒給 git 目錄 ⇒ 從這裡找；給了也照看（保守）
    if gdir_tok[0]:
        targets.append(resolve(gdir_tok[1], gcwd, env))
    if work_tok[0]:
        targets.append(resolve(work_tok[1], gcwd, env))
    live = unknown_env or any(live_or_unknown(t) for t in targets)
    return sub, live, gcwd


def old_git_live(cmd: str, cwd: str) -> list:
    """舊版（DD-2026-1008）的判定，原樣保留：只列會擋的子指令。"""
    hits = []
    for w in segments(cmd):
        if w[0] == "cd" and len(w) > 1:
            cwd = to_host(w[1], cwd)
            continue
        if w[0] == "git":
            gcwd, rest = cwd, w[1:]
            while len(rest) >= 2 and rest[0] == "-C":
                gcwd, rest = to_host(rest[1], gcwd), rest[2:]
            sub = rest[0] if rest else ""
            if in_live(gcwd) is not None and sub in GIT_FORBIDDEN:
                hits.append(sub)
    m = re.search(r"\bcd\s+(\S+)\s*&&\s*git\s+(\w[\w-]*)", cmd)
    if m and in_live(to_host(m.group(1), cwd)) is not None and m.group(2) in GIT_FORBIDDEN:
        hits.append(m.group(2))
    return hits


def new_git_check(cmd: str, cwd: str) -> None:
    """依實際作用的 repo 判斷：只會比舊判定更嚴；判斷不了就當正式樹（有設 live_tree 才有意義）。
    在 main 上 commit 也順便依 cd 後的目錄判斷（check_trunk 只看 -C）。"""
    how = "開發一律在 worktree：.dev-standard/bin/wt.sh new <type>/<描述>；暫存 clone 用字面絕對路徑、cd 後面接 &&"
    segs = segments_with_ops(cmd)
    trusted = segs != [] and not VAR_MUTATORS.search(cmd)
    env, gcwd_now = base_env(), cwd
    for raw, prev, nxt in segs:
        certain = trusted and prev in (None, ";") and nxt not in ("|", "&", "|&")
        prefix, w = split_prefix(raw, env, trusted, certain)
        if not w:
            continue
        head = w[0]
        if head.startswith("("):                         # 子 shell：之後的目錄判斷不了
            gcwd_now = None
            head = head.lstrip("(")
            w = [head] + w[1:] if head else w[1:]
            if not w:
                continue
            head = w[0]
        if head in ("cd", "pushd"):
            gcwd_now = resolve(w[1], gcwd_now, env) if len(w) > 1 else None
            continue
        if head == "popd":
            gcwd_now = None
            continue
        if os.path.basename(head) != "git":
            continue
        sub, live, gcwd = git_target(w[1:], gcwd_now, env, prefix)
        if LIVE and sub in GIT_FORBIDDEN and live:
            block(f"在正式樹 {LIVE}（或判斷不了的目錄，保守當正式樹）執行 git {sub}", how)
        if sub == "commit" and gcwd is not None and current_branch(gcwd) in MAIN:
            block("在 main 上 commit", WT_HOW)


def check_git(cmd: str, cwd: str) -> None:
    """新程式碼丟例外 ⇒ 只用舊判定（例外絕不能變成放行）。"""
    try:
        new_git_check(cmd, cwd)
    except SystemExit:
        raise
    except Exception:                                    # noqa: BLE001 — 退回舊判定，不放寬
        pass
    for sub in old_git_live(cmd, cwd):
        block(f"在正式樹 {LIVE} 執行 git {sub}",
              "開發一律在 worktree：.dev-standard/bin/wt.sh new <type>/<描述>；暫存 clone 用字面絕對路徑（可用同一行開頭的 NAME=/絕對路徑 指派）、cd 後面接 &&")


# ── ⑦ 下單模組：import 閉包 ──────────────────────────────────────────────────
def _imports(path: str) -> set:
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except Exception:                                    # noqa: BLE001 — 讀不了／語法錯：當作沒有 import，後面仍有字串層
        return set()
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.add(n.module)
    return out


def _resolve_mod(mod: str, scripts_dir: str):
    parts = mod.split(".")
    for cand in (os.path.join(scripts_dir, *parts) + ".py",
                 os.path.join(scripts_dir, *parts, "__init__.py"),
                 os.path.join(scripts_dir, parts[-1] + ".py")):
        if os.path.isfile(cand):
            return cand
    return None


class Timeout(Exception):
    """import 閉包分析超過時限：判斷不了就擋（main 轉成 exit 2）。"""


ANALYSIS_DEADLINE_S = 8.0


def _cache_path(script: str):
    import hashlib
    key = hashlib.sha1("\0".join([os.path.realpath(script), SCRIPTS_DIR, *sorted(ORDER_MODULES)]).encode()).hexdigest()
    return os.path.join(tempfile.gettempdir(), f"dev-standard-guard-{os.getuid()}", key + ".json")


def _cache_load(script: str):
    """命中條件：快取檔屬於自己、沒有他人可寫，且記下的每個檔／目錄 mtime 都沒變。任何異常都當沒命中。"""
    try:
        p = _cache_path(script)
        st = os.stat(p)
        if st.st_uid != os.getuid() or st.st_mode & 0o022:
            return None
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for path, m in data["mtimes"].items():
            if os.stat(path).st_mtime_ns != m:
                return None
        return bool(data["result"])
    except Exception:                                    # noqa: BLE001 — 快取只是加速，壞了就重算
        return None


def _cache_store(script: str, result: bool, seen: set, scripts_dir: str) -> None:
    try:
        p = _cache_path(script)
        os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
        mtimes = {x: os.stat(x).st_mtime_ns for x in list(seen) + [scripts_dir] if os.path.exists(x)}
        tmp = p + f".{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"result": result, "mtimes": mtimes}, f)
        os.replace(tmp, p)
    except Exception:                                    # noqa: BLE001 — 寫不進去只是少一次加速
        pass


def reaches_orders(script: str) -> bool:
    """script 的 import 閉包（限 scripts 目錄底下的本地模組）是否碰得到下單模組。超過 ANALYSIS_DEADLINE_S 丟 Timeout。"""
    cached = _cache_load(script)
    if cached is not None:
        return cached
    deadline = time.monotonic() + ANALYSIS_DEADLINE_S
    root = script
    while root != os.path.dirname(root) and os.path.basename(root) != SCRIPTS_DIR:
        root = os.path.dirname(root)
    scripts_dir = root if os.path.basename(root) == SCRIPTS_DIR else os.path.dirname(script)
    seen, todo = set(), [script]
    while todo:
        if time.monotonic() > deadline:
            raise Timeout(f"import 閉包分析超過 {ANALYSIS_DEADLINE_S:g} 秒（{script}）")
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        if os.path.splitext(os.path.basename(f))[0] in ORDER_MODULES:
            _cache_store(script, True, seen, scripts_dir)
            return True
        imps = _imports(f)
        if time.monotonic() > deadline:
            raise Timeout(f"import 閉包分析超過 {ANALYSIS_DEADLINE_S:g} 秒（{script}）")
        for m in imps:
            if m.split(".")[-1] in ORDER_MODULES:
                _cache_store(script, True, seen, scripts_dir)
                return True
            r = _resolve_mod(m, scripts_dir)
            if r and r not in seen:
                todo.append(r)
    _cache_store(script, False, seen, scripts_dir)
    return False


PY_EXE = re.compile(r"^python(\d+(\.\d+)?)?$")
SHELLS = {"sh", "bash", "zsh"}


def check_python_exec(w: list, cwd: str, depth: int = 0) -> None:
    """w 是一段指令的字詞。找出 python 直譯器真正要跑的腳本（或 -c 程式碼）再判斷。"""
    for i, word in enumerate(w):
        base = os.path.basename(word)
        if base in SHELLS and depth < 3:                 # sh -c '...python3 x.py...'
            for j in range(i + 1, len(w) - 1):
                if w[j] == "-c":
                    sub_cwd = cwd
                    for sub in segments(w[j + 1]):
                        if sub[0] == "cd" and len(sub) > 1:
                            sub_cwd = to_host(sub[1], sub_cwd)
                            continue
                        check_python_exec(sub, sub_cwd, depth + 1)
                    return
        if not PY_EXE.match(base):
            continue
        rest = w[i + 1:]
        k = 0
        target = None
        while k < len(rest):
            a = rest[k]
            if a == "-c" and k + 1 < len(rest):
                code = rest[k + 1]
                mods = "|".join(re.escape(m) for m in sorted(ORDER_MODULES))
                if any(c in code for c in ORDER_CALLS) or re.search(rf"\bimport\s+(?:{mods})\b|\bfrom\s+(?:{mods})\b", code):
                    block("python -c 直接碰下單模組", "下單只能走排程中的執行器；要測試請用 tests/ 的替身")
                return
            if a == "-m" and k + 1 < len(rest):
                rel = os.path.join(*rest[k + 1].split(".")) + ".py"
                dirs = [cwd, os.path.join(cwd, SCRIPTS_DIR)] + ([os.path.join(LIVE, SCRIPTS_DIR)] if LIVE else [])
                target = next((os.path.join(d, rel) for d in dirs if os.path.isfile(os.path.join(d, rel))),
                              os.path.join(cwd, rel))
                break
            if a == "-" or a.startswith("<"):            # 從 stdin（heredoc）讀：不是執行某支腳本
                return
            if a.startswith("-"):
                k += 2 if a in ("-W", "-X") else 1
                continue
            target = to_host(a, cwd)
            break
        if target is None:
            return
        if os.path.isfile(target) and reaches_orders(target):
            block(f"直接執行 {os.path.relpath(target, cwd) if target.startswith(cwd) else target}"
                  "（import 閉包碰得到下單模組）", "不要直接執行；跑它的測試，或請使用者自己執行")
        return


# ── ③ 取出憑證值 ────────────────────────────────────────────────────────────
# 比對整串指令文字（涵蓋 python -c／sh -c／heredoc 裡的寫法），旗標要是獨立的字詞，
# 所以 `find-generic-password -s x`（只驗存在，不印值）與 `grep -rn find-generic-password` 都放行。
KEYCHAIN_READ = re.compile(r"find-(?:generic|internet)-password")
KEYCHAIN_VALUE_FLAG = re.compile(r"(?<![\w-])-[A-Za-z]*[wg](?![\w-])")
KEYCHAIN_DUMP = re.compile(r"dump-keychain")
KEYCHAIN_DUMP_FLAG = re.compile(r"(?<![\w-])-[A-Za-z]*d(?![\w-])")
KEYCHAIN_EXPORT = re.compile(r"\bsecurity\b[^\n;&|]*\bexport\b")
ENV_DOTFILE = re.compile(r"^\.env(\.[\w.-]+)?$")
ENV_PRINTERS = re.compile(r"^(printenv(\s.*)?|env\s*([|>].*)?)$|/proc/[^\s/]+/environ")   # `sh -c 'set -e; …'`、`env FOO=1 cmd` 不算


def check_secret_extraction_text(cmd: str) -> None:
    if KEYCHAIN_READ.search(cmd) and KEYCHAIN_VALUE_FLAG.search(cmd):
        block("從 Keychain 取出密鑰值（find-*-password 帶 -w／-g）", SECRET_HOW)
    if KEYCHAIN_DUMP.search(cmd) and KEYCHAIN_DUMP_FLAG.search(cmd):
        block("dump-keychain -d 會解密列出所有項目", SECRET_HOW)
    if KEYCHAIN_EXPORT.search(cmd):
        block("security export 會匯出 Keychain 項目", SECRET_HOW)


def check_secret_extraction_segment(w: list) -> None:
    exe = os.path.basename(w[0])
    if exe in ("docker", "docker-compose"):
        args = w[1:]
        is_compose = exe == "docker-compose" or (args[:1] == ["compose"])
        if is_compose and "config" in args and "--no-env-resolution" not in args and "-q" not in args and "--quiet" not in args:
            block("docker compose config 會把 env_file 的值展開印出", "加 --no-env-resolution（只看結構），或 -q（只驗證）")
        if args[:1] == ["inspect"]:
            fmt = next((args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-f", "--format")), None)
            fmt = fmt or next((a.split("=", 1)[1] for a in args if a.startswith("--format=")), None)
            if fmt is None or re.search(r"Env|\.Config\b|json", fmt):
                block("docker inspect 會印出容器的環境變數", "加 --format 只取需要的欄位（例如 {{.State.Status}}，不含 Config／Env）")
        if args[:1] in (["exec"], ["run"]) or (is_compose and args[1:2] in (["exec"], ["run"])):
            for a in args:
                if ENV_PRINTERS.search(a):
                    block("在容器裡印環境變數", SECRET_HOW)
                if is_secret(a):
                    block(f"在容器裡讀憑證檔 {a}", SECRET_HOW)


def check_dotenv_out(w: list) -> None:
    """⑧ 設定裡列的指令（例：render-env）的 --out 只能寫成 .env* 檔名；寫到別的檔名就繞過憑證檔名比對。"""
    if not DOTENV_ONLY:
        return
    if os.path.basename(w[0]) not in DOTENV_ONLY and not any(os.path.basename(a) in DOTENV_ONLY for a in w[:3]):
        return
    for i, a in enumerate(w):
        tgt = a.split("=", 1)[1] if a.startswith("--out=") else (w[i + 1] if a == "--out" and i + 1 < len(w) else None)
        if tgt is not None and not ENV_DOTFILE.match(os.path.basename(tgt)):
            block(f"{os.path.basename(w[0])} --out 寫到非 .env 檔名 {tgt}", "輸出檔名必須是 .env*；其他用途請使用者自己執行")


# ── Bash／檔案 ──────────────────────────────────────────────────────────────
# 內建保護：護欄自己的設定與 hook，只有人能改（不能由 guard.json 關掉）
BUILTIN_PROTECTED = re.compile(r"^(\.dev-standard/guard\.json|\.claude/settings(\.local)?\.json|\.claude/hooks(/.*)?)$")


def protected_hit(path: str, root: str, cfg: dict):
    """寫入 path 會不會碰到受保護的路徑；回傳原因或 None。"""
    rel_live = in_live(path)
    if rel_live is not None and PROTECTED_STATE and PROTECTED_STATE.match(rel_live):
        return f"正式樹的帳本 {rel_live}", "帳本只能由排程中的正式腳本寫；要改請寫成提案，由人處理"
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(root)).replace(os.sep, "/")
    if BUILTIN_PROTECTED.match(rel):
        return f"{rel} 是護欄／hook 的設定", "這是 guard 自己的設定，只有人能改：請使用者用 `!` 自己改"
    for pat in cfg.get("protected_paths", []):
        if re.search(pat, rel):
            return f"{rel} 是 R3／正式環境路徑，agent 不動手", "寫成提案或 DD，由人核可或自己改"
    return None


REDIRECT = re.compile(r"""(?:>>?|\btee(?:\s+-a)?)\s*("[^"]*"|'[^']*'|[^\s;&|<>]+)""")


def write_targets(segs: list, cmd: str) -> list:
    """Bash 指令會寫入的目標（盡力而為）：重導／tee（去掉引號）、sed -i、mv、cp 的目的。擋不住任意程式自己寫檔。"""
    out = []
    for tgt in REDIRECT.findall(cmd):
        out.append(tgt[1:-1] if len(tgt) >= 2 and tgt[0] in "\"'" and tgt[-1] == tgt[0] else tgt)
    for w in segs:
        exe = os.path.basename(w[0])
        args = [a for a in w[1:] if not a.startswith("-")]
        if exe == "sed" and any(a == "--in-place" or a.startswith("--in-place=") or re.match(r"^-[A-Za-z]*i", a) for a in w[1:] if a.startswith("-")):
            out += args                                  # 第一個多半是 script；多查無害（要符合受保護 regex 才會擋）
        elif exe == "mv":
            out += args                                  # 來源被搬走、目的被蓋掉，都算
        elif exe == "cp" and args:
            out.append(args[-1])
    return out


# ── ⑨ 私有資料出網 ───────────────────────────────────────────────────────────
def _glob_part(comp: str) -> str:
    return re.escape(comp).replace(r"\*", "[^/]*")


def build_egress(pe: dict):
    """paths 空或沒設 ＝ 關（回 None）。每個目錄產生：
    相對 repo 根目錄的各種後綴（growth/outbox、outbox：cd 進 growth 之後用的寫法）、絕對路徑、以及祖先目錄（tar c growth）。"""
    paths = [p.strip("/") for p in pe.get("paths") or [] if p.strip("/")]
    if not paths:
        return None
    dirs = []
    for full in paths:
        comps = full.split("/")
        parts = [_glob_part(c) for c in comps]
        rels = [re.compile(r"^(?:\./)?" + "/+".join(parts[k:]) + r"(?:/+(.*))?$") for k in range(len(parts))]
        rels.append(re.compile(r"(?:^|/)" + "/+".join(parts) + r"(?:/+(.*))?$"))      # 絕對路徑、$PWD/…
        ancestors = [re.compile(r"^(?:\./)?" + "/+".join(parts[:k]) + r"/*$") for k in range(1, len(parts))]
        dirs.append((full, rels, ancestors))
    return {"clis": set(pe.get("clis") or EXTERNAL_CLIS_DEFAULT), "dirs": dirs, "allow": set(pe.get("allow") or [])}


def split_pipe(group: list) -> list:
    stages, cur = [], []
    for t in group + ["|"]:
        if t in ("|", "|&"):
            cur = strip_wrappers(cur)
            if cur:
                stages.append(cur)
            cur = []
        else:
            cur.append(t)
    return stages


def pipelines(cmd: str) -> list:
    """依 ; && || 換行切成 pipeline，管線（|）與重導向留在同一組，才看得出資料從哪流向哪。"""
    lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|\n")
    lx.whitespace = " \t\r"
    lx.whitespace_split = True
    try:
        toks = list(lx)
    except ValueError:                                   # 引號沒閉合：退回粗切，寧可多看
        toks = cmd.replace("\n", " ; ").split()
    out, cur = [], []
    for t in toks + [";"]:
        if t in OPERATORS and t not in ("|", "|&"):
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    return out


def private_token(tok: str) -> str:
    """token 是私有目錄的資料（或目錄本身）就回傳該 token，否則空字串。
    只看整個 token：含空白的句子、URL 裡提到路徑不算；絕對路徑與 $PWD/… 算。allow 只比對整個檔名。"""
    for cand in {tok, tok.lstrip("@<>"), tok.split("=")[-1].lstrip("@<>")}:
        cand = cand.strip("\"'")
        if not cand or re.search(r"\s", cand) or "://" in cand:
            continue
        for full, rels, ancestors in EGRESS["dirs"]:
            for rx in rels:
                m = rx.search(cand)
                if m:
                    rest = m.group(1)
                    if not rest or (rest not in EGRESS["allow"] and f"{full}/{rest}" not in EGRESS["allow"]):
                        return tok
            if any(a.match(cand) for a in ancestors):
                return tok
    return ""


def inner_commands(group: list) -> list:
    """bash -lc "…"、eval "…"、<<< "…"、$(…)、`…` 裡面的指令字串。"""
    out = []
    for i, t in enumerate(group):
        name = os.path.basename(t)
        if name in SHELLS:
            for j in range(i + 1, len(group)):
                if SHELL_C.match(group[j]) and j + 1 < len(group):
                    out.append(group[j + 1])
                    break
        if name == "eval":
            out.append(" ".join(group[i + 1:]))
        if t == "<<<" and i + 1 < len(group):
            out.append(group[i + 1])
        out += re.findall(r"\$\(([^()]*)\)", t) + re.findall(r"`([^`]*)`", t)
    return out


def check_exfil(cmd: str, depth: int = 0) -> None:
    """私有目錄的內容不准交給會出網的 CLI。只看同一條管線：`ls <私有> && curl …` 沒有資料流相連，不誤擋。
    `cd` 進私有目錄或把私有路徑指給變數後，同一條指令後面的出網 CLI 一律擋。bash -c 的字串遞迴檢查；xargs 後面的指令算在內。"""
    if EGRESS is None:
        return
    tainted = ""
    for group in pipelines(cmd):
        stages = split_pipe(group)
        if depth < 3:
            for inner in inner_commands(group):
                check_exfil(inner, depth + 1)
        ext = next((os.path.basename(t) for st in stages
                    for t in (st[:1] + (st[1:] if os.path.basename(st[0]) == "xargs" else []))
                    if os.path.basename(t) in EGRESS["clis"]), "")
        inner_toks = [t for inner in inner_commands(group) for t in inner.split()]
        hit = next((private_token(t) for t in group + inner_toks if private_token(t)), "")
        if ext and (hit or tainted):
            block(f"{ext} 的指令碰到 {hit or tainted}：設定為私有的目錄（private_egress.paths）內容不准出網",
                  "出網前先把要送的公開文字另存到私有目錄以外，或請使用者用 `!` 自己執行")
        if not ext and hit and (os.path.basename(group[0]) in ("cd", "pushd") or re.match(r"^\w+=", group[0])):
            tainted = hit


def check_bash(cmd: str, cwd: str, root: str, cfg: dict) -> None:
    check_exfil(cmd)
    segs = segments(cmd)
    for item in cfg.get("blocked_commands", []):         # 逐段比對；要精準就在 pattern 用 ^ 錨定
        if any(re.search(item["pattern"], " ".join(w)) for w in segs):
            block(f"危險指令：{item.get('why', item['pattern'])}")
    if cfg.get("secret_extraction", True):
        check_secret_extraction_text(cmd)
    check_trunk(segs, cwd)
    cwd0, cwd_run = cwd, cwd
    for w in segs:
        if w[0] == "cd" and len(w) > 1:                  # cd X && python3 y.py：之後的段落以 X 為 cwd
            cwd_run = to_host(w[1], cwd_run)
            continue
        if ORDER_MODULES:                                # 只有「被 python 直譯器執行」才算 —— 提到檔名不算（#147）
            check_python_exec(w, cwd_run)
        if cfg.get("secret_extraction", True):
            check_secret_extraction_segment(w)
        check_dotenv_out(w)
        exe = os.path.basename(w[0])
        if exe in READ_VERBS:
            paths = [a for a in w[1:] if not a.startswith("-")]
            if exe == "cp":
                paths = paths[:-1]                       # cp 只看來源；cp .env.example .env 是正常設定步驟
            for a in paths:
                if is_secret(a):
                    block(f"用 {exe} 讀憑證檔 {a}", SECRET_HOW)
    # 重導／tee 寫進受保護的路徑
    for tgt in write_targets(segs, cmd):
        hit = protected_hit(to_host(tgt, cwd_run), root, cfg)
        if hit:
            block(f"寫入{hit[0]}", hit[1])
    if LIVE:
        check_git(cmd, cwd0)
    else:
        try:
            new_git_check(cmd, cwd0)                     # 沒有正式樹：只剩 cd 之後的 main commit 判斷
        except SystemExit:
            raise
        except Exception:                                # noqa: BLE001 — check_trunk 已判過 -C 的寫法
            pass


def check_file(tool: str, path: str, root: str, cfg: dict) -> None:
    if not path:
        return
    if is_secret(path):
        block(f"{tool} 憑證檔 {path}", SECRET_HOW)
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        hit = protected_hit(path, root, cfg)
        if hit:
            block(f"{tool} {hit[0]}", hit[1])


def _main() -> int:
    try:
        ev = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0                                         # 讀不到輸入不擋（hook 壞掉不該讓整個 session 停擺）
    if not isinstance(ev, dict):
        return 0
    tool = ev.get("tool_name", "")
    inp = ev.get("tool_input") or {}
    cwd = ev.get("cwd") or os.getcwd()
    root = find_root(cwd)
    cfg = load_config(root)
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    if "__error__" in cfg:
        if tool == "Read":                               # 只放行讀；憑證檔照擋。設定壞了就是壞了，連修它都要人自己來
            configure({})
            check_file(tool, path, root, {})
            return 0
        block(cfg["__error__"], "請使用者用 `!` 自己修好 .dev-standard/guard.json；在那之前除了 Read 所有動作都擋，免得保護靜默失效")
    configure(cfg)
    if tool == "Bash":
        check_bash(inp.get("command", ""), cwd, root, cfg)
    else:
        check_file(tool, path, root, cfg)
    return 0


def main() -> int:
    """任何未預期的例外都 exit 2：Claude Code 的 hook 只有 2 會擋，exit 1／逾時／崩潰都是放行，所以不能讓例外漏出去。"""
    try:
        return _main()
    except SystemExit:
        raise
    except Timeout as e:
        sys.stderr.write(f"⛔ guard：{e}\n   → 腳本的 import 太深或太大，判斷不了就擋；請使用者用 `!` 自己執行\n")
        return 2
    except BaseException as e:                           # noqa: BLE001 — 含 KeyboardInterrupt／RecursionError：一律擋
        sys.stderr.write(f"⛔ guard：內部錯誤（{type(e).__name__}：{e}），保守擋下\n   → 請使用者用 `!` 自己執行，並回報這個錯誤\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
