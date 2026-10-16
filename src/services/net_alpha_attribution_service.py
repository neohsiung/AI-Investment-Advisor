"""
Net Alpha & Cash Drag Attribution Service
=========================================
實時淨 Alpha 歸因與現金拖累量化服務

核心職責：
1. 精算扣除模型調用與 SaaS 訂閱成本後之真實「淨 Alpha (Net Alpha)」：
   Net Alpha = (R_portfolio - R_SPY) - (LLM_Costs + SaaS_Costs) / E_0 - Trading_Friction
2. 驗證年化淨報酬是否達成超越標普 500 (SPY) +10% 之財務目標。
3. 量化「現金拖累折損 (Cash Drag) vs 防守期權價值 (Cash Put Value)」：
   - 現金機會成本 (Cash Drag)：衡量若把閒置現金投入儲備候選池龍頭股能獲得的預期超額收益。
   - 現金防守價值 (Downside Protected)：在大盤回檔時，高現金比例帶來的 MDD 壓縮與 Beta 減免。
   - 動態給出五級現金健康度評級 (OPTIMAL_DEFENSE, BALANCED_DEPLOYING, EXCESS_DRAG_WARNING 等)。
4. 支援 0-LLM 指令 `/alpha` 與每日戰報雙渠道推播 (Telegram HTML + Email nl2br)。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import pytz

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("NetAlphaAttributionService")


@dataclass
class CashDragMetrics:
    """現金機會成本與防守期權價值指標"""
    total_cash_usd: float                     # 當前總現金 (USD)
    cash_ratio_pct: float                     # 現金佔投組比率 (0.62 = 62.0%)
    defensive_reserve_pct: float              # 剛性防禦現金門檻 (0.20 = 20.0%)
    defensive_reserve_usd: float              # 剛性防禦現金金額 (USD)
    excess_idle_cash_usd: float               # 超額閒置現金 (USD)
    risk_free_rate_pct: float                 # 基準無風險年化利率 (0.048 = 4.8%)
    period_risk_free_return_pct: float        # 當期無風險回報率
    contenders_benchmark_return_pct: float    # 候選池 Contenders 當期平均回報率
    cash_drag_usd: float                      # 現金機會成本折損金額 (USD)
    cash_drag_pct: float                      # 現金機會成本佔總權益比率
    downside_saved_usd: float                 # 大盤下跌時現金挽回之虧損 (USD)
    downside_saved_pct: float                 # 大盤下跌時現金挽回佔總權益比率
    net_cash_protection_usd: float            # 淨防守貢獻 (downside_saved - cash_drag)
    cash_health_rating: str                   # 現金健康度評級
    health_rationale: str                     # 評級原因說明

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cash_usd": round(self.total_cash_usd, 2),
            "cash_ratio_pct": round(self.cash_ratio_pct * 100.0, 2),
            "defensive_reserve_pct": round(self.defensive_reserve_pct * 100.0, 1),
            "defensive_reserve_usd": round(self.defensive_reserve_usd, 2),
            "excess_idle_cash_usd": round(self.excess_idle_cash_usd, 2),
            "risk_free_rate_pct": round(self.risk_free_rate_pct * 100.0, 2),
            "period_risk_free_return_pct": round(self.period_risk_free_return_pct * 100.0, 2),
            "contenders_benchmark_return_pct": round(self.contenders_benchmark_return_pct * 100.0, 2),
            "cash_drag_usd": round(self.cash_drag_usd, 2),
            "cash_drag_pct": round(self.cash_drag_pct * 100.0, 2),
            "downside_saved_usd": round(self.downside_saved_usd, 2),
            "downside_saved_pct": round(self.downside_saved_pct * 100.0, 2),
            "net_cash_protection_usd": round(self.net_cash_protection_usd, 2),
            "cash_health_rating": self.cash_health_rating,
            "health_rationale": self.health_rationale,
        }


@dataclass
class NetAlphaAttributionReport:
    """全景淨 Alpha 財務與成本歸因報表"""
    user_id: str
    lookback_days: int
    initial_capital_usd: float                # 初始存入本金 (E_0)
    current_equity_usd: float                 # 當前總權益 (E_t)
    portfolio_pnl_usd: float                  # 累計名義盈虧 (E_t - E_0)
    portfolio_return_pct: float               # 投組當期報酬率
    spy_return_pct: float                     # 大盤 SPY 同期基準報酬率
    gross_alpha_pct: float                    # 毛超額報酬率 (Portfolio - SPY)
    llm_cost_usd: float                       # 累積 AI 模型推理調用花費 (USD)
    saas_subscription_cost_usd: float         # 軟體與資料訂閱攤提費用 (USD)
    total_cost_usd: float                     # 總運營與模型成本 (USD)
    cost_drag_pct: float                      # 成本折損率 (Total_Cost / E_0)
    net_alpha_pct: float                      # 當期實時淨 Alpha (Gross - Cost_Drag)
    annualized_net_alpha_pct: float           # 年化淨 Alpha
    target_annual_alpha_pct: float            # 目標年化超額 (預設 +10.0%)
    alpha_target_gap_pct: float               # 與目標差距 (Annualized_Net - Target)
    is_beating_target: bool                   # 是否達成年化超越大盤 10%
    cash_metrics: CashDragMetrics             # 現金分析指標
    # Data-quality markers (never silently substitute a plausible number).
    # 資料品質標記：任何代換都必須可被呼叫端看見。
    return_method: str = "point_in_time_fallback"   # "twr_snapshots" | "point_in_time_fallback"
    twr_days_used: int = 0                    # 納入 TWR 的有效日數
    excluded_days: List[str] = field(default_factory=list)  # 因異常被排除的日期
    annualization_reliable: bool = False      # 有效日數是否足以年化
    avg_equity_usd: float = 0.0               # 成本拖累所用之分母（視窗平均權益）
    data_quality_notes: List[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "lookback_days": self.lookback_days,
            "initial_capital_usd": round(self.initial_capital_usd, 2),
            "current_equity_usd": round(self.current_equity_usd, 2),
            "portfolio_pnl_usd": round(self.portfolio_pnl_usd, 2),
            "portfolio_return_pct": round(self.portfolio_return_pct * 100.0, 2),
            "spy_return_pct": round(self.spy_return_pct * 100.0, 2),
            "gross_alpha_pct": round(self.gross_alpha_pct * 100.0, 2),
            "llm_cost_usd": round(self.llm_cost_usd, 4),
            "saas_subscription_cost_usd": round(self.saas_subscription_cost_usd, 2),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "cost_drag_pct": round(self.cost_drag_pct * 100.0, 2),
            "net_alpha_pct": round(self.net_alpha_pct * 100.0, 2),
            "annualized_net_alpha_pct": round(self.annualized_net_alpha_pct * 100.0, 2),
            "target_annual_alpha_pct": round(self.target_annual_alpha_pct * 100.0, 1),
            "alpha_target_gap_pct": round(self.alpha_target_gap_pct * 100.0, 2),
            "is_beating_target": self.is_beating_target,
            "cash_metrics": self.cash_metrics.to_dict(),
            "return_method": self.return_method,
            "twr_days_used": self.twr_days_used,
            "excluded_days": list(self.excluded_days),
            "annualization_reliable": self.annualization_reliable,
            "avg_equity_usd": round(self.avg_equity_usd, 2),
            "data_quality_notes": list(self.data_quality_notes),
            "created_at": self.created_at,
        }


MAX_ABS_DAILY_RETURN = 0.5      # a >50% single-day move is treated as bad data / 單日 >50% 視為壞資料
MIN_DAYS_FOR_ANNUALIZATION = 20  # fewer valid days -> annualized figure is noise / 少於此日數年化無意義


def compute_twr(
    navs: List[Tuple[Any, float]],
    flows: Optional[Dict[Any, float]] = None,
    max_abs_daily: float = MAX_ABS_DAILY_RETURN,
) -> Tuple[float, int, List[str]]:
    """
    Time-weighted return from ordered (date, NAV) points, neutralising deposits/withdrawals
    (`flows[date]` = net external flow booked on that date). Days whose implied return is
    implausible (|r| > max_abs_daily) or whose base NAV is non-positive are excluded and
    reported, never silently included.
    由有序 (日期, NAV) 計算時間加權報酬，排除當日外部資金進出；
    隱含報酬不合理（|r|>上限）或前值非正的日子會被排除並回報，不會默默納入。
    Returns (twr, valid_days, excluded_dates).
    """
    flows = flows or {}
    growth = 1.0
    used = 0
    excluded: List[str] = []
    for i in range(1, len(navs)):
        d, nav = navs[i]
        prev_nav = navs[i - 1][1]
        if prev_nav is None or nav is None or prev_nav <= 0:
            excluded.append(str(d))
            continue
        r = (nav - flows.get(d, 0.0)) / prev_nav - 1.0
        if abs(r) > max_abs_daily:
            excluded.append(str(d))
            continue
        growth *= 1.0 + r
        used += 1
    return growth - 1.0, used, excluded


class NetAlphaAttributionService:
    """
    實時淨 Alpha 歸因與現金拖累量化服務
    """

    DEFAULT_INITIAL_CAPITAL_USD = 1711.00
    DEFAULT_ANNUAL_TARGET_ALPHA = 0.10        # +10% 年化打贏大盤
    DEFAULT_RISK_FREE_RATE = 0.048            # 4.8% 美國 3 個月國庫券無風險利率
    DEFAULT_DEFENSIVE_CASH_PCT = 0.20         # 20% 剛性防禦儲備

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Any = None,
        broker: Any = None,
        market_data_service: Any = None,
        token_logger_service: Any = None,
        snapshot_loader: Any = None,
        flow_loader: Any = None,
    ):
        # snapshot_loader(user_id, since_date) -> [(date, nav)]; flow_loader(user_id, since_date) -> {date: usd}
        self.snapshot_loader = snapshot_loader
        self.flow_loader = flow_loader
        self.user_id = resolve_user_id(user_id)
        self.settings_service = settings_service
        self.broker = broker
        self.market_data_service = market_data_service
        self.token_logger_service = token_logger_service

    async def _get_settings_service(self) -> Any:
        if self.settings_service:
            return self.settings_service
        from src.services.settings_service import SettingsService
        self.settings_service = SettingsService(user_id=self.user_id)
        return self.settings_service

    async def _get_broker(self) -> Any:
        if self.broker:
            return self.broker
        from src.services.broker_factory import BrokerFactory
        self.broker = BrokerFactory.get_broker(self.user_id)
        return self.broker

    async def _get_market_data_service(self) -> Any:
        if self.market_data_service:
            return self.market_data_service
        from src.services.market_data_service import MarketDataService
        self.market_data_service = MarketDataService(user_id=self.user_id)
        return self.market_data_service

    async def _get_token_logger_service(self) -> Any:
        if self.token_logger_service:
            return self.token_logger_service
        from src.services.token_logger_service import TokenLoggerService
        self.token_logger_service = TokenLoggerService()
        return self.token_logger_service

    # ═══════════════════════════════════════════════════════════════════════
    # 1. 核心歸因計算 (Core Net Alpha & Cash Drag Attribution)
    # ═══════════════════════════════════════════════════════════════════════

    def _load_snapshots(self, since: Any) -> List[Tuple[Any, float]]:
        if self.snapshot_loader:
            return list(self.snapshot_loader(self.user_id, since))
        from sqlalchemy import text
        from src.data.database import get_db_engine
        with get_db_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT date, MAX(total_nlv) AS nav FROM daily_snapshots "
                    "WHERE user_id = :uid AND date >= :since AND total_nlv IS NOT NULL "
                    "GROUP BY date ORDER BY date ASC"
                ),
                {"uid": self.user_id, "since": since},
            ).fetchall()
        return [(r[0], float(r[1])) for r in rows]

    def _load_flows(self, since: Any) -> Dict[Any, float]:
        if self.flow_loader:
            return dict(self.flow_loader(self.user_id, since))
        from sqlalchemy import text
        from src.data.database import get_db_engine
        with get_db_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT trade_date, SUM(CASE WHEN action = 'WITHDRAWAL' THEN -amount ELSE amount END) "
                    "FROM transactions WHERE user_id = :uid AND entry_category = 'capital_flow' "
                    "AND trade_date >= :since GROUP BY trade_date"
                ),
                {"uid": self.user_id, "since": since},
            ).fetchall()
        return {r[0]: float(r[1]) for r in rows}

    async def calculate_complete_report(
        self,
        lookback_days: int = 30,
    ) -> NetAlphaAttributionReport:
        """
        全量計算淨 Alpha 財務報表與現金拖累指標
        """
        settings_svc = await self._get_settings_service()
        broker = await self._get_broker()
        mkt_svc = await self._get_market_data_service()
        token_svc = await self._get_token_logger_service()

        # 1. 取得初始本金與目標
        initial_capital = self.DEFAULT_INITIAL_CAPITAL_USD
        target_alpha = self.DEFAULT_ANNUAL_TARGET_ALPHA
        monthly_saas = 0.0
        if settings_svc:
            try:
                init_val = settings_svc.get_setting("initial_capital_deposited_usd")
                if init_val is not None and float(init_val) > 0:
                    initial_capital = float(init_val)
                target_val = settings_svc.get_setting("target_annual_net_alpha_pct")
                if target_val is not None:
                    target_alpha = float(target_val)
                # Canonical key is monthly_data_subscription_cost_usd; the legacy
                # monthly_saas_* key is honoured only when the canonical one is unset.
                # 標準鍵為 monthly_data_subscription_cost_usd；舊鍵僅在標準鍵未設時沿用。
                saas_val = settings_svc.get_setting("monthly_data_subscription_cost_usd")
                if saas_val is None:
                    saas_val = settings_svc.get_setting("monthly_saas_subscription_cost_usd")
                if saas_val is not None:
                    monthly_saas = float(saas_val)
            except Exception as e:
                logger.debug("Failed reading settings for attribution: %s", e)

        # 2. 取得帳戶當前權益與現金
        current_equity = initial_capital
        available_cash = 0.0
        if broker:
            try:
                account = await broker.get_account()
                current_equity = float(getattr(account, "total_equity", 0.0) or initial_capital)
                available_cash = float(getattr(account, "available_cash", 0.0) or 0.0)
            except Exception as be:
                logger.warning("Failed to get broker account for attribution: %s", be)

        # Only broker-anchored snapshots are trustworthy; earlier ones were derived from a
        # drifting local ledger (2026-10 audit). Window = max(lookback, valid_since).
        # 僅採用券商錨定後的快照；視窗取 lookback 與 valid_since 的較晚者。
        from datetime import date as _d, timedelta as _t
        window_start = _d.today() - _t(days=lookback_days)
        valid_since_raw = None
        bounded_by_valid_since = False
        if settings_svc:
            try:
                valid_since_raw = settings_svc.get_setting("net_alpha_valid_since")
            except Exception as e:
                logger.warning("net_alpha_valid_since unreadable (%s); using lookback window", e)
        if valid_since_raw:
            try:
                vs = _d.fromisoformat(str(valid_since_raw)[:10])
                if vs > window_start:
                    window_start = vs
                    bounded_by_valid_since = True
            except ValueError:
                logger.warning("Invalid net_alpha_valid_since=%r; ignored", valid_since_raw)
        eff_days = max(1, (_d.today() - window_start).days)

        portfolio_pnl = current_equity - initial_capital
        portfolio_return = portfolio_pnl / max(1.0, initial_capital)
        return_method = "point_in_time_fallback"
        twr_days = 0
        excluded_days: List[str] = []
        avg_equity = current_equity
        notes: List[str] = []
        try:
            from datetime import date as _date, timedelta as _td
            # Base day must itself be trusted when bounded by valid_since.
            # 受 valid_since 限制時，基準日本身也必須可信，故不再往前多取一天。
            since = window_start if bounded_by_valid_since else window_start - _td(days=1)
            navs = self._load_snapshots(since)
            flows = self._load_flows(since)
            if len(navs) >= 2:
                twr, twr_days, excluded_days = compute_twr(navs, flows)
                if twr_days >= 1:
                    portfolio_return = twr
                    return_method = "twr_snapshots"
                    # Exclude the same implausible days so one bad snapshot cannot inflate the denominator.
                    # 排除同樣的異常日，避免單筆壞快照撐大分母。
                    valid_navs = [n for d, n in navs if n and n > 0 and str(d) not in excluded_days]
                    avg_equity = sum(valid_navs) / len(valid_navs) if valid_navs else current_equity
                    portfolio_pnl = portfolio_return * avg_equity
            if return_method != "twr_snapshots":
                notes.append("Fewer than 2 usable snapshots in window; using point-in-time return vs initial capital.")
        except Exception as e:
            logger.warning("TWR snapshot load failed (%s); falling back to point-in-time return", e)
            notes.append(f"Snapshot load failed: {e}; using point-in-time return vs initial capital.")
        if excluded_days:
            notes.append(f"Excluded implausible snapshot days: {', '.join(excluded_days)}")
        if return_method == "point_in_time_fallback":
            avg_equity = initial_capital

        # 3. 取得 SPY 大盤基準報酬率
        spy_return = 0.0
        try:
            spy_df = mkt_svc.get_history_df("SPY", days=max(10, eff_days + 5))
            if spy_df is not None and not spy_df.empty:
                # Align SPY to the same window as the portfolio TWR when dates are available.
                # 若有日期索引，將 SPY 對齊至與投組 TWR 相同的視窗。
                try:
                    import pandas as _pd
                    _cut = _pd.Timestamp(window_start)
                    _idx = _pd.to_datetime(spy_df.index, errors="coerce")
                    _sub = spy_df[_idx >= _cut]
                    if len(_sub) >= 2:
                        spy_df = _sub
                except Exception as _e:
                    logger.warning("SPY window alignment skipped: %s", _e)
            if spy_df is not None and not spy_df.empty and len(spy_df) >= 2:
                close_col = "Close" if "Close" in spy_df.columns else ("close" if "close" in spy_df.columns else None)
                if close_col is not None:
                    closes = spy_df[close_col].dropna().values
                    if len(closes) >= 2:
                        p_start = float(closes[0])
                        p_end = float(closes[-1])
                        if p_start > 0:
                            spy_return = (p_end - p_start) / p_start
        except Exception as se:
            logger.warning("Failed calculating SPY return: %s", se)

        gross_alpha = portfolio_return - spy_return

        # 4. 取得 AI 模型花費與 SaaS 成本攤提
        llm_cost = 0.0
        try:
            spending = token_svc.get_user_spending(self.user_id, days=eff_days)
            llm_cost = float(spending.get("total_cost", 0.0) or 0.0)
        except Exception as te:
            logger.debug("Failed querying user spending: %s", te)

        saas_cost = monthly_saas * (eff_days / 30.0)
        total_cost = llm_cost + saas_cost
        cost_drag = total_cost / max(1.0, avg_equity)

        net_alpha = gross_alpha - cost_drag
        annualized_factor = 365.0 / max(1, eff_days)
        annualized_net_alpha = net_alpha * annualized_factor
        alpha_target_gap = annualized_net_alpha - target_alpha
        annualization_reliable = (
            return_method == "twr_snapshots" and twr_days >= MIN_DAYS_FOR_ANNUALIZATION
        )
        if not annualization_reliable:
            notes.append(
                f"Annualized figure unreliable (valid days={twr_days}, need >={MIN_DAYS_FOR_ANNUALIZATION}); "
                "is_beating_target forced False."
            )
        is_beating = annualization_reliable and annualized_net_alpha >= target_alpha

        # 5. 精算現金機會成本 (Cash Drag) 與防守期權價值 (Cash Put Value)
        cash_metrics = await self._calculate_cash_drag_metrics(
            current_equity=current_equity,
            available_cash=available_cash,
            spy_return=spy_return,
            lookback_days=eff_days,
            mkt_svc=mkt_svc,
        )

        return NetAlphaAttributionReport(
            user_id=self.user_id,
            lookback_days=eff_days,
            initial_capital_usd=initial_capital,
            current_equity_usd=current_equity,
            portfolio_pnl_usd=portfolio_pnl,
            portfolio_return_pct=portfolio_return,
            spy_return_pct=spy_return,
            gross_alpha_pct=gross_alpha,
            llm_cost_usd=llm_cost,
            saas_subscription_cost_usd=saas_cost,
            total_cost_usd=total_cost,
            cost_drag_pct=cost_drag,
            net_alpha_pct=net_alpha,
            annualized_net_alpha_pct=annualized_net_alpha,
            target_annual_alpha_pct=target_alpha,
            alpha_target_gap_pct=alpha_target_gap,
            is_beating_target=is_beating,
            cash_metrics=cash_metrics,
            return_method=return_method,
            twr_days_used=twr_days,
            excluded_days=excluded_days,
            annualization_reliable=annualization_reliable,
            avg_equity_usd=avg_equity,
            data_quality_notes=notes,
        )

    async def _calculate_cash_drag_metrics(
        self,
        current_equity: float,
        available_cash: float,
        spy_return: float,
        lookback_days: int,
        mkt_svc: Any,
    ) -> CashDragMetrics:
        """
        度量現金之機會成本與防守期權價值
        """
        cash_ratio = available_cash / max(1.0, current_equity)
        defensive_pct = self.DEFAULT_DEFENSIVE_CASH_PCT
        defensive_usd = current_equity * defensive_pct
        excess_idle = max(0.0, available_cash - defensive_usd)

        rf_rate = self.DEFAULT_RISK_FREE_RATE
        period_rf = rf_rate * (lookback_days / 365.0)

        # 取得候選池龍頭標的（或預設龍頭組合）之平均報酬率作為機會成本參照
        contenders_return = 0.0
        contender_tickers = ["MSFT", "MU", "AMD", "NVDA", "AAPL"]
        try:
            from src.repositories.ticker_universe_repository import TickerUniverseRepository
            repo = TickerUniverseRepository()
            candidates = repo.get_all(self.user_id, status="candidate")
            if candidates:
                cand_syms = [c.ticker for c in candidates if getattr(c, "ticker", "")]
                if cand_syms:
                    contender_tickers = cand_syms[:5]
        except Exception as ce:
            logger.debug("TickerUniverseRepository candidate lookup skipped: %s", ce)

        # 計算候選標的平均報酬率
        returns_list: List[float] = []
        for sym in contender_tickers[:3]:
            try:
                df = mkt_svc.get_history_df(sym, days=max(10, lookback_days + 5))
                if df is not None and not df.empty and len(df) >= 2:
                    close_col = "Close" if "Close" in df.columns else ("close" if "close" in df.columns else None)
                    if close_col is not None:
                        closes = df[close_col].dropna().values
                        if len(closes) >= 2 and float(closes[0]) > 0:
                            r = (float(closes[-1]) - float(closes[0])) / float(closes[0])
                            returns_list.append(r)
            except Exception:
                continue

        if returns_list:
            contenders_return = sum(returns_list) / len(returns_list)
        else:
            contenders_return = max(0.0, spy_return)

        # 現金機會成本 (Cash Drag)：只有在候選股超越無風險利率時才構成實質機會成本
        excess_opportunity = max(0.0, contenders_return - period_rf)
        cash_drag_usd = excess_idle * excess_opportunity
        cash_drag_pct = cash_drag_usd / max(1.0, current_equity)

        # 下行防守保護價值 (Cash Put Value)：大盤下跌時，現金成功防禦之折算價值
        downside_saved_usd = 0.0
        downside_saved_pct = 0.0
        if spy_return < 0.0:
            downside_saved_usd = available_cash * abs(spy_return)
            downside_saved_pct = downside_saved_usd / max(1.0, current_equity)

        net_cash_protection = downside_saved_usd - cash_drag_usd

        # 判定現金健康度評級
        if cash_ratio <= defensive_pct + 0.05:
            rating = "HEALTHY_DEPLOYED"
            rationale = "現金水位維持在 20%~25% 防守基準，資本運用效率優異。"
        elif spy_return < -0.01 and downside_saved_usd >= cash_drag_usd:
            rating = "OPTIMAL_DEFENSE"
            rationale = "市場處於回檔避險週期，高現金帶來顯著下行保護，防守價值超越機會成本。"
        elif cash_ratio > 0.40 and contenders_return > 0.03 and cash_drag_usd > downside_saved_usd:
            rating = "EXCESS_DRAG_WARNING"
            rationale = f"標的池強勢上漲 (+{contenders_return*100:.1f}%) 但閒置現金偏高 ({cash_ratio*100:.1f}%)，產生顯著機會成本拖累。"
        else:
            rating = "BALANCED_DEPLOYING"
            rationale = "現金比例充裕，分批建倉與主力階梯限價吸籌有序推進中。"

        return CashDragMetrics(
            total_cash_usd=available_cash,
            cash_ratio_pct=cash_ratio,
            defensive_reserve_pct=defensive_pct,
            defensive_reserve_usd=defensive_usd,
            excess_idle_cash_usd=excess_idle,
            risk_free_rate_pct=rf_rate,
            period_risk_free_return_pct=period_rf,
            contenders_benchmark_return_pct=contenders_return,
            cash_drag_usd=cash_drag_usd,
            cash_drag_pct=cash_drag_pct,
            downside_saved_usd=downside_saved_usd,
            downside_saved_pct=downside_saved_pct,
            net_cash_protection_usd=net_cash_protection,
            cash_health_rating=rating,
            health_rationale=rationale,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 2. 格式化排版 (Telegram Safe HTML & Email nl2br)
    # ═══════════════════════════════════════════════════════════════════════

    def format_telegram_report(self, report: NetAlphaAttributionReport) -> str:
        """
        產生符合 Telegram 規範的安全 HTML 戰報
        """
        pnl_sign = "+" if report.portfolio_pnl_usd >= 0 else ""
        ret_sign = "+" if report.portfolio_return_pct >= 0 else ""
        spy_sign = "+" if report.spy_return_pct >= 0 else ""
        gross_sign = "+" if report.gross_alpha_pct >= 0 else ""
        net_sign = "+" if report.net_alpha_pct >= 0 else ""
        ann_sign = "+" if report.annualized_net_alpha_pct >= 0 else ""
        gap_sign = "+" if report.alpha_target_gap_pct >= 0 else ""

        target_badge = "🏆 <b>達成年化超額 +10%</b>" if report.is_beating_target else "⏳ <b>蓄力追趕目標中</b>"

        rating_emoji_map = {
            "HEALTHY_DEPLOYED": "🟢",
            "OPTIMAL_DEFENSE": "🛡️",
            "BALANCED_DEPLOYING": "⚖️",
            "EXCESS_DRAG_WARNING": "⚠️",
        }
        rating_emoji = rating_emoji_map.get(report.cash_metrics.cash_health_rating, "ℹ️")

        lines = [
            f"📊 <b>【實時淨 Alpha 歸因與現金拖累儀表 ({report.lookback_days} 天期)】</b>",
            "━━━━━━━━━━━━━━━━━━",
            f"• <b>初始本金</b>：<code>${report.initial_capital_usd:,.2f} USD</code>",
            f"• <b>當前權益</b>：<code>${report.current_equity_usd:,.2f} USD</code> ({pnl_sign}${report.portfolio_pnl_usd:,.2f})",
            f"• <b>投組回報</b>：<code>{ret_sign}{report.portfolio_return_pct*100:.2f}%</code> vs <b>SPY 大盤</b>：<code>{spy_sign}{report.spy_return_pct*100:.2f}%</code>",
            f"• <b>毛超額報酬 (Gross Alpha)</b>：<code>{gross_sign}{report.gross_alpha_pct*100:.2f}%</code>",
            "━━━━━━━━━━━━━━━━━━",
            "💸 <b>【模型與營運成本扣除明細】</b>",
            f"• <b>LLM 模型推理花費</b>：<code>${report.llm_cost_usd:.4f} USD</code>",
            f"• <b>SaaS/資料訂閱攤提</b>：<code>${report.saas_subscription_cost_usd:.2f} USD</code>",
            f"• <b>總運營成本折損率</b>：<code>-{report.cost_drag_pct*100:.2f}%</code> (總計: <code>${report.total_cost_usd:.4f} USD</code>)",
            "━━━━━━━━━━━━━━━━━━",
            "🎯 <b>【扣費後實時淨 Alpha 財務指標】</b>",
            f"• <b>當期實時淨 Alpha</b>：<code>{net_sign}{report.net_alpha_pct*100:.2f}%</code>",
            f"• <b>折合年化淨 Alpha</b>：<code>{ann_sign}{report.annualized_net_alpha_pct*100:.2f}%</code>",
            f"• <b>距年化 +10% 目標</b>：<code>{gap_sign}{report.alpha_target_gap_pct*100:.2f}%</code> | {target_badge}",
            "━━━━━━━━━━━━━━━━━━",
            f"{rating_emoji} <b>【現金配置度量與機會成本分析】</b>",
            f"• <b>總現金餘額</b>：<code>${report.cash_metrics.total_cash_usd:,.2f} USD</code> (<b>{report.cash_metrics.cash_ratio_pct*100:.1f}%</b>)",
            f"• <b>剛性防守儲備</b>：<code>${report.cash_metrics.defensive_reserve_usd:,.2f} USD</code> ({report.cash_metrics.defensive_reserve_pct*100:.0f}%)",
            f"• <b>超額閒置現金</b>：<code>${report.cash_metrics.excess_idle_cash_usd:,.2f} USD</code>",
            f"• <b>現金拖累 (機會成本)</b>：<code>-${report.cash_metrics.cash_drag_usd:.2f} USD</code> (折損 <code>-{report.cash_metrics.cash_drag_pct*100:.2f}%</code>)",
            f"• <b>下行防守保護價值</b>：<code>+${report.cash_metrics.downside_saved_usd:.2f} USD</code> (抗跌 <code>+{report.cash_metrics.downside_saved_pct*100:.2f}%</code>)",
            f"• <b>現金健康度狀態</b>：<b>[{report.cash_metrics.cash_health_rating}]</b>",
            f"  └ <i>{report.cash_metrics.health_rationale}</i>",
            "━━━━━━━━━━━━━━━━━━",
            "💡 <i>輸入 <code>/dipbuy plan</code> 檢視限價吸籌點位，輸入 <code>/universe</code> 檢視候選池。</i>",
        ]
        return "\n".join(lines)

    def format_email_report(self, report: NetAlphaAttributionReport) -> str:
        """
        產生符合 Email 排版規範的 Markdown / HTML 報告 (nl2br)
        """
        return self.format_telegram_report(report)

    async def dispatch_attribution_alert(
        self,
        report: NetAlphaAttributionReport,
    ) -> bool:
        """
        透過 NotificationService 發送雙渠道歸因戰報
        """
        try:
            from src.services.notification_service import NotificationService
            notif = NotificationService()
            html_msg = self.format_telegram_report(report)
            await notif.notify_all(
                title=f"📊 實時淨 Alpha 歸因與現金拖累儀表 ({report.lookback_days}D)",
                message=html_msg,
                priority="NORMAL",
            )
            return True
        except Exception as e:
            logger.error("Failed to dispatch attribution alert: %s", e)
            return False
