"""
Render a trade decision as a short, auditable Telegram card.
把交易決策渲染成簡短、可稽核的 Telegram 卡片。

Why this exists / 為何需要
────────────────────────
The old approval message said the confidence was "6.8/10" and listed the
sub-agent scores, but never the two things you actually need in the ten
seconds before tapping Approve:

  - What is the bar, and how far short did this fall?
  - Which input is responsible for falling short?

Both are arithmetic, so they are computed here rather than asked of an LLM.
The "why" line names the factor with the largest shortfall in *weighted
contribution* — the one whose improvement would most move the composite — not
merely the lowest raw score. A 3.2 at weight 0.20 costs less than a 5.0 at
weight 0.35, and the card should say whichever actually held the trade back.

舊的核准訊息只給「6.8/10」與各代理人分數，卻沒回答按下核准前十秒真正需要的
兩件事：門檻是多少、差多遠？以及是哪一項拖累？兩者都是算術，因此在此計算而
非再問一次 LLM。「為何沒自動執行」指出的是**加權貢獻**缺口最大的因子（改善它
對總分影響最大），而非單純分數最低者——權重 0.20 的 3.2 分，代價低於權重 0.35
的 5.0 分。

Telegram constraints / Telegram 限制
────────────────────────────────────
`telegram_adapter.send_alert` truncates the body at 3900 characters and sends
with `parse_mode=HTML`, escaping the title and converting a markdown subset.
These cards run well under 800 characters; `render_card` enforces a ceiling
anyway so a pathological breakdown cannot get the message silently cut.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Keep clear of telegram_adapter.py's 3900-char truncation.
# 與 telegram_adapter.py 的 3900 字截斷保持距離。
MAX_CARD_CHARS = 3000

_SEPARATOR = "  " + "─" * 26


def render_card(
    *,
    action: str,
    ticker: str,
    score: float,
    threshold: float,
    breakdown: Optional[List[Dict[str, Any]]] = None,
    size_line: Optional[str] = None,
    context_lines: Optional[List[str]] = None,
    auto_executed: bool = False,
    expires_seconds: Optional[int] = None,
    headline_suffix: str = "",
    headline: Optional[str] = None,
) -> str:
    """
    Build the card body. `score` and `threshold` are both on the 0-10 scale.
    產生卡片內容；score 與 threshold 皆為 0-10 級距。

    `breakdown` entries use the shape both compositors emit:
    `{agent, confidence, weight, contribution, key_factor}`. `weight` and
    `contribution` are optional — the entry-side CompositorService does not
    currently emit them, so they are derived or omitted rather than assumed.
    breakdown 使用兩個 compositor 共同的結構；weight 與 contribution 為選填，
    買進側目前未輸出，故採推導或省略而非假設其存在。
    """
    act = str(action).upper()
    lines: List[str] = []

    if auto_executed:
        # `headline` lets a user-approved fill say so — the same renderer
        # serves both, and labelling an approved trade "已自動執行" would
        # misreport who decided it.
        # headline 讓「使用者核准後成交」也能正確標示；同一個渲染器服務兩種情境，
        # 若一律寫「已自動執行」會誤述決策者是誰。
        lines.append(headline or f"✅ 已自動執行：{act} {ticker}{headline_suffix}")
        lines.append("")
        lines.append(f"分數 {score:.1f}/10 ｜ 自動門檻 {threshold:.1f} ｜ 超出 {score - threshold:+.1f}")
    else:
        lines.append(headline or f"🛎️ 需要核准：{act} {ticker}{headline_suffix}")
        lines.append("")

        # A card can need approval despite clearing the bar — the strategy
        # validation gate withholds auto-execution from an unvalidated SELL
        # even at 10/10. Printing "差 -0.5" there is nonsense, and worse, it
        # tells the user the score fell short when it did not.
        # 卡片可能在越過門檻的情況下仍需核准——策略驗證關卡會對未驗證的 SELL 撤銷
        # 自動執行資格，即使分數 10/10。此時印出「差 -0.5」不僅無意義，更會讓使用者
        # 誤以為分數不足。
        if score >= threshold:
            lines.append(f"分數 {score:.1f}/10 ｜ 自動門檻 {threshold:.1f} ｜ 已達標，但仍需你確認")
            reason = None
        else:
            lines.append(f"分數 {score:.1f}/10 ｜ 自動門檻 {threshold:.1f} ｜ 差 {threshold - score:.1f}")
            reason = explain_shortfall(breakdown, score, threshold)

        if reason:
            lines.append("")
            lines.append("為何沒自動執行：")
            lines.append(reason)

    table = _render_breakdown(breakdown, score)
    if table:
        lines.append("")
        lines.append("分數組成：")
        lines.extend(table)

    if size_line:
        lines.append("")
        lines.append(size_line)

    for extra in context_lines or []:
        lines.append(extra)

    if not auto_executed and expires_seconds:
        lines.append("")
        lines.append(f"⏱ {expires_seconds // 60} 分鐘內未回覆即失效")

    body = "\n".join(lines)
    if len(body) > MAX_CARD_CHARS:
        body = body[: MAX_CARD_CHARS - 20].rstrip() + "\n…（已截斷）"
    return body


def explain_shortfall(
    breakdown: Optional[List[Dict[str, Any]]],
    score: float,
    threshold: float,
) -> str:
    """
    Name the factor most responsible for missing the bar.
    指出最該為未達門檻負責的因子。

    Ranks by lost weighted contribution — `(10 - confidence) * weight` — which
    is how much composite each factor is giving up. That is the quantity that
    would have to improve to clear the threshold, so it is the honest answer
    to "why not", unlike simply reporting the smallest raw score.
    以「損失的加權貢獻」排序，即 (10 - 分數) x 權重：這才是要越過門檻必須改善的
    量，比單純回報最低原始分更誠實。
    """
    entries = _normalized(breakdown)
    if not entries:
        return f"綜合分數 {score:.1f} 未達門檻 {threshold:.1f}（無分項資料）"

    worst = max(entries, key=lambda e: (10.0 - e["confidence"]) * e["weight"])
    label = worst["agent"]
    conf = worst["confidence"]
    weight = worst["weight"]
    key_factor = (worst.get("key_factor") or "").strip()

    line = f"{label} {conf:.1f}/10 拉低總分（權重 {weight * 100:.0f}%）"
    if key_factor and key_factor != "N/A":
        line += f" — {key_factor}"
    return line


def _display_width(text: str) -> int:
    """
    Terminal/monospace width, counting CJK as two cells.
    等寬字型下的顯示寬度，CJK 視為兩格。

    `str.ljust` pads by character count, so a label like "集中度" (3 chars,
    6 cells) came out narrower than "Fundamental" and the columns sheared.
    str.ljust 依字元數補齊，「集中度」3 字元卻佔 6 格，導致欄位錯位。
    """
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def _render_breakdown(
    breakdown: Optional[List[Dict[str, Any]]],
    score: float,
) -> List[str]:
    entries = _normalized(breakdown)
    if not entries:
        return []

    total_label = "加權合計"
    label_width = max([_display_width(e["agent"]) for e in entries] + [_display_width(total_label)])

    rows: List[str] = []
    for e in entries:
        row = f"{_pad(e['agent'], label_width)}  {e['confidence']:4.1f} ×{e['weight']:.2f} = {e['contribution']:5.2f}"
        key_factor = (e.get("key_factor") or "").strip()
        if key_factor and key_factor != "N/A":
            row += f"   {key_factor}"
        rows.append(row)

    rows.append("─" * (label_width + 22))
    total = sum(e["contribution"] for e in entries)
    rows.append(f"{_pad(total_label, label_width)}  {'':4} {'':5}   {total:5.2f}")

    # Fenced so telegram_adapter renders it as <pre> (monospace). Without
    # that the alignment computed above is thrown away by the proportional
    # font Telegram uses for ordinary message text.
    # 加上圍欄讓 telegram_adapter 轉成 <pre>（等寬）；否則上面算好的對齊會被
    # Telegram 內文的比例字型破壞。
    return ["```"] + rows + ["```"]


def _normalized(breakdown: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Coerce either compositor's breakdown into one shape with usable weights.
    把兩側 compositor 的 breakdown 正規化成同一結構並補齊權重。

    The exit side supplies `weight` and `contribution`. The entry side
    (CompositorService._build_decision) supplies only agent/confidence/
    key_factor, so weights are looked up from its `agent_weights` table and
    contributions derived. Anything still missing falls back to an equal
    split, which keeps the arithmetic in the card internally consistent even
    if a future caller passes a partial breakdown.
    賣出側已含 weight/contribution；買進側只有 agent/confidence/key_factor，故
    自其 agent_weights 查表並推導貢獻。仍缺者退回等權重，確保卡片內的算術自洽。
    """
    if not breakdown:
        return []

    # Entry-side weights, keyed lowercase (confidence_compositor_service.py).
    entry_weights = {
        "fundamental": 0.35,
        "momentum": 0.25,
        "sentiment": 0.20,
        "risk": 0.20,
    }

    out: List[Dict[str, Any]] = []
    for raw in breakdown:
        if not isinstance(raw, dict):
            continue
        agent = str(raw.get("agent") or raw.get("factor_key") or "?")
        try:
            confidence = float(raw.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue

        weight = raw.get("weight")
        if weight is None:
            weight = entry_weights.get(agent.lower())
        try:
            weight = float(weight) if weight is not None else None
        except (TypeError, ValueError):
            weight = None

        out.append({
            "agent": agent,
            "confidence": confidence,
            "weight": weight,
            "key_factor": raw.get("key_factor"),
        })

    if not out:
        return []

    missing = [e for e in out if e["weight"] is None]
    if missing:
        known = sum(e["weight"] for e in out if e["weight"] is not None)
        share = max(0.0, (1.0 - known)) / len(missing) if known < 1.0 else 1.0 / len(out)
        for e in missing:
            e["weight"] = share

    # Renormalize so the displayed contributions sum to the displayed total
    # even if the supplied weights do not add to 1.0.
    # 重新正規化，讓顯示的貢獻總和與合計一致，即使傳入權重未加總為 1.0。
    total_weight = sum(e["weight"] for e in out)
    if total_weight > 0 and abs(total_weight - 1.0) > 1e-6:
        for e in out:
            e["weight"] = e["weight"] / total_weight

    for e in out:
        e["contribution"] = round(e["confidence"] * e["weight"], 2)

    return out
