"""
Tests for the Telegram decision card.
Telegram 決策卡的測試。

Context (2026-08-11): the card is the entire interface for a trade the system
will not execute on its own. If it does not state the bar, the shortfall, and
which input caused it, the only available response is to trust the number —
which defeats the point of asking.

2026-08-11：對於系統不會自行執行的交易，這張卡片就是全部的介面。若未說明門檻、
差距與肇因，使用者能做的只有相信那個數字，那就失去了「詢問」的意義。
"""
from src.services.decision_card import MAX_CARD_CHARS, explain_shortfall, render_card

_ENTRY_BREAKDOWN = [
    {"agent": "Fundamental", "confidence": 8.1, "key_factor": "PE 低於同業"},
    {"agent": "Momentum", "confidence": 7.5, "key_factor": "站上 20MA"},
    {"agent": "Sentiment", "confidence": 6.0, "key_factor": "新聞中性"},
    {"agent": "Risk", "confidence": 3.2, "key_factor": "財報前 2 日"},
]

_EXIT_BREAKDOWN = [
    {"agent": "未實現損益", "confidence": 4.0, "weight": 0.30, "key_factor": "+12.4%"},
    {"agent": "集中度", "confidence": 9.0, "weight": 0.25, "key_factor": "26% > 25%"},
    {"agent": "動能反轉", "confidence": 3.2, "weight": 0.25, "key_factor": "仍在 20MA 上"},
    {"agent": "風險/新聞", "confidence": 5.5, "weight": 0.20, "key_factor": "無重大事件"},
]


class TestCardStatesTheBar:

    def test_shows_score_threshold_and_gap(self):
        card = render_card(action="BUY", ticker="NVDA", score=6.8, threshold=7.5,
                           breakdown=_ENTRY_BREAKDOWN)
        assert "6.8/10" in card
        assert "7.5" in card
        assert "差 0.7" in card

    def test_auto_executed_card_reports_the_margin(self):
        card = render_card(action="BUY", ticker="NVDA", score=9.1, threshold=7.5,
                           breakdown=_ENTRY_BREAKDOWN, auto_executed=True)
        assert "超出 +1.6" in card
        assert "需要核准" not in card

    def test_auto_executed_card_omits_the_expiry_prompt(self):
        card = render_card(action="BUY", ticker="NVDA", score=9.1, threshold=7.5,
                           auto_executed=True, expires_seconds=300)
        assert "失效" not in card

    def test_headline_can_report_a_user_approved_fill(self):
        """An approved trade must not be labelled as auto-executed."""
        card = render_card(action="SELL", ticker="NVDA", score=6.5, threshold=6.0,
                           auto_executed=True, headline="✅ 核准後執行：SELL NVDA")
        assert "核准後執行" in card
        assert "已自動執行" not in card


class TestShortfallExplanation:

    def test_blames_the_largest_weighted_shortfall_not_the_lowest_score(self):
        """
        The point of the "why" line: 未實現損益 at 4.0x0.30 gives up 1.80 of
        composite, while 動能反轉 at 3.2x0.25 gives up only 1.70. The lower raw
        score is NOT the one holding the trade back, and saying so would send
        the user to investigate the wrong input.
        「為何沒自動執行」的重點：未實現損益 4.0x0.30 讓出 1.80，動能反轉 3.2x0.25
        只讓出 1.70。原始分數較低者並非真正的阻因，指錯會讓使用者去查錯地方。
        """
        reason = explain_shortfall(_EXIT_BREAKDOWN, score=5.4, threshold=6.0)
        assert "未實現損益" in reason
        assert "動能反轉" not in reason

    def test_names_the_weight_and_key_factor(self):
        reason = explain_shortfall(_ENTRY_BREAKDOWN, score=6.8, threshold=7.5)
        assert "Risk" in reason
        assert "20%" in reason
        assert "財報前 2 日" in reason

    def test_degrades_gracefully_without_a_breakdown(self):
        reason = explain_shortfall(None, score=6.8, threshold=7.5)
        assert "6.8" in reason and "7.5" in reason

    def test_appears_only_when_approval_is_needed(self):
        card = render_card(action="BUY", ticker="NVDA", score=9.1, threshold=7.5,
                           breakdown=_ENTRY_BREAKDOWN, auto_executed=True)
        assert "為何沒自動執行" not in card

    def test_a_withheld_but_passing_score_is_not_reported_as_short(self):
        """
        The validation gate can withhold auto-execution from a SELL scoring
        10/10. Printing "差 -4.0" there tells the user the score fell short
        when it did not — the reason was policy, not the number.
        驗證關卡可能對 10/10 的 SELL 撤銷自動執行。此時印出「差 -4.0」會讓使用者
        誤以為分數不足，但真正原因是政策而非分數。
        """
        card = render_card(action="SELL", ticker="NVDA", score=10.0, threshold=6.0,
                           breakdown=_EXIT_BREAKDOWN, auto_executed=False,
                           context_lines=["", "⚠️ strategy not validated"])
        assert "差 -" not in card
        assert "已達標" in card
        assert "為何沒自動執行" not in card


