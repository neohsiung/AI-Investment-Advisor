"""
Friction-Aware Tranche Sizing Service (Phase 63B).

Implements:
1. Turnover Friction Hurdle Engine:
   - Quantifies bid-ask spread, adverse execution slippage, and broker fees into total round-trip turnover friction.
   - Evaluates whether net excess return (Net Alpha = Delta Alpha - Turnover Friction) exceeds the hurdle threshold (default 0.80% / 80 bps).
   - Rejects or skips unremunerative rebalancing and micro-rotations that only burn commissions and spread.
2. Core (70%) vs Satellite (30%) Tranche Segregation:
   - Partitions every holding into a long-term Core Tranche (70%) and tactical Satellite Tranche (30%).
   - Core Tranche is strictly locked under primary trend conditions to compound without being shaken out.
   - Satellite Tranche actively participates in Limit Ladder accumulation, GEX pinning, and Kalman pairs arbitrage.
   - Routine non-emergency sells are capped strictly by the satellite tranche balance, shielding core capital.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logger import setup_logger
from src.config.owner import resolve_user_id

logger = setup_logger("FrictionAwareTrancheSizingService")


@dataclass
class TrancheAllocation:
    ticker: str
    total_shares: float
    core_shares: float
    satellite_shares: float
    core_ratio: float
    satellite_ratio: float
    max_sellable_satellite_shares: float
    is_core_locked: bool
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "total_shares": self.total_shares,
            "core_shares": self.core_shares,
            "satellite_shares": self.satellite_shares,
            "core_ratio": self.core_ratio,
            "satellite_ratio": self.satellite_ratio,
            "max_sellable_satellite_shares": self.max_sellable_satellite_shares,
            "is_core_locked": self.is_core_locked,
            "notes": self.notes,
        }


@dataclass
class FrictionHurdleMetric:
    ticker: str
    action: str
    proposed_shares: float
    current_price: float
    estimated_spread_pct: float
    estimated_slippage_pct: float
    estimated_fee_pct: float
    round_trip_friction_pct: float
    raw_alpha_gain_pct: float
    net_alpha_pct: float
    hurdle_threshold_pct: float
    passed_hurdle: bool
    tranche_info: TrancheAllocation
    adjusted_shares: float
    decision: str
    reason: str
    spread_source: str = "STATIC_LOOKUP"
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "action": self.action,
            "proposed_shares": self.proposed_shares,
            "current_price": self.current_price,
            "estimated_spread_pct": self.estimated_spread_pct,
            "estimated_slippage_pct": self.estimated_slippage_pct,
            "estimated_fee_pct": self.estimated_fee_pct,
            "round_trip_friction_pct": self.round_trip_friction_pct,
            "raw_alpha_gain_pct": self.raw_alpha_gain_pct,
            "net_alpha_pct": self.net_alpha_pct,
            "hurdle_threshold_pct": self.hurdle_threshold_pct,
            "passed_hurdle": self.passed_hurdle,
            "tranche_info": self.tranche_info.to_dict(),
            "adjusted_shares": self.adjusted_shares,
            "decision": self.decision,
            "reason": self.reason,
            "spread_source": self.spread_source,
            "evaluated_at": self.evaluated_at,
        }


@dataclass
class TrancheDriftReport:
    """
    Tranche Drift Auto-Healing Evaluation Report (Phase 64A).
    Tracks deviation of actual core/satellite ratios from the target 70/30 baseline
    and recommends rebalancing actions outside the tolerance band.
    """
    ticker: str
    current_price: float
    total_shares: float
    current_core_shares: float
    current_satellite_shares: float
    current_core_ratio: float
    target_core_ratio: float
    tolerance_pct: float
    drift_pct: float
    drift_state: str  # "BALANCED", "CORE_EXPANDED", "CORE_DEFICIT"
    action_recommendation: str  # "HOLD", "TRIM_CORE_TO_SATELLITE", "TOP_UP_CORE_FROM_SATELLITE"
    rebalance_shares: float
    rebalance_usd: float
    round_trip_friction_pct: float
    estimated_friction_usd: float
    is_healing_viable: bool
    notes: str = ""
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "current_price": self.current_price,
            "total_shares": self.total_shares,
            "current_core_shares": self.current_core_shares,
            "current_satellite_shares": self.current_satellite_shares,
            "current_core_ratio": self.current_core_ratio,
            "target_core_ratio": self.target_core_ratio,
            "tolerance_pct": self.tolerance_pct,
            "drift_pct": self.drift_pct,
            "drift_state": self.drift_state,
            "action_recommendation": self.action_recommendation,
            "rebalance_shares": self.rebalance_shares,
            "rebalance_usd": self.rebalance_usd,
            "round_trip_friction_pct": self.round_trip_friction_pct,
            "estimated_friction_usd": self.estimated_friction_usd,
            "is_healing_viable": self.is_healing_viable,
            "notes": self.notes,
            "evaluated_at": self.evaluated_at,
        }



class FrictionAwareTrancheSizingService:
    """
    Market-Maker Friction Cost & Core/Satellite Tranche Segregation Service.
    """

    DEFAULT_MIN_FRICTION_HURDLE_PCT = 0.008  # 0.80% (80 bps)
    DEFAULT_CORE_TRANCHE_RATIO = 0.70       # 70% Core
    DEFAULT_SATELLITE_TRANCHE_RATIO = 0.30  # 30% Satellite
    DEFAULT_SLIPPAGE_PCT = 0.0010           # 0.10% (10 bps)
    DEFAULT_DRIFT_TOLERANCE_PCT = 0.05      # 5% buffer (65% ~ 75%)

    # Typical bid-ask spreads for major liquid assets
    SPREAD_MAP: Dict[str, float] = {
        "SPY": 0.0002,   # 0.02%
        "QQQ": 0.0003,   # 0.03%
        "NVDA": 0.0005,  # 0.05%
        "AAPL": 0.0004,  # 0.04%
        "MSFT": 0.0004,  # 0.04%
        "AMD": 0.0006,   # 0.06%
        "META": 0.0005,  # 0.05%
        "TSLA": 0.0006,  # 0.06%
        "AMZN": 0.0005,  # 0.05%
        "GOOGL": 0.0005, # 0.05%
        "MU": 0.0008,    # 0.08%
        "TSM": 0.0008,   # 0.08%
    }

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = resolve_user_id(user_id)
        self._cfg = None

    def _load_config(self) -> Dict[str, Any]:
        if self._cfg is not None:
            return self._cfg
        cfg = {
            "enable_friction_aware_tranche_sizing": True,
            "min_friction_hurdle_pct": self.DEFAULT_MIN_FRICTION_HURDLE_PCT,
            "core_tranche_ratio": self.DEFAULT_CORE_TRANCHE_RATIO,
            "satellite_tranche_ratio": self.DEFAULT_SATELLITE_TRANCHE_RATIO,
            "enable_tranche_auto_healing": True,
            "tranche_drift_tolerance_pct": self.DEFAULT_DRIFT_TOLERANCE_PCT,
            "enable_live_spread_feed": True,
        }
        try:
            from src.services.settings_service import SettingsService

            stored = SettingsService(user_id=self.user_id).get_all_settings() or {}
            for k, default_val in list(cfg.items()):
                if k in stored and stored[k] not in (None, ""):
                    if isinstance(default_val, bool):
                        cfg[k] = str(stored[k]).strip().lower() in ("true", "1", "yes")
                    elif isinstance(default_val, float):
                        cfg[k] = float(stored[k])
                    elif isinstance(default_val, int):
                        cfg[k] = int(stored[k])
                    else:
                        cfg[k] = stored[k]
        except Exception as e:
            logger.debug("Failed to load settings in FrictionAwareTrancheSizingService: %s", e)
        self._cfg = cfg
        return cfg

    async def is_enabled(self) -> bool:
        cfg = self._load_config()
        return bool(cfg.get("enable_friction_aware_tranche_sizing", True))

    def resolve_spread_and_friction(
        self, ticker: str, live_spread_pct: Optional[float] = None
    ) -> Tuple[float, float, float, float, str]:
        """
        Resolve spread, slippage, fee, total round-trip turnover friction, and spread source (Phase 64B).
        Returns: (spread_pct, slippage_pct, fee_pct, round_trip_friction_pct, spread_source)
        """
        sym = ticker.upper().strip()
        cfg = self._load_config()
        enable_live = bool(cfg.get("enable_live_spread_feed", True))

        if enable_live and live_spread_pct is not None and live_spread_pct > 0:
            spread_pct = float(live_spread_pct)
            spread_source = "LIVE_ORDERBOOK"
        else:
            spread_pct = self.SPREAD_MAP.get(sym, 0.0012)
            spread_source = "STATIC_LOOKUP"

        slippage_pct = self.DEFAULT_SLIPPAGE_PCT      # 0.10%
        fee_pct = 0.0000                              # 0% stock commission

        # Round-trip friction = 2 * (Spread/2 + Slippage) + Fee
        round_trip_friction = 2.0 * (spread_pct / 2.0 + slippage_pct) + fee_pct
        return spread_pct, slippage_pct, fee_pct, round_trip_friction, spread_source

    def estimate_round_trip_friction(
        self, ticker: str, live_spread_pct: Optional[float] = None
    ) -> Tuple[float, float, float, float]:
        """
        Estimate spread, slippage, fee, and total round-trip turnover friction.
        Returns: (spread_pct, slippage_pct, fee_pct, round_trip_friction_pct)
        """
        spread_pct, slippage_pct, fee_pct, friction, _ = self.resolve_spread_and_friction(
            ticker, live_spread_pct
        )
        return spread_pct, slippage_pct, fee_pct, friction

    def calculate_tranche_allocation(
        self,
        ticker: str,
        total_shares: float,
        is_emergency_stop: bool = False,
    ) -> TrancheAllocation:
        """
        Partition holding into Core (70%) and Satellite (30%) tranches.
        """
        sym = ticker.upper().strip()
        cfg = self._load_config()
        core_ratio = float(cfg.get("core_tranche_ratio", self.DEFAULT_CORE_TRANCHE_RATIO))
        satellite_ratio = float(cfg.get("satellite_tranche_ratio", self.DEFAULT_SATELLITE_TRANCHE_RATIO))

        # Normalize ratios if needed
        total_ratio = core_ratio + satellite_ratio
        if abs(total_ratio - 1.0) > 1e-4 and total_ratio > 0:
            core_ratio = core_ratio / total_ratio
            satellite_ratio = satellite_ratio / total_ratio

        total_sh = max(0.0, float(total_shares or 0.0))
        core_sh = round(total_sh * core_ratio, 4)
        sat_sh = round(total_sh * satellite_ratio, 4)

        if is_emergency_stop:
            max_sellable = total_sh
            notes = "Emergency stop loss active: full liquidation permitted across all tranches."
            is_locked = False
        else:
            max_sellable = sat_sh
            notes = f"Routine operation: capped at satellite tranche ({satellite_ratio*100:.0f}%). Core tranche ({core_ratio*100:.0f}%) locked."
            is_locked = True

        return TrancheAllocation(
            ticker=sym,
            total_shares=total_sh,
            core_shares=core_sh,
            satellite_shares=sat_sh,
            core_ratio=core_ratio,
            satellite_ratio=satellite_ratio,
            max_sellable_satellite_shares=max_sellable,
            is_core_locked=is_locked,
            notes=notes,
        )

    def evaluate_tranche_drift(
        self,
        ticker: str,
        current_price: float,
        total_shares: float,
        current_core_shares: Optional[float] = None,
        live_spread_pct: Optional[float] = None,
    ) -> TrancheDriftReport:
        """
        Evaluate portfolio tranche drift and healing requirements (Phase 64A).
        Checks whether actual core allocation deviates from target 70% beyond
        the allowable tolerance band (default +/- 5%, i.e. 65% ~ 75%).
        """
        sym = ticker.upper().strip()
        price = max(0.01, float(current_price or 1.0))
        total_sh = max(0.0, float(total_shares or 0.0))

        cfg = self._load_config()
        core_target_ratio = float(cfg.get("core_tranche_ratio", self.DEFAULT_CORE_TRANCHE_RATIO))
        tolerance_pct = float(cfg.get("tranche_drift_tolerance_pct", self.DEFAULT_DRIFT_TOLERANCE_PCT))

        if current_core_shares is not None:
            core_sh = min(total_sh, max(0.0, float(current_core_shares)))
        else:
            core_sh = round(total_sh * core_target_ratio, 4)
        sat_sh = max(0.0, round(total_sh - core_sh, 4))

        core_ratio = core_sh / total_sh if total_sh > 0 else core_target_ratio
        drift_pct = core_ratio - core_target_ratio

        lower_bound = max(0.0, core_target_ratio - tolerance_pct)
        upper_bound = min(1.0, core_target_ratio + tolerance_pct)

        if total_sh <= 0:
            drift_state = "BALANCED"
            action = "HOLD"
            rebal_sh = 0.0
            notes = "目前無持倉部位，無需自癒調倉。"
        elif core_ratio > upper_bound:
            drift_state = "CORE_EXPANDED"
            action = "TRIM_CORE_TO_SATELLITE"
            target_core_sh = round(total_sh * core_target_ratio, 4)
            rebal_sh = max(0.0, round(core_sh - target_core_sh, 4))
            notes = (
                f"核心持倉佔比膨脹 ({core_ratio*100:.1f}% > {upper_bound*100:.1f}%)，"
                f"建議將 {rebal_sh:.4f} 股利潤溢出轉移至衛星戰術池，使核心回歸 {core_target_ratio*100:.0f}%。"
            )
        elif core_ratio < lower_bound:
            drift_state = "CORE_DEFICIT"
            action = "TOP_UP_CORE_FROM_SATELLITE"
            target_core_sh = round(total_sh * core_target_ratio, 4)
            rebal_sh = max(0.0, round(target_core_sh - core_sh, 4))
            notes = (
                f"核心底倉佔比不足 ({core_ratio*100:.1f}% < {lower_bound*100:.1f}%)，"
                f"建議從衛星戰術池提撥 {rebal_sh:.4f} 股歸入核心長線底倉，鞏固複利護城河。"
            )
        else:
            drift_state = "BALANCED"
            action = "HOLD"
            rebal_sh = 0.0
            notes = (
                f"核心持倉佔比 ({core_ratio*100:.1f}%) 位於容差帶 [{lower_bound*100:.0f}%, {upper_bound*100:.0f}%] 內，"
                f"無需微調，杜絕換手摩擦損耗。"
            )

        rebal_usd = round(rebal_sh * price, 2)
        _, _, _, friction_pct, _ = self.resolve_spread_and_friction(sym, live_spread_pct)
        estimated_fric_usd = round(rebal_usd * friction_pct, 2)

        is_viable = (drift_state != "BALANCED") and (rebal_usd >= 10.0)

        return TrancheDriftReport(
            ticker=sym,
            current_price=price,
            total_shares=total_sh,
            current_core_shares=core_sh,
            current_satellite_shares=sat_sh,
            current_core_ratio=round(core_ratio, 4),
            target_core_ratio=round(core_target_ratio, 4),
            tolerance_pct=round(tolerance_pct, 4),
            drift_pct=round(drift_pct, 4),
            drift_state=drift_state,
            action_recommendation=action,
            rebalance_shares=rebal_sh,
            rebalance_usd=rebal_usd,
            round_trip_friction_pct=round(friction_pct, 6),
            estimated_friction_usd=estimated_fric_usd,
            is_healing_viable=is_viable,
            notes=notes,
        )

    def auto_heal_tranche_drift(
        self,
        ticker: str,
        current_price: float,
        total_shares: float,
        current_core_shares: Optional[float] = None,
        dry_run: bool = True,
        live_spread_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute or simulate tranche drift auto-healing (Phase 64A).
        """
        report = self.evaluate_tranche_drift(
            ticker=ticker,
            current_price=current_price,
            total_shares=total_shares,
            current_core_shares=current_core_shares,
            live_spread_pct=live_spread_pct,
        )

        if report.action_recommendation == "TRIM_CORE_TO_SATELLITE":
            new_core_sh = round(report.current_core_shares - report.rebalance_shares, 4)
            new_sat_sh = round(report.current_satellite_shares + report.rebalance_shares, 4)
        elif report.action_recommendation == "TOP_UP_CORE_FROM_SATELLITE":
            new_core_sh = round(report.current_core_shares + report.rebalance_shares, 4)
            new_sat_sh = round(report.current_satellite_shares - report.rebalance_shares, 4)
        else:
            new_core_sh = report.current_core_shares
            new_sat_sh = report.current_satellite_shares

        post_core_ratio = new_core_sh / report.total_shares if report.total_shares > 0 else report.target_core_ratio

        return {
            "ticker": report.ticker,
            "dry_run": dry_run,
            "status": "PROPOSED" if dry_run else "EXECUTED",
            "action": report.action_recommendation,
            "drift_state": report.drift_state,
            "rebalance_shares": report.rebalance_shares,
            "rebalance_usd": report.rebalance_usd,
            "estimated_friction_usd": report.estimated_friction_usd,
            "is_healing_viable": report.is_healing_viable,
            "pre_healing": {
                "core_shares": report.current_core_shares,
                "satellite_shares": report.current_satellite_shares,
                "core_ratio": report.current_core_ratio,
            },
            "post_healing": {
                "core_shares": new_core_sh,
                "satellite_shares": new_sat_sh,
                "core_ratio": round(post_core_ratio, 4),
            },
            "report": report.to_dict(),
            "summary": report.notes,
        }

    async def evaluate_order_friction_and_tranche(
        self,
        ticker: str,
        action: str,
        quantity: float,
        current_price: Optional[float] = None,
        delta_weight: Optional[float] = None,
        strategy_name: Optional[str] = None,
        total_held_shares: Optional[float] = None,
        expected_alpha_pct: Optional[float] = None,
        live_spread_pct: Optional[float] = None,
    ) -> FrictionHurdleMetric:
        """
        Evaluate proposed order against the turnover friction hurdle and tranche bounds.
        """
        sym = ticker.upper().strip()
        act = action.upper().strip()
        strat = str(strategy_name or "").lower()
        qty = max(0.0, float(quantity or 1.0))
        price = float(current_price) if current_price and current_price > 0 else 100.0

        cfg = self._load_config()
        hurdle_thresh = float(cfg.get("min_friction_hurdle_pct", self.DEFAULT_MIN_FRICTION_HURDLE_PCT))

        is_emergency = any(
            k in strat
            for k in (
                "stop_loss",
                "trailing_stop_loss",
                "trailing_stop",
                "emergency_exit",
                "emergency_liquidation",
                "circuit_breaker",
            )
        )

        spread_pct, slippage_pct, fee_pct, friction_pct, spread_source = self.resolve_spread_and_friction(
            sym, live_spread_pct
        )

        # Expected alpha estimate:
        # If delta_weight provided, small weight changes generally have modest expected alpha (e.g. 0.5% ~ 1.5%)
        # If not provided, fallback to 1.2% baseline
        if expected_alpha_pct is not None:
            raw_alpha = float(expected_alpha_pct)
        elif delta_weight is not None:
            raw_alpha = max(0.002, abs(float(delta_weight)) * 0.20)
        else:
            raw_alpha = 0.015  # 1.50% default alpha expectation

        net_alpha = raw_alpha - friction_pct

        # Resolve current position shares for tranche check
        held_sh = float(total_held_shares) if total_held_shares is not None else qty
        tranche_alloc = self.calculate_tranche_allocation(
            sym, total_shares=held_sh, is_emergency_stop=is_emergency
        )

        # Hurdle Check:
        # Emergency stops, cash deployments, or new entries are exempt from turnover friction blocking
        is_routine_rebalance = any(k in strat for k in ("rebalance", "rotation", "churn", "routine"))
        is_exempt_from_hurdle = is_emergency or ("deploy" in strat) or ("open" in strat) or (not is_routine_rebalance and delta_weight is None)

        passed_hurdle = True
        adjusted_shares = qty
        decision = "PERMITTED"
        reason = "Order cleared friction hurdle and tranche allocation bounds."

        if not is_exempt_from_hurdle and net_alpha < hurdle_thresh:
            passed_hurdle = False
            decision = "BLOCKED_BY_FRICTION"
            reason = (
                f"[TurnoverFriction] Order blocked: Net Alpha {net_alpha*100:+.2f}% is below hurdle "
                f"{hurdle_thresh*100:.2f}% (Friction: {friction_pct*100:.2f}%, Raw Alpha: {raw_alpha*100:.2f}%). "
                f"Eliminates unremunerative churn."
            )

        # Tranche Sizing Check on SELL:
        elif act in ("SELL", "TRIM", "REDUCE") and not is_emergency:
            if qty > tranche_alloc.max_sellable_satellite_shares and held_sh > 0:
                # Exceeds satellite limit: Clamp or reject
                excess_sh = qty - tranche_alloc.max_sellable_satellite_shares
                if tranche_alloc.max_sellable_satellite_shares > 0:
                    adjusted_shares = tranche_alloc.max_sellable_satellite_shares
                    decision = "CLAMPED_TO_SATELLITE"
                    reason = (
                        f"[TrancheSizing] Sell quantity clamped from {qty:.4f} to {adjusted_shares:.4f} shares. "
                        f"70% core tranche ({tranche_alloc.core_shares:.4f} shares) is shielded from routine exit."
                    )
                else:
                    passed_hurdle = False
                    decision = "BLOCKED_BY_CORE_TRANCHE"
                    reason = (
                        f"[TrancheSizing] Sell blocked: 70% Core Tranche ({tranche_alloc.core_shares:.4f} shares) is locked. "
                        f"Zero satellite shares available for non-emergency sale."
                    )

        return FrictionHurdleMetric(
            ticker=sym,
            action=act,
            proposed_shares=qty,
            current_price=price,
            estimated_spread_pct=spread_pct,
            estimated_slippage_pct=slippage_pct,
            estimated_fee_pct=fee_pct,
            round_trip_friction_pct=friction_pct,
            raw_alpha_gain_pct=raw_alpha,
            net_alpha_pct=net_alpha,
            hurdle_threshold_pct=hurdle_thresh,
            passed_hurdle=passed_hurdle,
            tranche_info=tranche_alloc,
            adjusted_shares=adjusted_shares,
            decision=decision,
            reason=reason,
            spread_source=spread_source,
        )

    def format_tranche_report(
        self,
        metric: FrictionHurdleMetric,
        drift_report: Optional[TrancheDriftReport] = None,
    ) -> str:
        """
        Format clean, HTML/Markdown compliant telemetry report for /tranche command.
        """
        sym = metric.ticker
        tr = metric.tranche_info
        status_badge = "✅ <b>通過摩擦審查 (CLEARED)</b>" if metric.passed_hurdle else "⚠️ <b>觸發摩擦阻斷/裁減 (RESTRICTED)</b>"
        spread_source_badge = "⚡ 實時盤口注入 (LIVE_ORDERBOOK)" if getattr(metric, "spread_source", "STATIC_LOOKUP") == "LIVE_ORDERBOOK" else "📚 靜態流動性表 (STATIC_LOOKUP)"

        # Auto-compute drift if not provided and position exists
        drift = drift_report
        if drift is None and tr.total_shares > 0:
            try:
                drift = self.evaluate_tranche_drift(
                    ticker=sym,
                    current_price=metric.current_price,
                    total_shares=tr.total_shares,
                    current_core_shares=tr.core_shares,
                )
            except Exception:
                drift = None

        lines = [
            f"⚖️ <b>【做市商摩擦成本與核心/衛星倉位分級儀表 (Phase 63B/64A)】</b>",
            "━━━━━━━━━━━━━━━━━━",
            f"• <b>監控標的</b>：<code>{sym}</code> | 現價：<code>${metric.current_price:.2f}</code>",
            f"• <b>風控審查狀態</b>：{status_badge}",
            f"• <b>審定決策</b>：<code>{metric.decision}</code>",
            f"• <b>決策理由</b>：<i>{metric.reason}</i>",
            "━━━━━━━━━━━━━━━━━━",
            "<b>【70/30 核心底倉 vs 衛星波段分級隔離】</b>",
            f"• <b>總持倉股數</b>：<code>{tr.total_shares:.4f}</code> 股",
            f"• <b>🛡️ 70% 核心底倉 (Core)</b>：<code>{tr.core_shares:.4f}</code> 股 (鎖定長期複利，不參與短波折騰)",
            f"• <b>🚀 30% 衛星波段 (Satellite)</b>：<code>{tr.satellite_shares:.4f}</code> 股 (支援限價階梯吸籌與極值套利)",
            f"• <b>常規最大可賣股數</b>：<code>{tr.max_sellable_satellite_shares:.4f}</code> 股",
            f"• <b>核心持倉鎖定狀態</b>：{'🔒 核心鎖定保護中' if tr.is_core_locked else '🔓 緊急全額放行'}",
        ]

        if drift is not None:
            drift_badge_map = {
                "BALANCED": "⚖️ 平衡健康 (BALANCED)",
                "CORE_EXPANDED": "⚠️ 核心超額膨脹 (CORE_EXPANDED)",
                "CORE_DEFICIT": "⚠️ 核心底倉不足 (CORE_DEFICIT)",
            }
            d_badge = drift_badge_map.get(drift.drift_state, drift.drift_state)
            lines.extend([
                "━━━━━━━━━━━━━━━━━━",
                "<b>【核心/衛星動態漂移自癒監控 (Phase 64A)】</b>",
                f"• <b>核心持倉佔比</b>：<code>{drift.current_core_ratio*100:.1f}%</code> (目標: <code>{drift.target_core_ratio*100:.0f}%</code> | 容差: <code>±{drift.tolerance_pct*100:.1f}%</code>)",
                f"• <b>部位漂移率 (Drift)</b>：<code>{drift.drift_pct*100:+.2f}%</code>",
                f"• <b>漂移平衡狀態</b>：{d_badge}",
                f"• <b>自癒處置建議</b>：<code>{drift.action_recommendation}</code>",
                f"• <b>自癒微調指引</b>：<i>{drift.notes}</i>",
            ])

        lines.extend([
            "━━━━━━━━━━━━━━━━━━",
            "<b>【做市商換手摩擦損耗與淨超額 Alpha 矩陣】</b>",
            f"• <b>盤口價差來源</b>：{spread_source_badge}",
            f"• <b>預估買賣點差 (Spread)</b>：<code>{metric.estimated_spread_pct*100:.3f}%</code> (雙向: <code>{metric.estimated_spread_pct*100:.3f}%</code>)",
            f"• <b>預估衝擊滑點 (Slippage)</b>：<code>{metric.estimated_slippage_pct*100:.3f}%</code>",
            f"• <b>雙向總摩擦損耗 (Friction)</b>：<code>{metric.round_trip_friction_pct*100:.3f}%</code> ({metric.round_trip_friction_pct*10000:.1f} bps)",
            f"• <b>預期毛超額回報 (Gross Alpha)</b>：<code>{metric.raw_alpha_gain_pct*100:+.2f}%</code>",
            f"• <b>預期淨超額回報 (Net Alpha)</b>：<code>{metric.net_alpha_pct*100:+.2f}%</code>",
            f"• <b>最低換手門檻 (Hurdle Threshold)</b>：<code>{metric.hurdle_threshold_pct*100:.2f}%</code> ({metric.hurdle_threshold_pct*10000:.0f} bps)",
            "━━━━━━━━━━━━━━━━━━",
            "🛡️ <b>分級倉位與摩擦感知防護機制</b>：",
            "• 淨超額報酬 (Net Alpha) 必須顯著高於雙向摩擦成本 (預設 80 bps)，方放行換手調倉。",
            "• 核心 70% 部位杜絕常規止盈與微幅調倉拋售，由制度性護城河保護長線複利。",
            "• 30% 衛星部位承載戰術波段與低吸套利，遇硬性停損 (Stop Loss) 則 100% 部位可無阻礙避險出場。",
        ])
        return "\n".join(lines)

    def format_drift_heal_report(self, heal_res: Dict[str, Any]) -> str:
        """
        Format clean, HTML/Markdown compliant telemetry report for /tranche heal command (Phase 64A).
        """
        ticker = heal_res.get("ticker", "UNKNOWN")
        dry_run = heal_res.get("dry_run", True)
        action = heal_res.get("action", "HOLD")
        drift_state = heal_res.get("drift_state", "BALANCED")
        rebal_sh = heal_res.get("rebalance_shares", 0.0)
        rebal_usd = heal_res.get("rebalance_usd", 0.0)
        fric_usd = heal_res.get("estimated_friction_usd", 0.0)
        is_viable = heal_res.get("is_healing_viable", False)
        pre = heal_res.get("pre_healing", {})
        post = heal_res.get("post_healing", {})
        summary = heal_res.get("summary", "")

        status_badge = "🧪 <b>自癒模擬試算 (DRY RUN)</b>" if dry_run else "⚡ <b>自癒執行完成 (EXECUTED)</b>"
        viable_badge = "✅ <b>具備自癒經濟效益</b>" if is_viable else "ℹ️ <b>無顯著摩擦溢價 (無效益或處於容差帶)</b>"

        lines = [
            f"🩹 <b>【核心/衛星動態漂移自癒執行報告 (Phase 64A)】</b>",
            "━━━━━━━━━━━━━━━━━━",
            f"• <b>標的代號</b>：<code>{ticker}</code> | 執行模式：{status_badge}",
            f"• <b>漂移狀態評定</b>：<code>{drift_state}</code>",
            f"• <b>自癒處置動作</b>：<code>{action}</code>",
            f"• <b>效益經濟審查</b>：{viable_badge}",
            "━━━━━━━━━━━━━━━━━━",
            "<b>【部位再平衡調配計畫】</b>",
            f"• <b>調整轉移股數</b>：<code>{rebal_sh:.4f}</code> 股 (約合 <code>${rebal_usd:.2f} USD</code>)",
            f"• <b>預估摩擦損耗</b>：<code>${fric_usd:.2f} USD</code>",
            f"• <b>自癒前核心持倉</b>：<code>{pre.get('core_shares', 0.0):.4f}</code> 股 ({pre.get('core_ratio', 0.70)*100:.1f}%)",
            f"• <b>自癒後核心持倉</b>：<code>{post.get('core_shares', 0.0):.4f}</code> 股 ({post.get('core_ratio', 0.70)*100:.1f}%)",
            f"• <b>自癒前衛星持倉</b>：<code>{pre.get('satellite_shares', 0.0):.4f}</code> 股",
            f"• <b>自癒後衛星持倉</b>：<code>{post.get('satellite_shares', 0.0):.4f}</code> 股",
            "━━━━━━━━━━━━━━━━━━",
            f"📋 <b>執行總結</b>：<i>{summary}</i>",
        ]
        return "\n".join(lines)
