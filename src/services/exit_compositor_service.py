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

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.services.confidence_compositor_service import AgentSubScore, CompositorService
from src.config.owner import resolve_user_id

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
        self.user_id = resolve_user_id(user_id)
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
        open_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Score one candidate exit. Never raises — a scoring failure must not
        prevent a stop-loss from being considered.
        評估單一出場候選。不拋例外：評分失敗不得讓停損失去被考慮的機會。

        Returns the same shape as CompositorService decisions:
        `composite_score`, `breakdown`, `rationale`, plus exit-specific context.
        """
        sub_scores: List[AgentSubScore] = []

        pnl_pct, pnl_score, pnl_factors = self._safe(
            lambda: self._score_pnl(ticker, current_price, open_price=open_price),
            default=(None, 5.0, {}),
            label="pnl",
        )
        sub_scores.append(self._sub("pnl", ticker, pnl_score, pnl_factors))

        conc_score, conc_factors = self._safe(
            lambda: self._score_concentration(current_weight_pct, pnl_pct=pnl_pct),
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

        # Check active micro event bias (個經事件偏置)
        active_micro_bias = 0.0
        active_event_headline = ""
        try:
            from src.services.event_impact_service import EventImpactService
            impact_svc = EventImpactService(user_id=self.user_id, settings_service=self._settings_service)
            active_micro_bias, active_events = impact_svc.get_ticker_micro_bias(ticker)
            if active_events and active_micro_bias < 0:
                active_event_headline = active_events[0].get("headline", "")
        except Exception as e:
            logger.warning(f"ExitCompositor: failed to check micro event bias for {ticker}: {e}")

        effective_reason_hint = reason_hint
        if active_event_headline:
            effective_reason_hint = (
                f"{reason_hint} | Active Negative Event: {active_event_headline}"
                if reason_hint else f"Active Negative Event: {active_event_headline}"
            )

        # Fast path: if quantitative factors prove that even under the worst possible
        # risk score (10.0), the composite score cannot reach 5.0 (sell threshold is >= 6.0),
        # skip the expensive ~75s LLM call and assign neutral risk (3.0).
        # 若量化三因子顯示持倉極度穩健（即使風險給最極端 10 分總分仍低於 5.0），
        # 且無外部觸發理由與負面事件，則豁免慢速 LLM 呼叫，避免 Celery worker 軟超時。
        max_possible_composite = (
            pnl_score * EXIT_FACTOR_WEIGHTS["pnl"]
            + conc_score * EXIT_FACTOR_WEIGHTS["concentration"]
            + mom_score * EXIT_FACTOR_WEIGHTS["momentum_reversal"]
            + 10.0 * EXIT_FACTOR_WEIGHTS["risk"]
        )
        has_specific_adverse_event = bool(active_event_headline) or (
            bool(reason_hint) and not reason_hint.lower().startswith("periodic holding review")
        )
        if not has_specific_adverse_event and max_possible_composite < 5.0:
            risk_score = 3.0
            risk_factors = {
                "key_factor": "基本面與技術面強健（豁免 LLM 慢速呼叫）",
                "rationale": f"量化指標穩健，最高可能總分 {max_possible_composite:.1f} < 5.0（賣出門檻 >= 6.0）",
                "_fast_path_exempt": True,
            }
        else:
            try:
                risk_score, risk_factors = await asyncio.wait_for(
                    self._score_risk(ticker, effective_reason_hint),
                    timeout=30.0,
                )
            except (asyncio.TimeoutError, TimeoutError) as te:
                logger.warning(f"ExitCompositor: risk scoring timed out for {ticker} after 30s: {te}")
                risk_score, risk_factors = 5.0, {
                    "key_factor": "風險評分逾時",
                    "rationale": "LLM 呼叫超過 30 秒逾時，賦予中性風險值",
                    "_insufficient_data": True,
                }
            except Exception as e:
                logger.warning(f"ExitCompositor: risk factor raised for {ticker}: {e}")
                risk_score, risk_factors = 5.0, self._unavailable(e)

        # Apply risk floor if active negative event bias exists
        if active_micro_bias < 0:
            event_risk_floor = min(10.0, 5.0 + abs(active_micro_bias) * 2.0)
            if risk_score < event_risk_floor:
                risk_score = event_risk_floor
                risk_factors["event_bias_floor_applied"] = True
                risk_factors["active_event_bias"] = active_micro_bias
                risk_factors["key_factor"] = f"事件利空衝擊 ({active_micro_bias:+.2f} pt)"

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
        self, ticker: str, current_price: Optional[float], open_price: Optional[float] = None
    ) -> Tuple[Optional[float], float, Dict[str, Any]]:
        """
        Score exit urgency from where the position sits versus its entry.
        以部位相對於進場價的位置評估出場急迫性。

        Losses score high (cut it), gains score low-to-middling (let it run,
        with a bias to taking profit once the move hits target).
        虧損得高分（該砍），獲利達標時觸發停利。
        """
        avg_entry = None
        if open_price and open_price > 0:
            avg_entry = open_price
        else:
            lots = self._open_lots(ticker)
            if lots and current_price and current_price > 0:
                total_qty = sum(float(l.get("quantity") or 0) for l in lots)
                if total_qty > 0:
                    cost = sum(float(l.get("quantity") or 0) * float(l.get("open_price") or 0) for l in lots)
                    if cost > 0:
                        avg_entry = cost / total_qty

        if not avg_entry or avg_entry <= 0 or not current_price or current_price <= 0:
            return None, 5.0, {
                "key_factor": "無進場成本資料",
                "rationale": "缺少開倉紀錄或現價，無法計算損益",
                "_insufficient_data": True,
            }

        pnl_pct = (current_price / avg_entry - 1) * 100
        enable_fixed_stops = self._setting_bool("enable_fixed_stops", False)
        stop_pct = self._setting_float("stop_loss_pct", 8.0)
        tp_pct = self._setting_float("take_profit_pct", 20.0)

        if enable_fixed_stops:
            if pnl_pct <= -stop_pct:
                score = 10.0
                key = f"{pnl_pct:.1f}%，已觸停損 -{stop_pct:.0f}%"
            elif pnl_pct < 0:
                # Ramp 5 -> 10 as the loss approaches the stop.
                # 虧損逼近停損時由 5 線性升到 10。
                score = 5.0 + 5.0 * min(1.0, abs(pnl_pct) / stop_pct)
                key = f"{pnl_pct:.1f}%，距停損 {stop_pct - abs(pnl_pct):.1f} 個百分點"
            elif pnl_pct >= tp_pct:
                score = 8.5
                key = f"+{pnl_pct:.1f}%，已達停利目標 +{tp_pct:.0f}%"
            else:
                # Ramp 2 -> 6 across 0..tp_pct gain.
                score = 2.0 + 4.0 * (pnl_pct / max(tp_pct, 1.0))
                key = f"+{pnl_pct:.1f}%，仍在持有區間"
        else:
            # Long-term investment logic (長線投資模式：不因短期拉回砍倉，不隨意切斷贏家複利)
            if pnl_pct > 0:
                # Profitable compounder: low exit urgency (1.0 - 2.5), let winners run.
                # Concentration factor independently handles over-weight risk.
                score = max(1.0, 2.5 - min(1.5, pnl_pct / 50.0))
                key = f"+{pnl_pct:.1f}%，長線獲利中（持續持有複利）"
            elif pnl_pct >= -15.0:
                # Normal market noise / minor pullback (0% to -15%): neutral hold (score 3.0 - 4.5).
                score = 3.0 + 1.5 * (abs(pnl_pct) / 15.0)
                key = f"{pnl_pct:.1f}%，常規回撤區間（無急迫出場需求）"
            elif pnl_pct >= -30.0:
                # Moderately deep drawdown (-15% to -30%): moderate score (4.5 - 6.5), prompt review.
                score = 4.5 + 2.0 * ((abs(pnl_pct) - 15.0) / 15.0)
                key = f"{pnl_pct:.1f}%，拉回幅度偏深（觀察基本面論點）"
            else:
                # Severe secular drawdown (> -30%): score 7.0 - 8.5.
                score = min(8.5, 6.5 + 2.0 * ((abs(pnl_pct) - 30.0) / 20.0))
                key = f"{pnl_pct:.1f}%，深幅回撤（檢視是否換庫或論點失效）"

        return round(pnl_pct, 2), round(score, 1), {
            "key_factor": key,
            "rationale": f"加權平均成本 ${avg_entry:.4f}，現價 ${current_price:.4f}",
            "avg_entry_price": round(avg_entry, 4),
            "stop_loss_pct": stop_pct,
            "take_profit_pct": tp_pct,
            "enable_fixed_stops": enable_fixed_stops,
        }

    def _score_concentration(
        self, current_weight_pct: Optional[float], pnl_pct: Optional[float] = None
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Score exit urgency from position weight against the ceiling.
        以部位權重相對上限評估出場急迫性。
        State-driven: 處於獲利複利期的強勢贏家（pnl_pct > 5%），集中度不作為機械式出場理由，
        避免「拔掉鮮花去澆灌野草」；虧損或未達標者超出上限才產生高度出場急迫性。
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
        protect_winners = self._setting_bool("protect_winning_compounders", False)

        if ratio >= 1.0:
            if protect_winners and pnl_pct is not None and pnl_pct > 5.0:
                # Profitable runner: concentration is an alert for tight trailing stop, NOT an urge to sell
                score = min(4.0, 2.0 + (ratio - 1.0) * 1.5)
                key = f"佔 {current_weight_pct:.1f}% > 上限 {ceiling:.0f}%（獲利複利中，由動態 ATR 追蹤保護）"
            else:
                score = min(10.0, 9.0 + (ratio - 1.0) * 4.0)
                key = f"佔 {current_weight_pct:.1f}% > 上限 {ceiling:.0f}%"
        else:
            score = max(0.0, 6.0 * ratio)
            key = f"佔 {current_weight_pct:.1f}%，未達上限 {ceiling:.0f}%"

        return round(score, 1), {
            "key_factor": key,
            "rationale": f"權重 {current_weight_pct:.1f}% vs 上限 {ceiling:.1f}%",
            "ceiling_pct": ceiling,
            "pnl_pct": pnl_pct,
            "winner_protected": bool(protect_winners and pnl_pct is not None and pnl_pct > 5.0),
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

    def _setting_bool(self, key: str, default: bool) -> bool:
        try:
            raw = self._settings().get_setting(key, default, self.user_id)
            if isinstance(raw, str):
                return raw.lower() in ("true", "1")
            return bool(raw) if raw is not None else default
        except Exception as e:
            logger.warning(f"Setting {key!r} unreadable ({e}); using default {default}")
            return default

    def evaluate_dynamic_atr_exit(
        self,
        entry_price: float,
        current_price: float,
        highest_price: Optional[float] = None,
        atr: Optional[float] = None,
        regime: Optional[Any] = None,
        institutional_support_price: Optional[float] = None,
    ) -> DynamicAtrExitResult:
        """Evaluate dynamic ATR exit with profit ratchet and institutional support."""
        return compute_dynamic_atr_exit(
            entry_price=entry_price,
            current_price=current_price,
            highest_price=highest_price,
            atr=atr,
            regime=regime,
            institutional_support_price=institutional_support_price,
        )


@dataclass
class DynamicAtrExitResult:
    """Dynamic ATR Stop-Loss and Profit Ratchet Evaluation Result."""
    should_exit: bool
    exit_type: str                   # "STOP_LOSS" | "BREAKEVEN_PROTECTION" | "TRAILING_PROFIT" | "HOLD"
    stop_price: float                # The active stop price
    pnl_pct: float                   # Unrealized gain/loss % from entry
    highest_price: float             # Highest price reached since entry
    ratchet_stage: str               # "INITIAL" | "BREAKEVEN" | "ADVANCING" | "TRAILING" | "HARVEST" | "RUNNER_LOCK" | "SUPPORT_LOCKED"
    rationale: str                   # Detailed explanation of status
    tier: int = 0                    # 0=Initial, 1=Breakeven/Advancing, 2=Trailing, 3=Harvest, 4=RunnerLock
    locked_profit_pct: float = 0.0   # Guaranteed minimum return % locked by stop
    drawdown_from_peak_pct: float = 0.0 # Pullback % from highest price reached


def compute_dynamic_atr_exit(
    entry_price: float,
    current_price: float,
    highest_price: Optional[float] = None,
    atr: Optional[float] = None,
    regime: Optional[Any] = None,
    atr_multiplier: Optional[float] = None,
    institutional_support_price: Optional[float] = None,
    previous_stop_price: Optional[float] = None,
) -> DynamicAtrExitResult:
    """
    Compute non-linear tiered dynamic ATR-based trailing stop and profit ratchet with institutional support awareness.
    非線性分段動態 ATR 移動停損與利潤棘輪計算器（結合主力籌碼支撐與波動階梯）：
    - Tier 0 (初始緩衝期, Peak < +5%): 進場點 - (ATR 乘數 * ATR)。若提供主力支撐價，取較高防禦線。
    - Tier 1 (保本防禦期, Peak >= +5%): 停損線單向棘輪上移至成本保本價 (Entry * 1.005)，覆蓋手續費與滑點。
    - Tier 1.5 (前進階梯期, Peak >= +12% 且 < +15%): 啟動初步移動止損，鎖定至少 35% 峰值利潤，防範中階回吐。
    - Tier 2 (利潤追蹤期, Peak >= +15%): 啟動標準移動追蹤停利 (Highest - 2.0x ATR，熊市 1.5x ATR)，並鎖定至少 45% 峰值利潤。
    - Tier 3 (收割鎖利期, Peak >= +25%): 收緊追蹤至 1.2x ATR (熊市 0.8x ATR)，並鎖定至少 65% 峰值利潤。
    - Tier 4 (波段超級鎖定, Peak >= +40%): 極窄追蹤至 1.0x ATR (熊市 0.6x ATR)，並鎖定至少 75% 峰值利潤，保全超額暴利。
    - 單調遞增特性 (Monotonic Ratchet): 停損價只升不降，嚴密截斷虧損、保全獲利。
    """
    if entry_price <= 0:
        raise ValueError(f"entry_price must be positive, got {entry_price}")

    # Safe default for ATR: if missing or non-positive, estimate as 3% of entry price
    effective_atr = atr if (atr is not None and atr > 0) else (entry_price * 0.03)
    effective_highest = max(entry_price, current_price, highest_price or 0.0)
    pnl_pct = (current_price / entry_price - 1.0) * 100.0
    peak_pnl_pct = (effective_highest / entry_price - 1.0) * 100.0
    drawdown_from_peak_pct = ((current_price - effective_highest) / effective_highest) * 100.0 if effective_highest > 0 else 0.0

    # Determine regime string or enum
    regime_str = str(getattr(regime, "value", regime) or "NEUTRAL_RANGE").upper()

    # Determine base multiplier
    if atr_multiplier is not None and atr_multiplier > 0:
        mult = float(atr_multiplier)
    elif "BEAR" in regime_str:
        mult = 1.5
    elif "BULL" in regime_str:
        mult = 2.5
    else:
        mult = 2.0

    # 1. Tier 0: Initial stop
    initial_stop = entry_price - mult * effective_atr
    active_stop = initial_stop
    ratchet_stage = "INITIAL"
    tier = 0

    # 2. Institutional Support Anchor / Ratchet
    if institutional_support_price and institutional_support_price > 0:
        support_stop = institutional_support_price * 0.992  # 0.8% buffer below support
        if support_stop >= entry_price:
            if support_stop > active_stop:
                active_stop = support_stop
                ratchet_stage = "SUPPORT_LOCKED"
        else:
            # Tier 0 initial stop-loss zone (below entry).
            # Prevent institutional support from compressing stop too tight and causing whipsaw exits
            # by requiring a minimum volatility noise buffer (at least 1.5x ATR or 4.5% below entry).
            min_noise_distance = max(1.5 * effective_atr, entry_price * 0.045)
            max_allowed_tier0_stop = entry_price - min_noise_distance
            capped_support_stop = min(support_stop, max_allowed_tier0_stop)
            if capped_support_stop > active_stop:
                active_stop = capped_support_stop

    # 3. Tier 1: Profit Ratchet Stage: Breakeven (peak >= +5%)
    if peak_pnl_pct >= 5.0:
        breakeven_stop = entry_price * 1.005
        if breakeven_stop > active_stop:
            active_stop = breakeven_stop
            ratchet_stage = "BREAKEVEN"
        tier = 1

    # 3b. Tier 1.5: Advancing Ratchet Stage (peak >= +12% and < +15%)
    if peak_pnl_pct >= 12.0:
        trail_mult_adv = 1.6 if "BEAR" in regime_str else 2.2
        advancing_stop = effective_highest - trail_mult_adv * effective_atr
        # Guaranteed floor: protect at least 35% of peak gains
        profit_floor_adv = entry_price + 0.35 * (effective_highest - entry_price)
        candidate_adv = max(advancing_stop, profit_floor_adv)
        if candidate_adv > active_stop:
            active_stop = candidate_adv
            ratchet_stage = "ADVANCING"
        tier = 1

    # 4. Tier 2: Profit Ratchet Stage: Trailing (peak >= +15%)
    if peak_pnl_pct >= 15.0:
        trail_mult = 1.5 if "BEAR" in regime_str else 2.0
        trailing_stop = effective_highest - trail_mult * effective_atr
        # Guaranteed floor: protect at least 45% of peak gains
        profit_floor = entry_price + 0.45 * (effective_highest - entry_price)
        candidate_trailing = max(trailing_stop, profit_floor)
        if candidate_trailing > active_stop:
            active_stop = candidate_trailing
            ratchet_stage = "TRAILING"
        tier = 2

    # 5. Tier 3: Harvest Stage: Tight Trailing & Locked Profit (peak > +25%)
    if peak_pnl_pct > 25.0:
        harvest_mult = 0.8 if "BEAR" in regime_str else 1.2
        harvest_stop = effective_highest - harvest_mult * effective_atr
        # Guaranteed floor: protect at least 65% of peak gains
        harvest_floor = entry_price + 0.65 * (effective_highest - entry_price)
        candidate_harvest = max(harvest_stop, harvest_floor)
        if candidate_harvest > active_stop:
            active_stop = candidate_harvest
            ratchet_stage = "HARVEST"
        tier = 3

    # 6. Tier 4: Super Runner Lock Stage (peak >= +40%)
    if peak_pnl_pct >= 40.0:
        runner_mult = 0.6 if "BEAR" in regime_str else 1.0
        runner_stop = effective_highest - runner_mult * effective_atr
        # Guaranteed floor: protect at least 75% of peak gains
        runner_floor = entry_price + 0.75 * (effective_highest - entry_price)
        candidate_runner = max(runner_stop, runner_floor)
        if candidate_runner > active_stop:
            active_stop = candidate_runner
            ratchet_stage = "RUNNER_LOCK"
        tier = 4

    # Monotonic ratchet: active stop price must never decrease below previous known stop
    if previous_stop_price and previous_stop_price > active_stop:
        active_stop = previous_stop_price

    locked_profit_pct = round(((active_stop - entry_price) / entry_price) * 100.0, 2)

    # Evaluate whether to exit
    should_exit = current_price <= active_stop
    if should_exit:
        if ratchet_stage == "RUNNER_LOCK":
            exit_type = "TRAILING_PROFIT"
            rationale = (
                f"觸發超強波段鎖利 (RUNNER_LOCK)：現價 ${current_price:.2f} <= 停利價 ${active_stop:.2f} "
                f"(最高價 ${effective_highest:.2f}, 峰值獲利 +{peak_pnl_pct:.1f}%, 保障鎖利 +{locked_profit_pct:.1f}%)"
            )
        elif ratchet_stage == "HARVEST":
            exit_type = "TRAILING_PROFIT"
            rationale = (
                f"觸發極窄收割停利 (HARVEST)：現價 ${current_price:.2f} <= 停利價 ${active_stop:.2f} "
                f"(最高價 ${effective_highest:.2f}, 峰值獲利 +{peak_pnl_pct:.1f}%, 保障鎖利 +{locked_profit_pct:.1f}%)"
            )
        elif ratchet_stage == "TRAILING":
            exit_type = "TRAILING_PROFIT"
            rationale = (
                f"觸發追蹤停利：現價 ${current_price:.2f} <= 停利價 ${active_stop:.2f} "
                f"(最高價 ${effective_highest:.2f}, 峰值獲利 +{peak_pnl_pct:.1f}%, 保障鎖利 +{locked_profit_pct:.1f}%)"
            )
        elif ratchet_stage == "ADVANCING":
            exit_type = "TRAILING_PROFIT"
            rationale = (
                f"觸發前進階梯保護 (ADVANCING)：現價 ${current_price:.2f} <= 停利價 ${active_stop:.2f} "
                f"(最高價 ${effective_highest:.2f}, 峰值獲利 +{peak_pnl_pct:.1f}%, 保障鎖利 +{locked_profit_pct:.1f}%)"
            )
        elif ratchet_stage == "BREAKEVEN":
            exit_type = "BREAKEVEN_PROTECTION"
            rationale = (
                f"觸發保本防線：現價 ${current_price:.2f} <= 保本價 ${active_stop:.2f} "
                f"(成本 ${entry_price:.2f}, 峰值獲利曾達 +{peak_pnl_pct:.1f}%)"
            )
        elif ratchet_stage == "SUPPORT_LOCKED":
            exit_type = "TRAILING_PROFIT" if pnl_pct >= 0 else "STOP_LOSS"
            rationale = (
                f"觸發主力籌碼防線：現價 ${current_price:.2f} <= 籌碼支撐停損價 ${active_stop:.2f} "
                f"(主力支撐 ${institutional_support_price:.2f}, 損益 {pnl_pct:+.1f}%)"
            )
        else:
            exit_type = "STOP_LOSS"
            rationale = (
                f"觸發 ATR 動態停損：現價 ${current_price:.2f} <= 停損價 ${active_stop:.2f} "
                f"(進場 ${entry_price:.2f}, {mult:.1f}x ATR, 虧損 {pnl_pct:.1f}%)"
            )
    else:
        exit_type = "HOLD"
        rationale = (
            f"部位安全持有中：現價 ${current_price:.2f} > 活躍停損/利價 ${active_stop:.2f} "
            f"(階梯: Tier {tier} [{ratchet_stage}], 未實現損益: {pnl_pct:+.2f}%, 鎖定底線: {locked_profit_pct:+.1f}%)"
        )

    return DynamicAtrExitResult(
        should_exit=should_exit,
        exit_type=exit_type,
        stop_price=round(active_stop, 4),
        pnl_pct=round(pnl_pct, 2),
        highest_price=round(effective_highest, 4),
        ratchet_stage=ratchet_stage,
        rationale=rationale,
        tier=tier,
        locked_profit_pct=locked_profit_pct,
        drawdown_from_peak_pct=round(drawdown_from_peak_pct, 2),
    )

