#!/usr/bin/env python3
# 由 dev-standard v0.6.2 產生，請勿手改；要改請改 dev-standard 的 components/green-gate，再跑 sync.py update
"""green_gate.py — Claude Code Stop hook：綠燈才算完成（來由：hermes DD-2026-1009-claude-loop-workflow；dev-standard §4）

loop 的本體是「一個會失敗的檢查」。「看起來好」「模型說有把握」「沒報錯」都不是檢查。
所以每個任務**先寫** `.claude-task/green.sh`（可執行的驗收條件，exit 0 = 綠），再寫碼。
agent 想結束這一回合時，這支跑 green.sh：

  綠      ⇒ 放行（attempts 歸零）
  紅      ⇒ exit 2：把 green.sh 的輸出尾端回給 agent，要求**只修失敗的那個單元**
  連 MAX_ATTEMPTS 次紅 ⇒ 放行停止，並以 systemMessage 告訴**使用者**「計畫可能錯了」
           （同一單元修三次不好，問題在計畫，loop 看不見計畫；systemMessage 只給人看，agent 看不到）
  計數綁 session_id：上一個 session 留下的計數不會讓新 session 的第一次紅就放行
  green.sh 被改過 ⇒ 擋一次，要求 agent 在回覆裡跟使用者說明改了什麼驗收條件
           （改弱驗收條件＝把紅燈的開關交給被驗的人）
  沒有 green.sh ⇒ 放行（不是每個 session 都是開發任務）

green.sh 的慣例輸出（給 agent 看的單元式回報；不是強制）：
  UNIT: <哪一個單元>  VERDICT: red  REASON: <哪條檢查>  EVIDENCE: <檔案:行／數字>  SCOPE: <只准動哪些檔>

只用標準函式庫、相容 macOS 內建 python 3.9。
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys

TASK_DIR = ".claude-task"
MAX_ATTEMPTS = 3
GREEN_TIMEOUT_S = int(os.environ.get("GREEN_GATE_TIMEOUT_S", "900"))   # env 只給測試縮短
TAIL_LINES = 40


def find_root(cwd: str) -> str | None:
    d = os.path.realpath(cwd or ".")
    while True:
        if os.path.isfile(os.path.join(d, TASK_DIR, "green.sh")):
            return d
        if os.path.exists(os.path.join(d, ".git")) or d == os.path.dirname(d):
            return None
        d = os.path.dirname(d)


def _read(path: str, default: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return default


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def feedback(msg: str) -> None:
    sys.stderr.write(f"🔴 green_gate：{msg}\n（dev-standard §4）\n")
    sys.exit(2)


def main() -> int:
    try:
        ev = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0                                                  # 壞輸入不擋（hermes_guard 同一原則）
    root = find_root(ev.get("cwd") or os.getcwd())
    if root is None:
        return 0
    td = os.path.join(root, TASK_DIR)
    green = os.path.join(td, "green.sh")
    with open(green, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()[:12]
    sid = str(ev.get("session_id") or "")
    att_path = os.path.join(td, "attempts")
    old_sha = _read(os.path.join(td, "green.sha"))
    _write(os.path.join(td, "green.sha"), sha)
    if old_sha and old_sha != sha:
        _write(att_path, json.dumps({"session": sid, "n": 0}))
        feedback(f"驗收條件 green.sh 被改過（{old_sha} → {sha}）。在回覆裡跟使用者說明改了哪條檢查、為什麼；"
                 f"改弱驗收條件要使用者同意。說明完再結束。")
    p = subprocess.Popen(["bash", green], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         start_new_session=True)
    try:
        out, _ = p.communicate(timeout=GREEN_TIMEOUT_S)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)                      # 殺整個行程組：green.sh 底下的 docker／pytest 不留孤兒
        except ProcessLookupError:
            pass
        p.communicate()
        rc, out = 124, f"green.sh 超過 {GREEN_TIMEOUT_S}s —— 逾時是失敗不是跳過"
    out = out or ""
    if rc == 0:
        _write(att_path, json.dumps({"session": sid, "n": 0}))
        return 0
    try:
        prev = json.loads(_read(att_path, "{}") or "{}")
    except ValueError:
        prev = {}
    n = (int(prev.get("n") or 0) if isinstance(prev, dict) and prev.get("session") == sid else 0) + 1
    _write(att_path, json.dumps({"session": sid, "n": n}))
    tail = "\n".join(out.strip().splitlines()[-TAIL_LINES:])
    if n >= MAX_ATTEMPTS:
        _write(att_path, json.dumps({"session": sid, "n": 0}))
        print(json.dumps({"systemMessage": f"green_gate：green.sh 連續 {n} 次紅，放行停止。"
                                           f"同一單元修 {n} 次不好 ⇒ 計畫可能錯了，請檢視再決定。"},
                         ensure_ascii=False))
        return 0
    feedback(f"驗收未過（第 {n}/{MAX_ATTEMPTS} 次，rc={rc}）。只修下面失敗的單元，不要動其他已經綠的部分；"
             f"修完再結束。\n--- green.sh 輸出尾端 ---\n{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
