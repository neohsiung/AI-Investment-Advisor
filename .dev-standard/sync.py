#!/usr/bin/env python3
"""sync.py — 把 dev-standard 的〈給 agent 的精簡版〉帶進各 repo，並檢查漂移。

來由：investment-advisor 的 scripts/gen_agent_shims.py（單一正本＋產生的區塊＋--check）。
擴充成跨 repo：每個 repo 存一份正本複本（.dev-standard/STANDARD.md）並以 sha256 釘版本，
所以 CI 不用連到 dev-standard 也能檢查。只用標準函式庫，相容 python 3.9。

  python3 .dev-standard/sync.py update --from $DEV_STANDARD [--adopt]
                                                                              複製正本與本工具、釘版本、產生區塊。目的地已有「沒被釘過、內容不同」的檔時整個中止、什麼都不寫，
                                                                              列出檔案；確認要蓋掉才加 --adopt（會先把原檔備份到 .dev-standard/backup/<日期>/，備份不要 commit）
  python3 .dev-standard/sync.py render                                        依目前的複本產生區塊
  python3 .dev-standard/sync.py check [--no-local]                            CI 用：複本沒被手改、區塊是最新、元件有掛上；回非 0 表示漂移
                                                                              （--no-local：不看 core.hooksPath——它是本機狀態，CI 新 clone 一定是空的）
  python3 .dev-standard/sync.py wire [--dry-run] [--force-hookspath]                              把已裝的元件掛上：core.hooksPath、.claude/settings.json 的 hooks（冪等，先備份 .bak）
  python3 .dev-standard/sync.py status --from $DEV_STANDARD   本 repo 釘的版本落後上游多少
  python3 <dev-standard>/tools/sync.py report <repo> <repo> …                列出各 repo overlay 段落，標出回填候選（只列不判）

repo 的設定在 .dev-standard/config.json：
  {"agents_file": "AGENTS.md", "shims": ["CLAUDE.md", "GEMINI.md", ".cursorrules"], "create_missing_shims": false}
agents_file 與每個 shim 都會有一段 DEV-STANDARD 區塊，區塊外是 repo 自己的 overlay，本工具不碰。

元件（選用）：config.json 加 "components": ["guard", "hooks", …]，update 會把 dev-standard 的
components/<名>/manifest.json 列的檔複製到目的地、檔頭寫「由 dev-standard vX 產生」、每檔 sha256 釘進 PINNED.json
的 "components"。check 擋：被手改、缺檔、config 與 pin 對不上、元件裝了卻沒掛上（「未掛載」，見 wire）。manifest 的 "config" 列的是 repo 自己的設定檔
（例：.dev-standard/guard.json）：缺才從範例建，之後 update 不碰、check 不管。沒有 "components" 的 repo 行為不變。
"""
from __future__ import annotations

import datetime
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VENDOR_DIR = ".dev-standard"
SRC_RE = re.compile(r"<!-- AGENT-RULES:BEGIN -->\n(.*?)<!-- AGENT-RULES:END -->", re.S)
GEN_RE = re.compile(r"<!-- DEV-STANDARD:BEGIN[^>]*-->\n(.*?)<!-- DEV-STANDARD:END -->\n?", re.S)
HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.M)
DEFAULT_CONFIG = {"agents_file": "AGENTS.md", "shims": []}
COMP_DIR = "components"
HASH_COMMENT_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".toml"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def find_repo(start: Path) -> Path:
    d = start.resolve()
    for cand in [d, *d.parents]:
        if (cand / VENDOR_DIR / "config.json").exists() or (cand / ".git").exists():
            return cand
    return d


def load_config(repo: Path) -> dict:
    p = repo / VENDOR_DIR / "config.json"
    cfg = dict(DEFAULT_CONFIG)
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _safe_rel(rel: str, what: str) -> str:
    parts = rel.split("/")
    if not rel or rel.startswith("/") or ".." in parts:
        raise SystemExit(f"manifest 的 {what}「{rel}」必須是不含 .. 的相對路徑")
    return rel


