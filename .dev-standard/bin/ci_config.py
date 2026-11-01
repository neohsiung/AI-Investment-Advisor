#!/usr/bin/env python3
# 由 dev-standard v0.7.3 產生，請勿手改；要改請改 dev-standard 的 components/ci，再跑 sync.py update
"""讀 .dev-standard/ci.json，決定共同 CI 的 tests 與 lint 怎麼跑，寫進 $GITHUB_OUTPUT。

  python3 .dev-standard/bin/ci_config.py --output "$GITHUB_OUTPUT"

ci.json 可以不存在，那就跟以前一樣：有 tests/*.py 才跑 pytest、有 pyproject.toml 或 ruff.toml 才跑 ruff。
每一節（tests、lint）可以是：
  false                                   關掉：job 照樣出現，印「略過」
  {"run": "<指令>"}                       改跑自己的指令
  {"install": "<指令>", "run": "<指令>"}   先裝相依再跑
其他寫法一律報錯（exit 2）：打錯一個字不能默默退回預設。
rules（規則檔漂移）、secrets（gitleaks）、junk（殘留檔）不讀這份設定，一律會跑。
ci.json 在 .dev-standard/ 底下，pr_checks 內建判 R2：只改它的 PR 不會自動合併。
"""
import argparse
import json
import uuid
import sys
from pathlib import Path

SECTIONS = ("tests", "lint")
KEYS = {"install", "run"}


class ConfigError(Exception):
    pass


def parse(data) -> dict:
    """回 {節: (mode, install, run)}，mode 是 default、custom、off。"""
    if not isinstance(data, dict):
        raise ConfigError("ci.json 最外層要是物件，例如 {\"tests\": false}")
    unknown = sorted(set(data) - set(SECTIONS))
    if unknown:
        raise ConfigError(f"ci.json 有不認得的欄位：{', '.join(unknown)}（只接受 {', '.join(SECTIONS)}）")
    out = {}
    for name in SECTIONS:
        v = data.get(name, None)
        if name not in data:
            out[name] = ("default", "", "")
        elif v is False:
            out[name] = ("off", "", "")
        elif isinstance(v, dict):
            bad = sorted(set(v) - KEYS)
            if bad:
                raise ConfigError(f"ci.json 的 {name} 有不認得的欄位：{', '.join(bad)}（只接受 install、run）")
            run, install = v.get("run"), v.get("install", "")
            if not isinstance(run, str) or not run.strip():
                raise ConfigError(f"ci.json 的 {name}.run 要是非空字串")
            if not isinstance(install, str):
                raise ConfigError(f"ci.json 的 {name}.install 要是字串")
            out[name] = ("custom", install, run)
        else:
            raise ConfigError(f"ci.json 的 {name} 只能是 false 或 {{\"run\": ...}}，現在是 {json.dumps(v)}")
    return out


def load(repo: Path) -> dict:
    p = repo / ".dev-standard" / "ci.json"
    if not p.exists():
        return parse({})
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ConfigError(f".dev-standard/ci.json 不是合法 JSON：{e}")
    except OSError as e:
        raise ConfigError(f".dev-standard/ci.json 讀不到：{e}")
    return parse(data)


def _put(lines: list, key: str, value: str) -> None:
    # 多行值用 heredoc 格式；分隔字串每次隨機，指令內容無法提早結束它、偽造別的 output
    while True:
        delim = f"CI_CONFIG_{uuid.uuid4().hex[:16]}"
        if delim not in value:
            break
    lines += [f"{key}<<{delim}", value, delim]


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--output", required=True, help="通常是 $GITHUB_OUTPUT")
    a = ap.parse_args(argv)
    try:
        cfg = load(Path(a.repo))
    except ConfigError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 2
    lines = []
    for name, (mode, install, run) in cfg.items():
        lines.append(f"{name}_mode={mode}")
        _put(lines, f"{name}_install", install)
        _put(lines, f"{name}_run", run)
        if mode == "off":
            print(f"{name}：略過（.dev-standard/ci.json 設成 false；這個 repo 在自己的 workflow 跑）")
        elif mode == "custom":
            print(f"{name}：照 .dev-standard/ci.json 的指令跑")
        else:
            print(f"{name}：預設（沒有 .dev-standard/ci.json 或沒設這一節）")
    with open(a.output, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
