#!/usr/bin/env python3
"""sync.py — 把 dev-standard 的〈給 agent 的精簡版〉帶進各 repo，並檢查漂移。

來由：investment-advisor 的 scripts/gen_agent_shims.py（單一正本＋產生的區塊＋--check）。
擴充成跨 repo：每個 repo 存一份正本複本（.dev-standard/STANDARD.md）並以 sha256 釘版本，
所以 CI 不用連到 dev-standard 也能檢查。只用標準函式庫，相容 python 3.9。

  python3 .dev-standard/sync.py update --from ~/Work/Projects/dev-standard   複製正本與本工具、釘版本、產生區塊
  python3 .dev-standard/sync.py render                                        依目前的複本產生區塊
  python3 .dev-standard/sync.py check                                         CI 用：複本沒被手改、區塊是最新；回非 0 表示漂移
  python3 .dev-standard/sync.py status --from ~/Work/Projects/dev-standard   本 repo 釘的版本落後上游多少
  python3 <dev-standard>/tools/sync.py report <repo> <repo> …                列出各 repo overlay 段落，標出回填候選（只列不判）

repo 的設定在 .dev-standard/config.json：
  {"agents_file": "AGENTS.md", "shims": ["CLAUDE.md", "GEMINI.md", ".cursorrules"], "create_missing_shims": false}
agents_file 與每個 shim 都會有一段 DEV-STANDARD 區塊，區塊外是 repo 自己的 overlay，本工具不碰。
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

VENDOR_DIR = ".dev-standard"
SRC_RE = re.compile(r"<!-- AGENT-RULES:BEGIN -->\n(.*?)<!-- AGENT-RULES:END -->", re.S)
GEN_RE = re.compile(r"<!-- DEV-STANDARD:BEGIN[^>]*-->\n(.*?)<!-- DEV-STANDARD:END -->\n?", re.S)
HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.M)
DEFAULT_CONFIG = {"agents_file": "AGENTS.md", "shims": []}


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


def cmd_update(repo: Path, src: Path) -> int:
    src = src.expanduser().resolve()
    std = _read(src / "STANDARD.md")
    if not std:
        raise SystemExit(f"{src} 不是 dev-standard（找不到 STANDARD.md）")
    version = _read(src / "VERSION").strip() or "0.0.0"
    vd = repo / VENDOR_DIR
    vd.mkdir(exist_ok=True)
    old = pinned(repo).get("version")
    (vd / "STANDARD.md").write_text(std, encoding="utf-8")
    shutil.copyfile(src / "tools" / "sync.py", vd / "sync.py")
    (vd / "PINNED.json").write_text(json.dumps({"version": version, "sha256": _sha(std)}, indent=2) + "\n",
                                    encoding="utf-8")
    if not (vd / "config.json").exists():
        (vd / "config.json").write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
    print(f"釘版本：{old or '（無）'} → {version}")
    return cmd_render(repo)


def cmd_check(repo: Path) -> int:
    errors = []
    pin = pinned(repo)
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
        return cmd_check(repo)
    if cmd in ("update", "status"):
        src = opt("--from")
        if not src:
            raise SystemExit(f"{cmd} 需要 --from <dev-standard 路徑>")
        return cmd_update(repo, Path(src)) if cmd == "update" else cmd_status(repo, Path(src))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