class TestBreakdownArithmetic:

    def test_entry_side_weights_are_supplied_when_missing(self):
        """
        CompositorService emits agent/confidence/key_factor with no weights,
        so the card looks them up rather than pretending each is equal.
        買進側不輸出權重，卡片改為查表補齊而非假裝等權。
        """
        card = render_card(action="BUY", ticker="NVDA", score=6.8, threshold=7.5,
                           breakdown=_ENTRY_BREAKDOWN)
        assert "×0.35" in card  # Fundamental
        assert "×0.20" in card  # Sentiment / Risk

    def test_contributions_sum_to_the_displayed_total(self):
        card = render_card(action="SELL", ticker="NVDA", score=5.4, threshold=6.0,
                           breakdown=_EXIT_BREAKDOWN)
        # 4.0*.30 + 9.0*.25 + 3.2*.25 + 5.5*.20 = 5.35
        assert "5.35" in card

    def test_weights_that_do_not_sum_to_one_are_renormalized(self):
        """
        The displayed contributions must add up to the displayed total, or the
        card contradicts itself in front of the user.
        顯示的貢獻必須加總等於顯示的合計，否則卡片會當著使用者的面自相矛盾。
        """
        card = render_card(
            action="SELL", ticker="X", score=5.0, threshold=6.0,
            breakdown=[
                {"agent": "A", "confidence": 6.0, "weight": 0.5},
                {"agent": "B", "confidence": 4.0, "weight": 0.5},
                {"agent": "C", "confidence": 8.0, "weight": 0.5},
            ],
        )
        rows = [l for l in card.splitlines() if "=" in l]
        shown = sum(float(r.split("=")[1].split()[0]) for r in rows)
        total_line = [l for l in card.splitlines() if "加權合計" in l][0]
        assert abs(shown - float(total_line.split()[-1])) < 0.02

    def test_breakdown_is_fenced_for_monospace(self):
        """
        Telegram renders body text proportionally; only <pre> preserves the
        column alignment, and telegram_adapter derives that from the fence.
        Telegram 內文為比例字型，唯有 <pre> 能保留欄位對齊，而該標籤由圍欄產生。
        """
        card = render_card(action="BUY", ticker="NVDA", score=6.8, threshold=7.5,
                           breakdown=_ENTRY_BREAKDOWN)
        assert card.count("```") == 2

    def test_cjk_labels_align_by_display_width(self):
        """
        str.ljust pads by character count, so "集中度" (3 chars, 6 cells) came
        out narrower than "Fundamental" and sheared the columns.
        str.ljust 依字元數補齊，「集中度」3 字元卻佔 6 格，會導致欄位錯位。
        """
        import unicodedata

        def cells(text):
            # Character index is the wrong measure here: CJK labels have fewer
            # characters but occupy more columns, so aligned rows have
            # *different* str.index() values. Compare display width instead.
            # 字元索引在此是錯的量測：CJK 標籤字元較少但佔更多欄位，對齊的列反而
            # 有不同的 str.index()。應改比對顯示寬度。
            return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)

        card = render_card(action="SELL", ticker="NVDA", score=5.4, threshold=6.0,
                           breakdown=_EXIT_BREAKDOWN)
        rows = [l for l in card.splitlines() if "×" in l]
        columns = {cells(r[: r.index("×")]) for r in rows}
        assert len(columns) == 1, f"× not aligned across rows (display cols): {columns}"


class TestTelegramLimits:

    def test_typical_card_is_far_below_the_limit(self):
        card = render_card(action="BUY", ticker="NVDA", score=6.8, threshold=7.5,
                           breakdown=_ENTRY_BREAKDOWN, size_line="部位：$20.00",
                           expires_seconds=300)
        assert len(card) < 1000

    def test_pathological_breakdown_is_truncated(self):
        card = render_card(
            action="BUY", ticker="NVDA", score=6.8, threshold=7.5,
            breakdown=[
                {"agent": f"Agent{i}", "confidence": 5.0, "key_factor": "x" * 200}
                for i in range(100)
            ],
        )
        assert len(card) <= MAX_CARD_CHARS