def load_manifest(src: Path, name: str) -> tuple:
    """回傳 (元件目錄, manifest)。名稱不存在或 manifest 壞掉就大聲失敗。"""
    d = src / COMP_DIR / name
    mp = d / "manifest.json"
    if not mp.is_file():
        known = sorted(p.parent.name for p in (src / COMP_DIR).glob("*/manifest.json"))
        raise SystemExit(f"未知的元件「{name}」：{mp} 不存在（上游有的元件：{', '.join(known) or '無'}）")
    try:
        man = json.loads(mp.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"{mp} 不是合法 JSON：{e}")
    if not isinstance(man.get("files"), list) or not man["files"]:
        raise SystemExit(f"{mp} 缺 files 清單")
    return d, man


def add_header(text: str, dst: str, name: str, version: str) -> str:
    """在檔案開頭（shebang、frontmatter 之後）寫一行「由 dev-standard 產生」。不確定語法的檔不寫。"""
    msg = f"由 dev-standard v{version} 產生，請勿手改；要改請改 dev-standard 的 components/{name}，再跑 sync.py update"
    suffix = Path(dst).suffix.lower()
    if text.startswith("#!"):
        first, _, rest = text.partition("\n")
        return f"{first}\n# {msg}\n{rest}"
    if suffix in HASH_COMMENT_SUFFIXES:
        return f"# {msg}\n{text}"
    if suffix == ".md":
        c = f"<!-- {msg} -->\n"
        if text.startswith("---\n"):
            i = text.find("\n---\n", 4)
            if i != -1:
                j = i + len("\n---\n")
                return text[:j] + c + text[j:]
        return c + text
    return text


def plan_components(src: Path, names: list, version: str) -> tuple:
    """先把所有元件讀完驗完，回傳 (檔案清單, 設定檔清單)；任何一個有問題就整個失敗，不留半套。"""
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise SystemExit("config.json 的 components 必須是字串清單")
    files, configs, seen = [], [], {}
    for name in names:
        d, man = load_manifest(src, name)
        for f in man["files"]:
            fsrc, dst = f.get("src", ""), _safe_rel(f.get("dst", ""), "dst")
            sp = d / _safe_rel(fsrc, "src")
            if not sp.is_file():
                raise SystemExit(f"元件「{name}」的來源檔不存在：{sp}")
            if dst in seen:
                raise SystemExit(f"元件「{name}」與「{seen[dst]}」都要寫到 {dst}")
            seen[dst] = name
            raw = sp.read_bytes()
            try:
                body = add_header(raw.decode("utf-8"), dst, name, version).encode("utf-8")
            except UnicodeDecodeError:
                body = raw                                     # 二進位檔不寫檔頭
            files.append((name, dst, body, int(str(f.get("mode", "644")), 8)))
        for c in man.get("config", []):
            ex = d / _safe_rel(c.get("example", ""), "example")
            if not ex.is_file():
                raise SystemExit(f"元件「{name}」的設定範例不存在：{ex}")
            configs.append((_safe_rel(c.get("dst", ""), "config dst"), ex.read_bytes()))
    return files, configs


def write_components(repo: Path, files: list, configs: list, old_pin: dict) -> dict:
    """寫檔、建缺的設定檔、清掉上游已拿掉且沒被改過的舊檔。回傳要釘的 {元件: {files: {dst: sha}}}。"""
    pins: dict = {}
    for name, dst, body, mode in files:
        p = repo / dst
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        p.chmod(mode)
        pins.setdefault(name, {"files": {}})["files"][dst] = _sha_bytes(body)
    for dst, body in configs:
        p = repo / dst
        if not p.exists():                                     # repo 自己的設定：只建不覆蓋
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
    new_dsts = {dst for _n, dst, _b, _m in files}
    for name, info in old_pin.get("components", {}).items():
        for dst, sha in info.get("files", {}).items():
            if dst in new_dsts:
                continue
            _safe_rel(dst, "PINNED 的檔案路徑")                 # PINNED.json 是 repo 裡的檔，不可信：不准刪到 repo 外面
            p = repo / dst
            if not p.exists():
                continue
            if _sha_bytes(p.read_bytes()) == sha:
                p.unlink()
            else:
                print(f"提醒：上游已不再提供 {dst}（元件 {name}），但本地被改過，沒有刪")
    return pins


