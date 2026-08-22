"""
Confidence scoring for EXITS. The sell-side counterpart to CompositorService.
賣出信心評分：CompositorService 的賣出側對應物。

Why this exists / 為何需要
────────────────────────
Buying was already scored. `CompositorService` runs four analyst agents,
weights them, and emits a 0-10 composite with a per-agent breakdown — and the
cash-deployment path feeds that straight into `evaluate_and_execute_trade`.

Selling had none of that. Every sell in the system carried a hardcoded number:

    sentinel_service._handle_rebalance_logic   a settings constant
    sentinel_service._trigger_emergency_...    emergency_score / hedge_score
    sentinel_service._execute_trade_signals    an LLM's unstructured self-rating
    socket_manager                             literally 10
    confidence_rebalance_service               literally 8

Those numbers were compared against the same auto-execute threshold as a
scored buy, so a constant decided whether real money moved, with no way to
ask *why*. This module supplies the missing half.

買進側早有評分（四個分析代理人加權為 0-10 並附分項），賣出側卻全是寫死常數，
而這些常數又和有評分的買單比對同一個自動執行門檻——等於由常數決定真錢是否
移動，且無從追問理由。本模組補上缺的另一半。

Exit factors are not entry factors / 賣出因子不同於買進因子
──────────────────────────────────────────────────────────
Whether to open a position and whether to close one are different questions,
so the factor set differs. Fundamental quality barely moves week to week and
is a poor exit trigger; where the position sits relative to its entry, and
whether the thesis is breaking, are what matter.

  Unrealized P&L / stop distance  0.30   position_lots.open_price vs spot
  Concentration                   0.25   weight vs max_single_position_weight
  Momentum reversal               0.25   OHLCV, same source as entry Momentum
  Risk / news                     0.20   the existing Risk agent

The output shape deliberately matches `CompositorService._build_decision` —
same `composite_score`, `breakdown`, `rationale` keys — so the decision card
and the execution path never have to branch on direction.

輸出結構刻意與買進側一致，讓決策卡與執行路徑無需依方向分岔。

A caveat worth stating plainly / 一個必須說清楚的限制
────────────────────────────────────────────────────
These weights are a human prior, not a calibration. Nothing here has been
fitted to outcomes, because `decision_outcomes` has no history yet. A 9.0 does
not mean 90% of such exits are correct. The number is an auditable summary of
four stated inputs — that is all it claims to be until there is enough
resolved history to calibrate against.

這些權重是人訂的先驗而非校準結果——decision_outcomes 尚無歷史可擬合。9.0 不
代表九成正確。在累積足夠已結算歷史之前，它只是四項輸入的可稽核彙總。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.services.confidence_compositor_service import AgentSubScore, CompositorService

logger = logging.getLogger("ExitCompositorService")

# Factor -> weight. Sums to 1.0.
# 因子與權重，總和為 1.0。
EXIT_FACTOR_WEIGHTS: Dict[str, float] = {
    "pnl": 0.30,
    "concentration": 0.25,
    "momentum_reversal": 0.25,
    "risk": 0.20,
}

# Display labels, so the Telegram card and the logs agree.
# 顯示名稱，讓 Telegram 卡片與日誌一致。
EXIT_FACTOR_LABELS: Dict[str, str] = {
    "pnl": "未實現損益",
    "concentration": "集中度",
    "momentum_reversal": "動能反轉",
    "risk": "風險/新聞",
}


class ExitCompositorService:
    """
    Score how strongly a position should be closed, 0-10.
    評估一個部位應該被平掉的強度，0-10。
    """

    def __init__(self, user_id: str, settings_service: Any = None, market_service: Any = None):
        self.user_id = user_id
        self._settings_service = settings_service
        self._market_service = market_service
        # Reused for its LLM plumbing (_get_pipeline / _score_via_llm /
        # _fallback_score) so the Risk factor goes through exactly the same
        # budget-aware router and JSON parsing as the entry side.
        # 重用其 LLM 管線，讓風險因子與買進側走同一套路由與 JSON 解析。
        self._llm = CompositorService(user_id=user_id)

    # ── Public API ──

    async def score_exit(
        self,
        ticker: str,
        quantity: float,
        current_price: Optional[float] = None,
        current_weight_pct: Optional[float] = None,
        reason_hint: str = "",
    ) -> Dict[str, Any]:
        """
        Score one candidate exit. Never raises — a scoring failure must not
        prevent a stop-loss from being considered.
        評估單一出場候選。不拋例外：評分失敗不得讓停損失去被考慮的機會。

        Returns the same shape as CompositorService decisions:
        `composite_score`, `breakdown`, `rationale`, plus exit-specific context.
        """
        sub_scores: List[AgentSubScore] = []

        # Each factor is isolated. The individual scorers already handle their
        # own expected failures, but an unhandled one here would propagate and
        # abort the whole evaluation — which in the rebalance path means a
        # position that should have been considered for a stop-loss is simply
        # never looked at. A neutral 5.0 keeps the other three factors
        # meaningful; losing the whole score loses the stop.
        # 每個因子彼此隔離。各評分函式已處理自身的預期失敗，但此處若有未攔截的
        # 例外會往上拋並中止整次評估——在再平衡路徑上，等於某個本該被考慮停損的
        # 部位根本沒被看過。給中性 5.0 可保留其餘三項因子的意義；讓整個評分失敗
        # 則連停損機會一起失去。
        pnl_pct, pnl_score, pnl_factors = self._safe(
            lambda: self._score_pnl(ticker, current_price),
            default=(None, 5.0, {}),
            label="pnl",
        )
        sub_scores.append(self._sub("pnl", ticker, pnl_score, pnl_factors))

        conc_score, conc_factors = self._safe(
            lambda: self._score_concentration(current_weight_pct),
            default=(5.0, {}),
            label="concentration",
        )
        sub_scores.append(self._sub("concentration", ticker, conc_score, conc_factors))

        mom_score, mom_factors = self._safe(
            lambda: self._score_momentum_reversal(ticker),
            default=(5.0, {}),
            label="momentum_reversal",
        )
        sub_scores.append(self._sub("momentum_reversal", ticker, mom_score, mom_factors))

        try:
            risk_score, risk_factors = await self._score_risk(ticker, reason_hint)
        except Exception as e:
            logger.warning(f"ExitCompositor: risk factor raised for {ticker}: {e}")
            risk_score, risk_factors = 5.0, self._unavailable(e)
        sub_scores.append(self._sub("risk", ticker, risk_score, risk_factors))

        composite = self._aggregate(sub_scores)

        return {
            "ticker": ticker,
            "action": "SELL",
            "quantity": quantity,
            "composite_score": round(composite, 2),
            "unrealized_pnl_pct": pnl_pct,
            "current_weight_pct": current_weight_pct,
            "breakdown": [
                {
                    "agent": EXIT_FACTOR_LABELS.get(s.agent_name, s.agent_name),
                    "factor_key": s.agent_name,
                    "confidence": s.confidence,
                    "weight": EXIT_FACTOR_WEIGHTS.get(s.agent_name, 0.0),
                    "contribution": round(
                        s.confidence * EXIT_FACTOR_WEIGHTS.get(s.agent_name, 0.0), 2
                    ),
                    "key_factor": s.factors.get("key_factor", "N/A"),
                    "factors": s.factors,
                }
                for s in sub_scores
            ],
            "rationale": self._build_rationale(sub_scores, composite),
        }

    # ── Factors ──

    def _score_pnl(
        self, ticker: str, current_price: Optional[float]
    ) -> Tuple[Optional[float], float, Dict[str, Any]]:
        """
        Score exit urgency from where the position sits versus its entry.
        以部位相對於進場價的位置評估出場急迫性。

        Losses score high (cut it), gains score low-to-middling (let it run,
        with a mild bias to taking profit once the move is large). The stop
        level is `stop_loss_pct` from settings, defaulting to 8%.
        虧損得高分（該砍），獲利得低到中間分（讓利潤跑，僅在漲幅很大時略偏向
        獲利了結）。停損水位取設定 stop_loss_pct，預設 8%。
        """
        lots = self._open_lots(ticker)
        if not lots or not current_price or current_price <= 0:
            return None, 5.0, {
                "key_factor": "無進場成本資料",
                "rationale": "position_lots 無此標的開倉紀錄，或缺少現價，無法計算損益",
                "_insufficient_data": True,
            }

        total_qty = sum(float(l.get("quantity") or 0) for l in lots)
        if total_qty <= 0:
            return None, 5.0, {
                "key_factor": "無有效持倉",
                "rationale": "開倉紀錄數量為 0",
                "_insufficient_data": True,
            }

        cost = sum(float(l.get("quantity") or 0) * float(l.get("open_price") or 0) for l in lots)
        avg_entry = cost / total_qty
        if avg_entry <= 0:
            return None, 5.0, {
                "key_factor": "進場成本異常",
                "rationale": f"加權平均成本為 {avg_entry}",
                "_insufficient_data": True,
            }

        pnl_pct = (current_price / avg_entry - 1) * 100
        stop_pct = self._setting_float("stop_loss_pct", 8.0)

        if pnl_pct <= -stop_pct:
            score = 10.0
            key = f"{pnl_pct:.1f}%，已觸停損 -{stop_pct:.0f}%"
        elif pnl_pct < 0:
            # Ramp 5 -> 10 as the loss approaches the stop.
            # 虧損逼近停損時由 5 線性升到 10。
            score = 5.0 + 5.0 * min(1.0, abs(pnl_pct) / stop_pct)
            key = f"{pnl_pct:.1f}%，距停損 {stop_pct - abs(pnl_pct):.1f} 個百分點"
        elif pnl_pct >= 25.0:
            score = 6.0
            key = f"+{pnl_pct:.1f}%，漲幅大，可考慮部分了結"
        else:
            # Ramp 2 -> 6 across 0..25% gain. A winner is not a reason to sell.
            # 0~25% 獲利區間由 2 升到 6；獲利本身不是賣出理由。
            score = 2.0 + 4.0 * (pnl_pct / 25.0)
            key = f"+{pnl_pct:.1f}%，仍在持有區間"

        return round(pnl_pct, 2), round(score, 1), {
            "key_factor": key,
            "rationale": f"加權平均成本 ${avg_entry:.4f}，現價 ${current_price:.4f}",
            "avg_entry_price": round(avg_entry, 4),
            "stop_loss_pct": stop_pct,
        }

    def _score_concentration(self, current_weight_pct: Optional[float]) -> Tuple[float, Dict[str, Any]]:
        """
        Score exit urgency from position weight against the ceiling.
        以部位權重相對上限評估出場急迫性。
        """
        if current_weight_pct is None:
            return 5.0, {
                "key_factor": "無權重資料",
                "rationale": "呼叫端未提供 current_weight_pct",
                "_insufficient_data": True,
            }

        ceiling = self._setting_float("max_single_position_weight", 25.0)
        if ceiling <= 0:
            return 5.0, {"key_factor": "上限設定無效", "rationale": f"max_single_position_weight={ceiling}"}

        ratio = current_weight_pct / ceiling
        if ratio >= 1.0:
            # 10 at the ceiling, saturating as it goes further past.
            # 觸及上限得 10，超越越多越飽和。
            score = min(10.0, 9.0 + (ratio - 1.0) * 4.0)
            key = f"佔 {current_weight_pct:.1f}% > 上限 {ceiling:.0f}%"
        else:
            # Below the ceiling concentration is not an exit reason.
            # 未達上限時，集中度不構成出場理由。
            score = max(0.0, 6.0 * ratio)
            key = f"佔 {current_weight_pct:.1f}%，未達上限 {ceiling:.0f}%"

        return round(score, 1), {
            "key_factor": key,
            "rationale": f"權重 {current_weight_pct:.1f}% vs 上限 {ceiling:.1f}%",
            "ceiling_pct": ceiling,
        }

    def _score_momentum_reversal(self, ticker: str) -> Tuple[float, Dict[str, Any]]:
        """
        Score exit urgency from price breaking down through its moving average.
        以價格跌破均線的程度評估出場急迫性。

        Deterministic and cheap — no LLM. Uses the same `get_ohlcv` the entry
        side's Momentum agent reads, so entry and exit cannot disagree about
        what the price did.
        純計算、不呼叫 LLM，且與買進側 Momentum 讀同一個 get_ohlcv，避免進出場
        對「價格發生了什麼」有不同認知。
        """
        try:
            market = self._market()
            ohlcv = market.get_ohlcv(ticker, days=30)
            closes = [float(c) for c in (ohlcv.get("close") or [])]
        except Exception as e:
            logger.warning(f"ExitCompositor: OHLCV unavailable for {ticker}: {e}")
            return 5.0, {
                "key_factor": "無價格資料",
                "rationale": f"get_ohlcv 失敗：{e}",
                "_insufficient_data": True,
            }

        if len(closes) < 20:
            return 5.0, {
                "key_factor": "價格樣本不足",
                "rationale": f"只有 {len(closes)} 根 K 線，需要 20 根",
                "_insufficient_data": True,
            }

        ma20 = sum(closes[-20:]) / 20.0
        spot = closes[-1]
        if ma20 <= 0:
            return 5.0, {"key_factor": "均線異常", "rationale": f"MA20={ma20}"}

        gap_pct = (spot / ma20 - 1) * 100

        if gap_pct <= -5.0:
            score, key = 9.0, f"跌破 20MA {abs(gap_pct):.1f}%，趨勢轉弱"
        elif gap_pct < 0:
            score = 5.0 + 4.0 * (abs(gap_pct) / 5.0)
            key = f"跌破 20MA {abs(gap_pct):.1f}%"
        elif gap_pct >= 10.0:
            score, key = 1.0, f"高於 20MA {gap_pct:.1f}%，趨勢仍強"
        else:
            score = 5.0 - 4.0 * (gap_pct / 10.0)
            key = f"高於 20MA {gap_pct:.1f}%"

        return round(score, 1), {
            "key_factor": key,
            "rationale": f"現價 ${spot:.4f} vs MA20 ${ma20:.4f}",
            "ma20": round(ma20, 4),
            "gap_pct": round(gap_pct, 2),
        }

    async def _score_risk(self, ticker: str, reason_hint: str) -> Tuple[float, Dict[str, Any]]:
        """
        Score exit urgency from news / event risk, via the existing Risk agent.
        以新聞與事件風險評估出場急迫性，走既有的 Risk 代理人。
        """
        prompt = (
            "You are a risk analyst deciding whether an EXISTING long position should be "
            "CLOSED because of risk or news, not whether to open one.\n"
            "Ticker: {ticker}\n"
            f"Context from the monitoring system: {reason_hint or 'none'}\n\n"
            "Score 0-10 where 10 = close immediately (severe adverse news, "
            "credit/solvency event, regulatory action) and 0 = no risk reason to exit.\n"
            'Return ONLY JSON: {{"score": <0-10>, "key_factor": "<12 words max>", '
            '"rationale": "<one sentence>"}}'
        )
        try:
            score, factors = await self._llm._score_via_llm(
                ticker=ticker,
                agent_name="Risk",
                prompt_template=prompt,
                tier=CompositorService.AGENT_TIERS.get("Risk", "fast"),
            )
            factors.setdefault("key_factor", "N/A")
            return score, factors
        except Exception as e:
            # Neutral rather than alarming: a broken LLM call is not evidence
            # of risk, and scoring it 10 would trigger spurious liquidations.
            # 取中性而非警戒值：LLM 失敗不構成風險證據，給 10 會引發假性清倉。
            logger.warning(f"ExitCompositor: risk scoring failed for {ticker}: {e}")
            return 5.0, {
                "key_factor": "風險評分不可用",
                "rationale": f"LLM 呼叫失敗：{e}",
                "_insufficient_data": True,
            }

    # ── Aggregation ──

    def _aggregate(self, sub_scores: List[AgentSubScore]) -> float:
        """Weighted mean over EXIT_FACTOR_WEIGHTS. 依權重加權平均。"""
        weighted_sum = 0.0
        total_weight = 0.0
        for s in sub_scores:
            weight = EXIT_FACTOR_WEIGHTS.get(s.agent_name, 0.0)
            weighted_sum += s.confidence * weight
            total_weight += weight
        if total_weight <= 0:
            return 5.0
        return weighted_sum / total_weight

    def _build_rationale(self, sub_scores: List[AgentSubScore], composite: float) -> str:
        lines = [f"Exit confidence: {composite:.1f}/10"]
        for s in sub_scores:
            label = EXIT_FACTOR_LABELS.get(s.agent_name, s.agent_name)
            lines.append(f"  ├─ {label}: {s.confidence:.1f}/10 ({s.factors.get('key_factor', 'N/A')})")
        return "\n".join(lines)

    # ── Helpers ──

    def _safe(self, fn, default, label: str):
        """
        Run one factor; on an unexpected error return `default` and say so.
        執行單一因子；發生非預期錯誤時回傳 default 並記錄。
        """
        try:
            return fn()
        except Exception as e:
            logger.warning(f"ExitCompositor: {label} factor raised: {e}")
            # Replace the trailing factors dict with an explanatory one so the
            # decision card shows why that row is neutral instead of implying
            # a real 5.0 reading.
            # 以說明性的 factors 取代最後一個元素，讓決策卡顯示該列為何中性，
            # 而非讓使用者以為那是真實量測到的 5.0。
            return tuple(default[:-1]) + (self._unavailable(e),)

    @staticmethod
    def _unavailable(error: Exception) -> Dict[str, Any]:
        return {
            "key_factor": "評分不可用",
            "rationale": f"{type(error).__name__}: {error}",
            "_insufficient_data": True,
        }

    def _sub(self, name: str, ticker: str, score: float, factors: Dict[str, Any]) -> AgentSubScore:
        return AgentSubScore(
            agent_name=name,
            ticker=ticker,
            confidence=float(score),
            factors=factors,
            rationale=factors.get("rationale", ""),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _open_lots(self, ticker: str) -> List[Dict[str, Any]]:
        try:
            from src.repositories.position_lot_repository import AlchemyPositionLotRepository
            return AlchemyPositionLotRepository().get_open_lots(self.user_id, ticker=ticker) or []
        except Exception as e:
            logger.warning(f"ExitCompositor: could not read position_lots for {ticker}: {e}")
            return []

    def _market(self):
        if self._market_service is None:
            # MarketDataService must be given a user-scoped SettingsService.
            # Constructed bare it builds SettingsService() with no user_id,
            # whose _get_effective_uid() raises — and because
            # _score_momentum_reversal catches broadly, that would have
            # degraded the momentum factor to a permanent neutral 5.0 instead
            # of failing loudly. Matches how SentinelService builds it.
            # MarketDataService 必須傳入綁定使用者的 SettingsService；無參數建構會
            # 產生沒有 user_id 的 SettingsService 並在取用時拋錯，而動能評分的
            # 廣泛 except 會把它吞成永久中性的 5.0，而非明確失敗。
            from src.services.market_data_service import MarketDataService
            self._market_service = MarketDataService(settings_service=self._settings())
        return self._market_service

    def _settings(self):
        if self._settings_service is None:
            from src.services.settings_service import SettingsService
            self._settings_service = SettingsService(user_id=self.user_id)
        return self._settings_service

    def _setting_float(self, key: str, default: float) -> float:
        try:
            raw = self._settings().get_setting(key, default, self.user_id)
            return float(raw) if raw is not None else default
        except Exception as e:
            # `stop_loss_pct` and `max_single_position_weight` come through
            # here and both shape an exit score. Falling back quietly means a
            # tuned threshold silently stops applying.
            # stop_loss_pct 與 max_single_position_weight 都經由此處，且都會影響
            # 出場評分；靜默退回預設等於調校過的門檻悄悄失效。
            logger.warning(f"Setting {key!r} unreadable ({e}); using default {default}")
            return default
