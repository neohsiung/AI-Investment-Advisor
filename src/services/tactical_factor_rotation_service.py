"""
Tactical Factor Rotation & Liquidity Premium Service
=====================================================
多因子流動性溢價與智能波段換倉服務

結合市場週期（價值 vs 成長、大盤 vs 中小型）與量價流動性溢價，於大盤回穩或反轉時，
自動將防守避險釋放的現金或低效資本，精準切換至 Alpha 彈性最大、動能最強的領導板塊。

核心設計：
1. 流動性溢價度量 (Liquidity Premium & Volume Elasticity)：
   整合 Amihud 非流動性溢價指標、成交量放量比率 (ADV5/ADV20) 與換手彈性 (Turnover Elasticity)，
   識別具備非對稱向上彈性、受聰明資金大單承接的優質標的。
2. 市場週期與風格體制感知 (Tactical Market Phase)：
   - EARLY_REBOUND (恐慌拐點 / 超跌反彈)：重押高彈性動能股與流動性擴張領導股 (Beta 彈性領先)。
   - BULL_ACCELERATION (多頭主升段)：順勢重押強勢動能 (Momentum) 與聰明錢突破 (Smart Money)。
   - LATE_CYCLE_VALUE (景氣末期 / 通膨高利率)：轉進高自由現金流價值股 (Value) 與高品質抗通膨資產 (Quality)。
   - DEFENSIVE_CONSOLIDATION (震盪盤整 / 體制防禦)：側重低波動 (Low Volatility) 與防守品質。
3. 非線性機會成本換倉門檻 (Friction-Aware Opportunity Swap)：
   委託 OpportunityCostService 檢驗雙向手續費與滑價門檻，杜絕頻繁無效換倉，並嚴格保護認證長線贏家。
4. 避險現金精準導流 (Defense Cash Injection)：
   當宏觀波動率平復 (解避險) 或防守現金充裕時，直接將儲備資本注入 Top Alpha 彈性候選標的。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.config.owner import resolve_user_id

logger = logging.getLogger("TacticalFactorRotationService")

STRATEGY_NAME = "tactical_factor_rotation"


class TacticalMarketPhase(str, Enum):
    """Tactical market cycle phase for factor rotation."""
    EARLY_REBOUND = "EARLY_REBOUND"                     # 恐慌拐點 / 波動回落超跌強彈
    BULL_ACCELERATION = "BULL_ACCELERATION"             # 順勢多頭動能加速
    LATE_CYCLE_VALUE = "LATE_CYCLE_VALUE"               # 景氣高檔 / 價值與防守現金流領先
    DEFENSIVE_CONSOLIDATION = "DEFENSIVE_CONSOLIDATION" # 震盪盤整 / 低波動品質防守


@dataclass
class LiquidityFactorMetrics:
    """Metrics quantifying liquidity premium and turnover elasticity for a ticker."""
    ticker: str
    adv_5d: float = 0.0
    adv_20d: float = 0.0
    volume_expansion_ratio: float = 1.0     # ADV5 / ADV20
    turnover_ratio: float = 0.02            # Dollar volume / Market Cap approximation
    amihud_ratio: float = 0.001             # |Return| / Dollar Volume (price impact)
    liquidity_premium_score: float = 0.50   # Standardized [0.0 ~ 1.0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "volume_expansion_ratio": round(self.volume_expansion_ratio, 2),
            "turnover_ratio": round(self.turnover_ratio, 4),
            "amihud_ratio": round(self.amihud_ratio, 6),
            "liquidity_premium_score": round(self.liquidity_premium_score, 4),
        }


@dataclass
class TacticalAssetScore:
    """Consolidated tactical factor rating for a single asset."""
    ticker: str
    phase: TacticalMarketPhase
    alpha_elasticity_score: float           # Composite score [0.0 ~ 1.0]
    rank: int = 1
    beta: float = 1.0
    factor_breakdown: Dict[str, float] = field(default_factory=dict)
    recommended_action: str = "MAINTAIN"    # "DEPLOY_BUY", "SWAP_TARGET", "MAINTAIN", "PRUNE_SELL"
    suggested_weight: float = 0.0
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "phase": self.phase.value,
            "alpha_elasticity_score": round(self.alpha_elasticity_score, 4),
            "rank": self.rank,
            "beta": round(self.beta, 2),
            "factor_breakdown": {k: round(v, 4) for k, v in self.factor_breakdown.items()},
            "recommended_action": self.recommended_action,
            "suggested_weight": round(self.suggested_weight, 4),
            "reason": self.reason,
        }


@dataclass
class TacticalRotationPlan:
    """Consolidated action plan for factor rotation and cash deployment."""
    phase: TacticalMarketPhase
    phase_rationale: str
    available_deployment_cash: float
    total_portfolio_value: float
    asset_scores: List[TacticalAssetScore] = field(default_factory=list)
    rebalance_orders: List[Dict[str, Any]] = field(default_factory=list)
    swaps_approved: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "phase_rationale": self.phase_rationale,
            "available_deployment_cash": round(self.available_deployment_cash, 2),
            "total_portfolio_value": round(self.total_portfolio_value, 2),
            "asset_scores": [s.to_dict() for s in self.asset_scores],
            "rebalance_orders": self.rebalance_orders,
            "swaps_approved": self.swaps_approved,
            "timestamp": self.timestamp.isoformat(),
        }


class TacticalFactorRotationService:
    """
    Evaluates market cycles, calculates multi-factor & liquidity premium scores,
    and devises frictionless tactical rotation plans to maximize alpha elasticity.
    """

    DEFAULT_MIN_SWAP_EDGE = 0.020           # Minimum 2.0% expected edge after friction
    DEFAULT_MAX_SWAPS_PER_CYCLE = 2         # Cap at 2 swaps per rotation tick
    DEFAULT_MAX_POSITION_WEIGHT = 0.20      # Cap individual asset weight at 20%

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        market_service: Optional[Any] = None,
        multi_factor_service: Optional[Any] = None,
        opportunity_cost_service: Optional[Any] = None,
        winner_service: Optional[Any] = None,
    ):
        try:
            self.user_id = resolve_user_id(user_id) if user_id else None
        except Exception:
            self.user_id = user_id or "default"
        self.settings_service = settings_service
        self.market_service = market_service
        self.multi_factor_service = multi_factor_service
        self.opportunity_cost_service = opportunity_cost_service
        self.winner_service = winner_service

    def _get_setting(self, key: str, default: Any, user_id: Optional[str] = None) -> Any:
        uid = user_id or self.user_id
        if self.settings_service:
            try:
                val = self.settings_service.get_setting(key, default, user_id=uid)
                if val is not None:
                    return val
            except Exception as e:
                logger.debug(f"Failed to read setting '{key}': {e}")
        return default

    def determine_market_phase(
        self,
        vix: float,
        vix_z_score: float = 0.0,
        spy_price: float = 0.0,
        spy_sma200: float = 0.0,
        yield_spread: Optional[float] = None,
        regime_hint: Optional[str] = None,
    ) -> Tuple[TacticalMarketPhase, str]:
        """
        Classify current tactical market phase based on volatility trajectory,
        trend position vs SMA 200, and macro yield curves.
        """
        hint_upper = (regime_hint or "").upper()
        if "PIVOT" in hint_upper or "REBOUND" in hint_upper:
            return (
                TacticalMarketPhase.EARLY_REBOUND,
                f"體制拐點訊號確立 ({regime_hint})：恐慌力竭回落，啟動超跌強彈高彈性資產配置",
            )

        # 1. EARLY_REBOUND: VIX turning down from spike (e.g. VIX was > 30 and now Z < 2.0 and VIX < 30)
        # or VIX between 24 and 35 but Z-Score dropping sharply
        if (22.0 <= vix <= 35.0 and vix_z_score < 1.5) or (vix < 28.0 and vix_z_score < 0.8 and hint_upper == "VOLATILITY_PIVOT"):
            return (
                TacticalMarketPhase.EARLY_REBOUND,
                f"波動率拐頭回落 (VIX={vix:.1f}, Z={vix_z_score:.1f}σ)：市場進入超跌修復期，優先布局高 Beta 與流動性彈性標的",
            )

        # 2. DEFENSIVE_CONSOLIDATION: Extreme volatility or strong breakdown
        if vix >= 30.0 or vix_z_score >= 2.5 or (spy_price > 0 and spy_sma200 > 0 and spy_price < spy_sma200 * 0.95):
            return (
                TacticalMarketPhase.DEFENSIVE_CONSOLIDATION,
                f"市場處於防禦震盪或下行期 (VIX={vix:.1f}, Z={vix_z_score:.1f}σ)：維持低波動與高品質防守配置",
            )

        # 3. LATE_CYCLE_VALUE: Yield curve inverted and calm volatility, or explicit value rotation
        if yield_spread is not None and yield_spread < -0.30 and vix < 24.0:
            return (
                TacticalMarketPhase.LATE_CYCLE_VALUE,
                f"殖利率曲線持續倒掛 (利差={yield_spread:.2f}%)：景氣循環末期，著重現金流品質與價值防禦標的",
            )

        # 4. BULL_ACCELERATION: SPY firmly above SMA200 and calm volatility
        if (spy_price > 0 and spy_sma200 > 0 and spy_price >= spy_sma200 * 1.01) or vix < 22.0:
            return (
                TacticalMarketPhase.BULL_ACCELERATION,
                f"多頭趨勢穩固順暢 (VIX={vix:.1f})：全面釋放動能 (Momentum) 與聰明錢 (Smart Money) 領導標的",
            )

        return (
            TacticalMarketPhase.DEFENSIVE_CONSOLIDATION,
            f"大盤指標處於中性震盪區間 (VIX={vix:.1f})：採取均衡配置陣型",
        )

    def get_phase_factor_weights(self, phase: TacticalMarketPhase) -> Dict[str, float]:
        """
        Return tactical factor allocation weights customized for the current market phase:
        [momentum, smart_money, liquidity_premium, quality, value, low_vol]
        """
        if phase == TacticalMarketPhase.EARLY_REBOUND:
            # Rebound phase prizes highest elasticity: high momentum + liquidity surge + quality core
            weights = {
                "momentum": 0.30,
                "liquidity_premium": 0.25,
                "smart_money": 0.20,
                "quality": 0.15,
                "value": 0.10,
                "low_vol": 0.00,
            }
        elif phase == TacticalMarketPhase.BULL_ACCELERATION:
            # Bull trend prioritizes sustained momentum and institutional accumulation
            weights = {
                "momentum": 0.35,
                "smart_money": 0.25,
                "quality": 0.20,
                "liquidity_premium": 0.10,
                "value": 0.10,
                "low_vol": 0.00,
            }
        elif phase == TacticalMarketPhase.LATE_CYCLE_VALUE:
            # Late cycle focuses on valuation margin of safety and balance sheet quality
            weights = {
                "value": 0.35,
                "quality": 0.25,
                "liquidity_premium": 0.15,
                "low_vol": 0.15,
                "smart_money": 0.05,
                "momentum": 0.05,
            }
        else:  # DEFENSIVE_CONSOLIDATION
            # Defensive phase protects against volatility and downside variance
            weights = {
                "low_vol": 0.35,
                "quality": 0.35,
                "value": 0.15,
                "liquidity_premium": 0.10,
                "smart_money": 0.05,
                "momentum": 0.00,
            }

        # Dynamically adjust liquidity_premium if custom setting provided
        custom_liq_weight = self._get_setting("factor_liquidity_premium_weight", None)
        if custom_liq_weight is not None:
            try:
                target_liq = float(custom_liq_weight)
                current_liq = weights.get("liquidity_premium", 0.10)
                diff = target_liq - current_liq
                weights["liquidity_premium"] = target_liq
                # Adjust remaining factor weights proportionally
                other_keys = [k for k in weights if k != "liquidity_premium"]
                other_sum = sum(weights[k] for k in other_keys)
                if other_sum > 0:
                    for k in other_keys:
                        weights[k] = max(0.0, weights[k] - diff * (weights[k] / other_sum))
            except Exception as e:
                logger.debug(f"Failed to apply custom factor_liquidity_premium_weight: {e}")

        return weights

    def compute_liquidity_premium_metrics(
        self,
        ticker_metrics: Dict[str, Dict[str, Any]],
    ) -> Dict[str, LiquidityFactorMetrics]:
        """
        Calculate cross-sectional liquidity metrics and normalized liquidity premium scores [0.0 ~ 1.0].
        Higher score = greater volume expansion and liquidity elasticity.
        """
        if not ticker_metrics:
            return {}

        results = {}
        raw_expansion = []
        tickers = list(ticker_metrics.keys())

        for t in tickers:
            data = ticker_metrics.get(t, {})
            adv5 = float(data.get("adv_5d", 0.0) or data.get("volume_5d", 0.0) or 1.0)
            adv20 = float(data.get("adv_20d", 0.0) or data.get("volume_20d", 0.0) or 1.0)
            expansion = adv5 / adv20 if adv20 > 0 else 1.0
            turnover = float(data.get("turnover_ratio", 0.02) or 0.02)
            amihud = float(data.get("amihud_ratio", 0.001) or 0.001)

            raw_expansion.append(expansion)
            results[t] = LiquidityFactorMetrics(
                ticker=t,
                adv_5d=adv5,
                adv_20d=adv20,
                volume_expansion_ratio=expansion,
                turnover_ratio=turnover,
                amihud_ratio=amihud,
                liquidity_premium_score=0.50,
            )

        # Cross-sectional percentile ranking
        if len(raw_expansion) > 1:
            ranks = np.argsort(np.argsort(raw_expansion))
            norm_scores = ranks / (len(raw_expansion) - 1)
            for i, t in enumerate(tickers):
                results[t].liquidity_premium_score = float(norm_scores[i])
        else:
            for t in tickers:
                results[t].liquidity_premium_score = 0.50

        return results

    def score_candidate_universe(
        self,
        candidate_data: Dict[str, Dict[str, Any]],
        phase: TacticalMarketPhase,
    ) -> List[TacticalAssetScore]:
        """
        Score and rank candidate universe by synthesizing multi-factor ensemble scores
        with liquidity premium elasticity.
        """
        if not candidate_data:
            return []

        weights = self.get_phase_factor_weights(phase)
        liquidity_metrics = self.compute_liquidity_premium_metrics(candidate_data)

        scored_assets: List[TacticalAssetScore] = []

        for ticker, data in candidate_data.items():
            # Extract standard factor scores [0.0 ~ 1.0]
            f_mom = float(data.get("momentum_score") if data.get("momentum_score") is not None else data.get("momentum", 0.50))
            f_qual = float(data.get("quality_score") if data.get("quality_score") is not None else data.get("quality", 0.50))
            f_val = float(data.get("value_score") if data.get("value_score") is not None else data.get("value", 0.50))
            f_low_vol = float(data.get("low_vol_score") if data.get("low_vol_score") is not None else data.get("low_vol", 0.50))
            f_smart = float(data.get("smart_money_score") if data.get("smart_money_score") is not None else data.get("smart_money", 0.50))
            beta = float(data.get("beta", 1.0))

            liq_metric = liquidity_metrics.get(ticker)
            f_liq = liq_metric.liquidity_premium_score if liq_metric else 0.50

            # Composite elasticity score
            composite = (
                weights.get("momentum", 0.0) * f_mom
                + weights.get("smart_money", 0.0) * f_smart
                + weights.get("liquidity_premium", 0.0) * f_liq
                + weights.get("quality", 0.0) * f_qual
                + weights.get("value", 0.0) * f_val
                + weights.get("low_vol", 0.0) * f_low_vol
            )

            # In EARLY_REBOUND, beta elasticity acts as an accelerator (higher beta bounces faster)
            if phase == TacticalMarketPhase.EARLY_REBOUND and beta > 1.2:
                beta_boost = min(0.08, (beta - 1.0) * 0.05)
                composite = min(1.0, composite + beta_boost)

            breakdown = {
                "momentum": f_mom,
                "smart_money": f_smart,
                "liquidity_premium": f_liq,
                "quality": f_qual,
                "value": f_val,
                "low_vol": f_low_vol,
            }

            reason = (
                f"[{phase.value}] 綜合評分={composite:.3f} | 動能={f_mom:.2f}, "
                f"流動性溢價={f_liq:.2f}, 聰明錢={f_smart:.2f}, Beta={beta:.2f}"
            )

            scored_assets.append(TacticalAssetScore(
                ticker=ticker,
                phase=phase,
                alpha_elasticity_score=composite,
                beta=beta,
                factor_breakdown=breakdown,
                reason=reason,
            ))

        # Sort descending by composite alpha elasticity score
        scored_assets.sort(key=lambda x: x.alpha_elasticity_score, reverse=True)
        for idx, item in enumerate(scored_assets, 1):
            item.rank = idx

        return scored_assets

    def evaluate_rotation_plan(
        self,
        portfolio: Dict[str, Any],
        candidate_data: Dict[str, Dict[str, Any]],
        vix: float,
        vix_z_score: float = 0.0,
        spy_price: float = 0.0,
        spy_sma200: float = 0.0,
        yield_spread: Optional[float] = None,
        regime_hint: Optional[str] = None,
    ) -> TacticalRotationPlan:
        """
        Formulate a comprehensive tactical factor rotation and cash deployment plan.
        """
        is_enabled = bool(self._get_setting("enable_tactical_factor_rotation", True))
        raw_min_edge = float(self._get_setting("tactical_rotation_min_edge_pct", 8.0))
        min_edge = (raw_min_edge / 100.0) if raw_min_edge > 1.0 else raw_min_edge
        max_swaps = int(self._get_setting("tactical_rotation_max_swaps_per_tick", self.DEFAULT_MAX_SWAPS_PER_CYCLE))
        max_pos_weight = float(self._get_setting("max_single_position_pct", self.DEFAULT_MAX_POSITION_WEIGHT))
        enable_rebound_cash = bool(self._get_setting("enable_rebound_cash_reinvestment", True))

        total_nlv = float(portfolio.get("total_nlv", 0.0) or portfolio.get("net_liquidation_value", 0.0) or 0.0)
        cash_balance = float(portfolio.get("cash_balance", 0.0) or portfolio.get("available_cash", 0.0) or 0.0)
        positions = portfolio.get("positions", []) or []

        if total_nlv <= 0:
            pos_val = sum(float(p.get("market_value", 0.0) or 0.0) for p in positions)
            total_nlv = pos_val + cash_balance

        phase, phase_rationale = self.determine_market_phase(
            vix=vix,
            vix_z_score=vix_z_score,
            spy_price=spy_price,
            spy_sma200=spy_sma200,
            yield_spread=yield_spread,
            regime_hint=regime_hint,
        )

        if not is_enabled or total_nlv <= 0:
            return TacticalRotationPlan(
                phase=phase,
                phase_rationale="波段輪動服務未啟用或投組淨值為 0",
                available_deployment_cash=cash_balance,
                total_portfolio_value=total_nlv,
                asset_scores=[],
            )

        scored_candidates = self.score_candidate_universe(candidate_data, phase)
        candidate_score_map = {c.ticker: c for c in scored_candidates}

        current_holdings_map = {}
        for p in positions:
            sym = p.get("symbol") or p.get("ticker")
            if sym:
                current_holdings_map[sym] = p

        rebalance_orders = []
        approved_swaps = []

        # 1. Direct Cash Deployment (Deploy excess cash from macro hedge unwind or cash reserve)
        # Target deployment: Allocate idle cash into Top 1~3 Alpha elasticity leaders
        base_cash_target = float(self._get_setting("target_cash_ratio", 0.10)) * total_nlv
        excess_cash = max(0.0, cash_balance - base_cash_target)

        if enable_rebound_cash and excess_cash >= 100.0 and scored_candidates:
            top_leaders = [c for c in scored_candidates if c.alpha_elasticity_score >= 0.65][:3]
            if top_leaders:
                cash_per_leader = excess_cash / len(top_leaders)
                for leader in top_leaders:
                    curr_pos = current_holdings_map.get(leader.ticker, {})
                    curr_val = float(curr_pos.get("market_value", 0.0) or 0.0)
                    curr_weight = curr_val / total_nlv if total_nlv > 0 else 0.0

                    if curr_weight < max_pos_weight:
                        allocable = min(cash_per_leader, (max_pos_weight - curr_weight) * total_nlv)
                        if allocable >= 50.0:
                            rebalance_orders.append({
                                "action": "BUY",
                                "ticker": leader.ticker,
                                "amount": round(allocable, 2),
                                "weight": round(allocable / total_nlv, 4),
                                "strategy_name": STRATEGY_NAME,
                                "confidence_score": round(leader.alpha_elasticity_score * 10, 1),
                                "reason": f"[{phase.value}] 避險現金回流注入 Top Alpha 彈性標的: {leader.ticker} (排名 #{leader.rank})",
                            })
                            leader.recommended_action = "DEPLOY_BUY"
                            leader.suggested_weight = allocable / total_nlv

        # 2. Friction-Aware Swaps (汰弱換強)
        # Identify underperforming holdings to swap into higher-conviction candidates
        protected_winners = set()
        if self.winner_service:
            try:
                winners = self.winner_service.get_certified_winners(user_id=self.user_id)
                protected_winners = {w.get("symbol") for w in winners if isinstance(w, dict)}
            except Exception as e:
                logger.debug(f"Failed to query certified winners: {e}")

        holding_scores = []
        for sym, p in current_holdings_map.items():
            if sym in ("CASH", "USD") or sym in protected_winners:
                continue
            cand_score = candidate_score_map.get(sym)
            score_val = cand_score.alpha_elasticity_score if cand_score else 0.40
            mval = float(p.get("market_value", 0.0) or 0.0)
            holding_scores.append({
                "ticker": sym,
                "score": score_val,
                "market_value": mval,
            })

        # Sort holdings ascending (lowest score candidate to swap out first)
        holding_scores.sort(key=lambda x: x["score"])

        # Check top candidates for swap opportunities
        top_candidates = [c for c in scored_candidates if c.ticker not in current_holdings_map and c.alpha_elasticity_score >= 0.70]
        swap_count = 0

        for h in holding_scores:
            if swap_count >= max_swaps or not top_candidates:
                break

            cand = top_candidates[0]
            edge = cand.alpha_elasticity_score - h["score"]

            # Friction check
            friction_hurdle = 0.003 * 2.5 + min_edge  # roundtrip friction + minimum excess hurdle
            if edge >= friction_hurdle:
                swap_amount = min(h["market_value"], total_nlv * 0.10)
                if swap_amount >= 100.0:
                    approved_swaps.append({
                        "sell_ticker": h["ticker"],
                        "buy_ticker": cand.ticker,
                        "swap_amount": round(swap_amount, 2),
                        "holding_score": round(h["score"], 3),
                        "candidate_score": round(cand.alpha_elasticity_score, 3),
                        "net_edge": round(edge, 3),
                        "reason": f"[{phase.value}] 汰弱換強：賣出低彈性標的 {h['ticker']} (分={h['score']:.2f}) 換入領先標的 {cand.ticker} (分={cand.alpha_elasticity_score:.2f}, 淨優勢={edge*100:.1f}%)",
                    })
                    rebalance_orders.append({
                        "action": "SELL",
                        "ticker": h["ticker"],
                        "amount": round(swap_amount, 2),
                        "weight": round(swap_amount / total_nlv, 4),
                        "strategy_name": STRATEGY_NAME,
                        "confidence_score": 8.0,
                        "reason": f"汰弱換強釋放資本：{h['ticker']} -> {cand.ticker}",
                    })
                    rebalance_orders.append({
                        "action": "BUY",
                        "ticker": cand.ticker,
                        "amount": round(swap_amount, 2),
                        "weight": round(swap_amount / total_nlv, 4),
                        "strategy_name": STRATEGY_NAME,
                        "confidence_score": round(cand.alpha_elasticity_score * 10, 1),
                        "reason": f"汰弱換強承接建倉：{cand.ticker} <- {h['ticker']}",
                    })
                    cand.recommended_action = "SWAP_TARGET"
                    top_candidates.pop(0)
                    swap_count += 1

        return TacticalRotationPlan(
            phase=phase,
            phase_rationale=phase_rationale,
            available_deployment_cash=cash_balance,
            total_portfolio_value=total_nlv,
            asset_scores=scored_candidates,
            rebalance_orders=rebalance_orders,
            swaps_approved=approved_swaps,
        )


class TacticalFactorRotationContract:
    """
    Contract wrapper adapting TacticalFactorRotationService to the generalized StrategyContract interface.
    """
    def __init__(self, rotation_service: Optional[TacticalFactorRotationService] = None):
        from src.domain.strategy_contract import StrategyContract, MarketRegimeType, RiskBudget
        self.strategy_id = STRATEGY_NAME
        self.rotation_service = rotation_service or TacticalFactorRotationService()
        self.subscribed_regimes = [
            MarketRegimeType.TREND_ACCELERATION,
            MarketRegimeType.VOLATILITY_PIVOT,
            MarketRegimeType.NORMAL,
        ]
        self.risk_budget = RiskBudget(
            max_underlying_stop_pct=8.0,
            trailing_stop_pct=5.0,
            max_position_margin_pct=0.20,
            max_holding_days=60,
            max_portfolio_gross_leverage=1.20,
            max_allowed_leverage=1,
        )

    def evaluate_entry(self, market_context: Dict[str, Any]):
        from src.domain.strategy_contract import StrategyExecutionPlan
        vix = market_context.get("vix", 20.0)
        vix_val = float(vix) if vix is not None else 20.0
        vix_z = float(market_context.get("vix_z_score", 0.0) or 0.0)
        spy_price = float(market_context.get("spy_price", 0.0) or 0.0)
        spy_sma200 = float(market_context.get("spy_sma200", 0.0) or 0.0)
        portfolio = market_context.get("portfolio") or {}
        candidate_data = market_context.get("candidate_data") or {}

        plan = self.rotation_service.evaluate_rotation_plan(
            portfolio=portfolio,
            candidate_data=candidate_data,
            vix=vix_val,
            vix_z_score=vix_z,
            spy_price=spy_price,
            spy_sma200=spy_sma200,
        )

        buy_orders = [o for o in plan.rebalance_orders if o.get("action") == "BUY"]
        if buy_orders:
            target_weight = sum(o.get("weight", 0.0) for o in buy_orders)
            top_ticker = buy_orders[0].get("ticker", "TOP_ALPHA")
            return StrategyExecutionPlan(
                action="BUY",
                stage=1,
                target_leverage=1,
                target_cumulative_weight=min(0.30, target_weight),
                incremental_weight=min(0.20, target_weight),
                stop_loss_pct=6.0,
                take_profit_pct=20.0,
                is_trailing_stop_loss=True,
                reason=f"[{plan.phase.value}] 波段輪動建倉 {top_ticker}: {plan.phase_rationale}",
            )
        return None

    def evaluate_exit(self, position: Any, market_context: Dict[str, Any]):
        from src.domain.strategy_contract import StrategyExecutionPlan
        # Exit or trim when asset falls out of top conviction during rotation
        sym = getattr(position, "symbol", None) or (position.get("symbol") if isinstance(position, dict) else None)
        underperforming = market_context.get("underperforming_tickers", [])
        if sym and sym in underperforming:
            return StrategyExecutionPlan(
                action="PARTIAL_EXIT",
                stage=0,
                target_leverage=1,
                target_cumulative_weight=0.0,
                incremental_weight=0.0,
                reason=f"多因子波段輪動汰換：{sym} 評分落後，釋放資本換庫至強勢 Alpha 標的",
            )
        return None

    def is_safety_control(self) -> bool:
        return False