def unpinned_conflicts(repo: Path, files: list, old_pin: dict) -> list:
    """會蓋掉「不是上次 update 寫的、內容也不同」的既有檔的 dst 清單（使用者自己的檔，不能靜默覆蓋）。"""
    pinned_dsts = {d for info in old_pin.get("components", {}).values() for d in info.get("files", {})}
    out = []
    for _name, dst, body, _mode in files:
        p = repo / dst
        if dst not in pinned_dsts and p.is_file() and p.read_bytes() != body:
            out.append(dst)
    return out


def backup_files(repo: Path, dsts: list) -> Path:
    """把 dsts 原樣複製到 .dev-standard/backup/<日期>/<dst>。名稱不加 .bak／.pre-*，免得被 pre-commit 的殘留檔檢查誤認。"""
    bd = repo / VENDOR_DIR / "backup" / datetime.date.today().strftime("%Y%m%d")
    for dst in dsts:
        t = bd / dst
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / dst, t)
    return bd


def agent_block(standard_text: str) -> str:
    m = SRC_RE.search(standard_text)
    if not m:
        raise SystemExit("STANDARD.md 沒有 <!-- AGENT-RULES:BEGIN --> … <!-- AGENT-RULES:END --> 區塊")
    return m.group(1).strip() + "\n"


def render_block(block: str, version: str) -> str:
    return (f"<!-- DEV-STANDARD:BEGIN v{version} -->\n"
            f"<!-- 由 dev-standard 的 tools/sync.py 產生。要改規則請改 dev-standard 的 STANDARD.md 再 update；"
            f"本 repo 自己的差異寫在這個區塊外。 -->\n{block}<!-- DEV-STANDARD:END -->\n")


def with_block(text: str, gen: str) -> str:
    if GEN_RE.search(text):
        return GEN_RE.sub(lambda _m: gen, text, count=1)
    # 沒有區塊：放在第一個 H1 之後（沒有 H1 就放最前面）
    m = re.search(r"^# .*\n", text, re.M)
    if m:
        i = m.end()
        return text[:i] + "\n" + gen + "\n" + text[i:]
    return gen + ("\n" + text if text else "")


def overlay_headings(text: str) -> list:
    outside = GEN_RE.sub("", text)
    return [h for _lvl, h in HEADING_RE.findall(outside)]


def pinned(repo: Path) -> dict:
    p = repo / VENDOR_DIR / "PINNED.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def targets(repo: Path, cfg: dict) -> list:
    return [cfg["agents_file"], *cfg.get("shims", [])]


def compute(repo: Path) -> tuple:
    """回傳 (每個目標檔的新內容, 版本)。不寫檔。"""
    cfg = load_config(repo)
    std = _read(repo / VENDOR_DIR / "STANDARD.md")
    if not std:
        raise SystemExit(f"{repo / VENDOR_DIR / 'STANDARD.md'} 不存在：先跑 update --from <dev-standard>")
    version = pinned(repo).get("version", "0.0.0")
    gen = render_block(agent_block(std), version)
    out = {}
    for rel in targets(repo, cfg):
        # shim 不存在就跳過（有些 repo 把各家規則檔 gitignore，新 clone 上沒有）；
        # 要讓 render 建出來就在 config 設 create_missing_shims: true。agents_file 一定處理。
        if rel != cfg["agents_file"] and not (repo / rel).exists() and not cfg.get("create_missing_shims"):
            continue
        cur = _read(repo / rel)
        out[rel] = (cur, with_block(cur, gen))
    return out, version


def cmd_render(repo: Path) -> int:
    out, version = compute(repo)
    changed = []
    for rel, (cur, new) in out.items():
        if new != cur:
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(new, encoding="utf-8")
            changed.append(rel)
    print(f"dev-standard v{version}：" + ("已是最新" if not changed else "已更新 " + ", ".join(changed)))
    return 0


def cmd_update(repo: Path, src: Path, adopt: bool = False) -> int:
    src = src.expanduser().resolve()
    std = _read(src / "STANDARD.md")
    if not std:
        raise SystemExit(f"{src} 不是 dev-standard（找不到 STANDARD.md）")
    # 正在跑的這份跟上游不同（例：repo 裡的舊 copy），就交給上游那份跑。
    # 否則這一輪用舊邏輯，新功能（例：元件）要再跑第二次才生效，而輸出看起來像已經完成。
    upstream = src / "tools" / "sync.py"
    me = Path(__file__).resolve()
    if upstream.is_file() and me != upstream.resolve() and _read(me) != _read(upstream):
        print(f"這份 sync.py 與上游不同，改用上游 {upstream} 執行 update")
        args = [sys.executable, str(upstream), "update", "--from", str(src)] + (["--adopt"] if adopt else [])
        return subprocess.run(args, cwd=str(repo)).returncode
    version = _read(src / "VERSION").strip() or "0.0.0"
    vd = repo / VENDOR_DIR
    old_pin = pinned(repo)
    # 先驗證所有元件再動手：未知元件、壞 manifest 不會留下寫一半的狀態
    files, configs = plan_components(src, load_config(repo).get("components", []), version)
    for info in old_pin.get("components", {}).values():       # 舊 pin 的路徑不可信：先驗，免得刪到 repo 外面
        for dst in info.get("files", {}):
            _safe_rel(dst, "PINNED 的檔案路徑")
    conflicts = unpinned_conflicts(repo, files, old_pin)
    if conflicts and not adopt:
        print("中止，沒有寫任何檔：以下檔案已存在、不是 dev-standard 上次寫的，內容也和新版不同；蓋掉會丟掉你的內容：", file=sys.stderr)
        for c in conflicts:
            print(f"  {c}", file=sys.stderr)
        print("確認要由 dev-standard 接手這些檔，就加 --adopt 重跑（原檔會先備份到 .dev-standard/backup/<日期>/）；"
              "要保留自己的版本，就從 config.json 的 components 拿掉對應元件。", file=sys.stderr)
        return 1
    if conflicts:
        bd = backup_files(repo, conflicts)
        print(f"--adopt：{len(conflicts)} 個檔已備份到 {bd.relative_to(repo)}（不要 commit 它）：" + "、".join(conflicts))
    vd.mkdir(exist_ok=True)
    old = old_pin.get("version")
    (vd / "STANDARD.md").write_text(std, encoding="utf-8")
    shutil.copyfile(src / "tools" / "sync.py", vd / "sync.py")
    pin = {"version": version, "sha256": _sha(std)}
    comp_pins = write_components(repo, files, configs, old_pin)
    if comp_pins:
        pin["components"] = comp_pins
    (vd / "PINNED.json").write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
    if not (vd / "config.json").exists():
        (vd / "config.json").write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
    print(f"釘版本：{old or '（無）'} → {version}")
    rc = cmd_render(repo)
    if any(n in SETTINGS_WIRES or n == "hooks" for n in installed(repo)):
        print("提醒：hooks／guard／green-gate 要掛上才會生效，跑 python3 .dev-standard/sync.py wire"
              "（--dry-run 先看會改什麼）；sync.py check 會檢查有沒有掛")
    return rc


def check_components(repo: Path, pin: dict) -> list:
    """元件檔：缺檔、被手改、config 與 PINNED 對不上（沒跑 update）。"""
    errors = []
    want = load_config(repo).get("components", [])
    pc = pin.get("components", {})
    for n in want:
        if n not in pc:
            errors.append(f"元件「{n}」在 config.json 但 PINNED 沒釘：跑 update --from <dev-standard>")
    for n in pc:
        if n not in want:
            errors.append(f"PINNED 還釘著元件「{n}」，但 config.json 已移除：跑 update 清掉")
    for n, info in pc.items():
        for dst, sha in info.get("files", {}).items():
            p = repo / dst
            if not p.exists():
                errors.append(f"元件檔缺漏：{dst}（元件 {n}），跑 update 補回")
            elif _sha_bytes(p.read_bytes()) != sha:
                errors.append(f"元件檔被手改：{dst}（元件 {n}）。要改請改 dev-standard 的 components/{n}，再 update")
    return errors


HOOKS_PATH = ".githooks"
SETTINGS_REL = ".claude/settings.json"
GUARD_MATCHER = "Bash|Edit|Write|MultiEdit|NotebookEdit|Read"
# 元件 → (settings.json 的事件, 要掛的 entry, 用來辨識「已經掛了」的檔名)。順序固定，輸出才穩定。
SETTINGS_WIRES = {
    "guard": ("PreToolUse", {"matcher": GUARD_MATCHER, "hooks": [
        {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py"', "timeout": 30}]},
              ".claude/hooks/guard.py"),
    "green-gate": ("Stop", {"hooks": [
        {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/green_gate.py"', "timeout": 960}]},
                   ".claude/hooks/green_gate.py"),
}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _load_settings(repo: Path) -> dict:
    """settings.json 不存在回 {}；壞掉就大聲失敗，絕不覆蓋使用者的檔。"""
    p = repo / SETTINGS_REL
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"{p} 不是合法 JSON，不動它：{e}")
    if not isinstance(data, dict):
        raise SystemExit(f"{p} 最外層必須是物件，不動它")
    return data


def _event_groups(data: dict, event: str) -> list:
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict) or not isinstance(hooks.get(event, []), list):
        raise SystemExit(f"{SETTINGS_REL} 的 hooks.{event} 不是預期的形狀（hooks 要是物件、{event} 要是清單），不動它")
    return hooks.get(event, [])


def _has_hook(groups: list, marker: str) -> bool:
    for g in groups:
        for h in (g.get("hooks", []) if isinstance(g, dict) else []):
            if isinstance(h, dict) and marker in str(h.get("command", "")):
                return True
    return False


def merge_settings(data: dict, names: list) -> dict:
    """把 names 列的元件需要的 hook entry 併進 data：既有的 entry 與順序都保留，已經掛了的不重複，新的接在該事件的最後。"""
    out = json.loads(json.dumps(data))
    for name in names:
        if name not in SETTINGS_WIRES:
            continue
        event, entry, marker = SETTINGS_WIRES[name]
        if _has_hook(_event_groups(out, event), marker):
            continue
        out.setdefault("hooks", {}).setdefault(event, []).append(json.loads(json.dumps(entry)))
    return out


def installed(repo: Path) -> list:
    return [n for n in load_config(repo).get("components", []) if isinstance(n, str)]


def wiring_gaps(repo: Path, local: bool = True) -> list:
    """已安裝但沒掛上的東西，每項一行。local=False 不看 core.hooksPath（它是本機狀態，CI 的新 clone 一定是空的）。"""
    names = installed(repo)
    gaps = []
    if "denylist-gate" in names and "hooks" not in names:
        gaps.append("未掛載：denylist-gate 需要 hooks 元件（它掛在 .githooks/pre-commit.d/，由 hooks 的 pre-commit 串起來）；config.json 的 components 加上 hooks")
    if "hooks" in names and local:
        r = _git(repo, "config", "--local", "--get", "core.hooksPath")
        cur = r.stdout.strip()
        if cur != HOOKS_PATH and not (cur and (repo / cur).is_dir() and (repo / cur).resolve() == (repo / HOOKS_PATH).resolve()):
            gaps.append(f"未掛載：core.hooksPath（現值：{cur or '未設'}，應為 {HOOKS_PATH}）；跑 sync.py wire")
    hook = repo / HOOKS_PATH / "pre-commit"
    if "hooks" in names and (repo / ".pre-commit-config.yaml").exists() and hook.exists() \
            and FRAMEWORK_MARK not in hook.read_text(encoding="utf-8", errors="replace"):
        gaps.append("未串接：repo 有 .pre-commit-config.yaml，但 .githooks/pre-commit 是舊 copy，不會跑 pre-commit framework"
                    "（密鑰掃描無聲停止）；跑 sync.py update --from <dev-standard>")
    data = _load_settings(repo)
    for name in names:
        if name in SETTINGS_WIRES:
            event, _entry, marker = SETTINGS_WIRES[name]
            if not _has_hook(_event_groups(data, event), marker):
                gaps.append(f"未掛載：{SETTINGS_REL} 的 hooks.{event} 沒有 {marker}（元件 {name}）；跑 sync.py wire")
    return gaps


# pre-commit framework 產生的 shim 固定有這一行。用整行比對，不用網址子字串（CodeQL 會誤判成網址驗證）
PRECOMMIT_SHIM_RE = re.compile(r"^# File generated by pre-commit: https://pre-commit\.com", re.M)
FRAMEWORK_MARK = "DEV_PRECOMMIT_FRAMEWORK_SKIP"   # hooks 元件的 pre-commit 有串接 pre-commit framework 的記號；舊 copy 沒有


def foreign_git_hooks(repo: Path) -> list:
    """$(git rev-parse --git-common-dir)/hooks 裡不是 .sample、也不是 hooks 元件會串接的檔。
    core.hooksPath 一設，git 就不再執行這些檔：不處理就是無聲停用。
    唯一例外：repo 有 .pre-commit-config.yaml 時，pre-commit framework 自己裝的 pre-commit shim（元件的 pre-commit 會串接它）。"""
    r = _git(repo, "rev-parse", "--git-common-dir")
    if r.returncode != 0:
        return []
    d = (repo / r.stdout.strip() / "hooks").resolve()
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.name.endswith(".sample"):
            continue
        chained = repo / HOOKS_PATH / "pre-commit"     # 豁免只在元件的 pre-commit 真的會串接 framework 時成立
        if f.name == "pre-commit" and (repo / ".pre-commit-config.yaml").exists() \
                and PRECOMMIT_SHIM_RE.search(f.read_text(encoding="utf-8", errors="replace")) \
                and chained.is_file() and FRAMEWORK_MARK in chained.read_text(encoding="utf-8", errors="replace"):
            continue
        out.append(f.name)
    return out


def cmd_wire(repo: Path, dry_run: bool = False, force_hookspath: bool = False) -> int:
    """把已安裝的元件掛進 git 與 .claude/settings.json。冪等：跑兩次跟跑一次一樣。不刪使用者原有的任何 entry。"""
    names = installed(repo)
    problems = []
    if "hooks" in names:
        cur = _git(repo, "config", "--local", "--get", "core.hooksPath").stdout.strip()
        if cur == HOOKS_PATH:
            print(f"core.hooksPath 已是 {HOOKS_PATH}")
        elif cur:
            problems.append(f"core.hooksPath 已設成別的值（{cur}），不覆蓋；確認後自行改成 {HOOKS_PATH}")
        elif (foreign := foreign_git_hooks(repo)) and not force_hookspath:
            problems.append("不設 core.hooksPath：設了之後 git 不再執行 .git/hooks/ 裡這些 hook，等於無聲停用："
                            + "、".join(foreign) + "。確認它們已由別的方式接手（或不需要）後，加 --force-hookspath 再跑 wire")
        elif dry_run:
            print(f"[dry-run] 會設定 core.hooksPath = {HOOKS_PATH}")
        else:
            r = _git(repo, "config", "--local", "core.hooksPath", HOOKS_PATH)
            if r.returncode != 0:
                problems.append(f"設定 core.hooksPath 失敗：{r.stderr.strip() or '不是 git repo？'}")
            else:
                print(f"已設定 core.hooksPath = {HOOKS_PATH}")
    p = repo / SETTINGS_REL
    cur_data = _load_settings(repo)
    new_data = merge_settings(cur_data, names)
    if new_data == cur_data:
        print(f"{SETTINGS_REL} 已掛好（沒有要改的）")
    else:
        old_text = p.read_text(encoding="utf-8") if p.exists() else ""
        new_text = json.dumps(new_data, indent=2, ensure_ascii=False) + "\n"
        if dry_run:
            sys.stdout.writelines(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True),
                                                       f"a/{SETTINGS_REL}", f"b/{SETTINGS_REL}"))
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists():
                shutil.copyfile(p, p.with_name(p.name + ".bak"))
            p.write_text(new_text, encoding="utf-8")
            print(f"已更新 {SETTINGS_REL}（原檔備份在 {SETTINGS_REL}.bak）")
    for msg in problems:
        print(f"未掛載：{msg}")
    return 1 if problems else 0


def cmd_check(repo: Path, local: bool = True) -> int:
    errors = []
    pin = pinned(repo)
    # 先講檢查的是哪個 repo、釘哪一版：在別的 worktree 或目錄跑時，「一致」不會被讀成在講別的 repo
    print(f"檢查 {repo.resolve()}（釘 v{pin.get('version') if pin else '無'}）")
    std = _read(repo / VENDOR_DIR / "STANDARD.md")
    if not pin or not std:
        errors.append("缺 .dev-standard/PINNED.json 或 STANDARD.md：先跑 update --from <dev-standard>")
    elif _sha(std) != pin.get("sha256"):
        errors.append(".dev-standard/STANDARD.md 被手改過（sha 與 PINNED 不符）。規則要改在 dev-standard，再 update")
    if not errors:
        out, _v = compute(repo)
        stale = [rel for rel, (cur, new) in out.items() if cur != new]
        if stale:
            errors.append("區塊過期或被手改：" + ", ".join(stale) + "（跑 sync.py render）")
        std_heads = set(overlay_headings(_read(repo / VENDOR_DIR / "STANDARD.md")))
        cfg = load_config(repo)
        dup = [h for h in overlay_headings(_read(repo / cfg["agents_file"])) if h in std_heads]
        for h in dup:   # 提醒不擋：是不是漂移由人判斷
            print(f"提醒：overlay 有跟正本同名的段落「{h}」，可能是漂移或該回填")
    errors += check_components(repo, pin)
    errors += wiring_gaps(repo, local)
    if errors:
        print("dev-standard 檢查失敗：\n- " + "\n- ".join(errors))
        return 1
    print(f"dev-standard v{pin.get('version')}：一致")
    return 0


def cmd_status(repo: Path, src: Path) -> int:
    src = src.expanduser().resolve()
    up_v = _read(src / "VERSION").strip()
    up_sha = _sha(_read(src / "STANDARD.md"))
    pin = pinned(repo)
    if pin.get("sha256") == up_sha:
        print(f"跟上游一致（v{up_v}）")
        return 0
    print(f"落後上游：本 repo v{pin.get('version')}，上游 v{up_v}。跑 update --from {src} 並看 CHANGELOG")
    return 0


def cmd_report(repos: list) -> int:
    seen: dict = {}
    print("# overlay 段落（區塊外，repo 自己的差異）\n")
    for r in repos:
        repo = Path(r).expanduser().resolve()
        cfg = load_config(repo)
        heads = overlay_headings(_read(repo / cfg["agents_file"]))
        print(f"## {repo.name}（{cfg['agents_file']}）")
        for h in heads:
            print(f"- {h}")
            seen.setdefault(h, []).append(repo.name)
        print()
    shared = {h: rs for h, rs in seen.items() if len(set(rs)) > 1}
    print("# 回填候選：兩個以上 repo 都有的段落標題（只列不判）\n")
    for h, rs in sorted(shared.items()):
        print(f"- {h}：{', '.join(sorted(set(rs)))}")
    if not shared:
        print("（無）")
    return 0


def main(argv: list) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "report":
        return cmd_report(rest or ["."])

    def opt(name: str):
        if name in rest:
            i = rest.index(name)
            return rest[i + 1] if i + 1 < len(rest) else None
        return None

    repo = Path(opt("--repo") or ".")
    repo = find_repo(repo)
    if cmd == "render":
        return cmd_render(repo)
    if cmd == "check":
        return cmd_check(repo, local="--no-local" not in rest)
    if cmd == "wire":
        return cmd_wire(repo, dry_run="--dry-run" in rest, force_hookspath="--force-hookspath" in rest)
    if cmd in ("update", "status"):
        src = opt("--from")
        if not src:
            raise SystemExit(f"{cmd} 需要 --from <dev-standard 路徑>")
        return cmd_update(repo, Path(src), adopt="--adopt" in rest) if cmd == "update" else cmd_status(repo, Path(src))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
