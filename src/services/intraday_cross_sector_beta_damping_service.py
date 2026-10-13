"""
Intraday Cross-Sector Correlation & Beta Damping Service (Phase 58)
==================================================================
跨板塊標的即時波動率相關性動態阻尼引擎

核心架構：
1. 標的與大盤基準 (SPY) 滾動協方差、方差、Beta 與相關性計算：
   - 歷史基準序列 (15~30 天日線)：計算基礎 Beta 與 Pearson 相關性
   - 日內即時報價 (Last, Open, Previous Close)：計算當日即時報酬率與相對強度 (RS)
   - 動態融合：有效 Beta 結合歷史回歸與日內動能確認
2. 4 級即時體制識別 (Beta Regimes)：
   - DEFENSIVE_DECOUPLED (低貝塔解耦): beta <= 0.75 and corr <= 0.40 (Multiplier: 1.15x, BOOST_STALKING)
   - NEUTRAL_BALANCED (中性平衡): 0.75 < beta < 1.25 (Multiplier: 1.00x, STANDARD_STALKING)
   - CONTAGION_AMPLIFIED (高貝塔傳染): beta >= 1.25 或 (beta > 1.0 且 corr >= 0.75) (Multiplier: 0.60x ~ 0.85x, DAMP_STALKING)
   - MARKET_STRESS_DAMPED (大盤跳水剛性阻尼): SPY 日內跌幅 <= -1.2% 且 beta >= 0.85 (Hard Damping: 0.50x, FREEZE_STALKING)
3. 整合 StaggeredDipBuyingService：
   - 14:00 盤中追單改價時動態調節折價收斂速度 (BOOST / STANDARD / DAMP / FREEZE)
   - 15:50 尾盤 MOC 接管時動態縮放執行金額，保護現金
4. 0-LLM 數理優先，輸出符合 Telegram HTML + Email nl2br 雙渠道格式標準。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import inspect
import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("IntradayCrossSectorBetaDampingService")


@dataclass
class IntradayBetaMetric:
    """單一跨板塊標的之即時貝塔與相關性阻尼指標"""
    ticker: str
    benchmark_ticker: str
    beta: float
    correlation: float
    intraday_return_pct: float
    benchmark_return_pct: float
    relative_strength_pct: float
    regime: str  # DEFENSIVE_DECOUPLED, NEUTRAL_BALANCED, CONTAGION_AMPLIFIED, MARKET_STRESS_DAMPED
    damping_factor: float  # 0.50 ~ 1.15
    stalking_action: str   # BOOST_STALKING, STANDARD_STALKING, DAMP_STALKING, FREEZE_STALKING
    rationale: str
    is_cross_sector_injected: bool = True
    injected_sector: Optional[str] = None
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "benchmark_ticker": self.benchmark_ticker,
            "beta": round(self.beta, 4),
            "correlation": round(self.correlation, 4),
            "intraday_return_pct": round(self.intraday_return_pct, 4),
            "benchmark_return_pct": round(self.benchmark_return_pct, 4),
            "relative_strength_pct": round(self.relative_strength_pct, 4),
            "regime": self.regime,
            "damping_factor": round(self.damping_factor, 4),
            "stalking_action": self.stalking_action,
            "rationale": self.rationale,
            "is_cross_sector_injected": self.is_cross_sector_injected,
            "injected_sector": self.injected_sector,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IntradayBetaMetric:
        return cls(
            ticker=str(data.get("ticker", "")),
            benchmark_ticker=str(data.get("benchmark_ticker", "SPY")),
            beta=float(data.get("beta", 1.0) or 1.0),
            correlation=float(data.get("correlation", 0.5) or 0.5),
            intraday_return_pct=float(data.get("intraday_return_pct", 0.0) or 0.0),
            benchmark_return_pct=float(data.get("benchmark_return_pct", 0.0) or 0.0),
            relative_strength_pct=float(data.get("relative_strength_pct", 0.0) or 0.0),
            regime=str(data.get("regime", "NEUTRAL_BALANCED")),
            damping_factor=float(data.get("damping_factor", 1.0) or 1.0),
            stalking_action=str(data.get("stalking_action", "STANDARD_STALKING")),
            rationale=str(data.get("rationale", "")),
            is_cross_sector_injected=bool(data.get("is_cross_sector_injected", True)),
            injected_sector=data.get("injected_sector"),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


class IntradayCrossSectorBetaDampingService:
    """跨板塊標的即時波動率相關性動態阻尼服務"""

    DEFAULT_BENCHMARK = "SPY"
    DEFAULT_CONTAGION_BETA_THRESHOLD = 1.25     # 高貝塔傳染門檻 (>= 1.25)
    DEFAULT_DECOUPLED_BETA_THRESHOLD = 0.75     # 低貝塔解耦防守門檻 (<= 0.75)
    DEFAULT_CORRELATION_CONTAGION_THRESHOLD = 0.75  # 相關性傳染門檻 (>= 0.75)
    DEFAULT_CORRELATION_DECOUPLED_THRESHOLD = 0.40  # 相關性解耦門檻 (<= 0.40)
    DEFAULT_MARKET_STRESS_DRAWDOWN_PCT = -1.2       # 大盤跳水觸發點 (-1.2%)

    REDIS_CACHE_TTL_SECONDS = 300               # 快取 5 分鐘
    REDIS_KEY_PREFIX = "cross_sector:beta_damping"

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        market_data_service: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        from src.services.settings_service import SettingsService
        self.settings_service = settings_service or SettingsService(user_id=self.user_id)
        self.market_data_service = market_data_service

    def _get_setting(self, key: str, default: Any) -> Any:
        try:
            return self.settings_service.get_setting(key, default)
        except Exception:
            return default

    @property
    def is_enabled(self) -> bool:
        return bool(self._get_setting("enable_cross_sector_beta_damping", True))

    @property
    def contagion_beta_threshold(self) -> float:
        return float(self._get_setting("beta_damping_contagion_threshold", self.DEFAULT_CONTAGION_BETA_THRESHOLD))

    @property
    def decoupled_beta_threshold(self) -> float:
        return float(self._get_setting("beta_damping_decoupled_threshold", self.DEFAULT_DECOUPLED_BETA_THRESHOLD))

    @property
    def correlation_contagion_threshold(self) -> float:
        return float(self._get_setting("beta_damping_correlation_threshold", self.DEFAULT_CORRELATION_CONTAGION_THRESHOLD))

    @property
    def market_stress_drawdown_pct(self) -> float:
        return float(self._get_setting("beta_damping_market_stress_drawdown_pct", self.DEFAULT_MARKET_STRESS_DRAWDOWN_PCT))

    async def _get_market_data_service(self) -> Any:
        if self.market_data_service:
            return self.market_data_service
        try:
            from src.services.market_data_service import MarketDataService
            self.market_data_service = MarketDataService(user_id=self.user_id)
            return self.market_data_service
        except Exception as me:
            logger.debug("Could not resolve MarketDataService: %s", me)
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # 1. 歷史 Beta 與 Pearson 相關性精算
    # ═══════════════════════════════════════════════════════════════════════

    def calculate_historical_beta_and_correlation(
        self,
        ticker_returns: List[float],
        benchmark_returns: List[float],
        default_beta: float = 1.0,
        default_corr: float = 0.50,
    ) -> Tuple[float, float]:
        """
        計算標的與大盤基準之歷史 Beta 與相關性：
        Beta = Cov(y, x) / Var(x)
        Corr = Cov(y, x) / (std_y * std_x)
        """
        try:
            if len(ticker_returns) >= 5 and len(benchmark_returns) >= 5:
                import numpy as np
                min_len = min(len(ticker_returns), len(benchmark_returns))
                y = np.array(ticker_returns[-min_len:], dtype=float)
                x = np.array(benchmark_returns[-min_len:], dtype=float)

                var_x = float(np.var(x, ddof=1))
                std_x = float(np.std(x, ddof=1))
                std_y = float(np.std(y, ddof=1))

                if var_x > 1e-7 and std_x > 1e-7 and std_y > 1e-7:
                    cov_xy = float(np.cov(y, x, ddof=1)[0, 1])
                    beta = float(cov_xy / var_x)
                    corr = float(cov_xy / (std_x * std_y))
                    return (
                        round(max(0.1, min(3.0, beta)), 4),
                        round(max(-1.0, min(1.0, corr)), 4),
                    )
        except Exception as e:
            logger.debug("Failed computing historical beta and correlation: %s", e)
        return (default_beta, default_corr)

    # ═══════════════════════════════════════════════════════════════════════
    # 2. 跨板塊標的即時評估 (evaluate_ticker_beta_damping)
    # ═══════════════════════════════════════════════════════════════════════

    async def evaluate_ticker_beta_damping(
        self,
        ticker: str,
        benchmark_ticker: str = DEFAULT_BENCHMARK,
        sector: Optional[str] = None,
        force_refresh: bool = False,
    ) -> IntradayBetaMetric:
        """
        評估標的與大盤之即時 Beta、相關性與動態阻尼決策。
        1. 檢查 Redis 快取。
        2. 抓取標的與基準歷史日線（計算歷史基準 Beta 與相關性）。
        3. 抓取日內即時報價（計算即時漲跌幅與相對強度 RS）。
        4. 融合有效 Beta，判定 4 級體制狀態機與阻尼係數。
        """
        clean_ticker = (ticker or "").upper().strip()
        clean_bench = (benchmark_ticker or self.DEFAULT_BENCHMARK).upper().strip()

        # 1. 檢查 Redis 快取
        if not force_refresh:
            try:
                from src.infrastructure.cache.redis_client import get_redis
                r = await get_redis(decode_responses=True)
                cache_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{clean_ticker}"
                cached = await r.get(cache_key)
                if cached:
                    return IntradayBetaMetric.from_dict(json.loads(cached))
            except Exception as ce:
                logger.debug("Redis lookup error in beta damping: %s", ce)

        mkt_svc = await self._get_market_data_service()

        # 2. 抓取歷史序列
        ticker_rets: List[float] = []
        bench_rets: List[float] = []

        if mkt_svc:
            try:
                df_t = mkt_svc.get_history_df(clean_ticker, days=30)
                if df_t is not None and not df_t.empty:
                    c_col = "Close" if "Close" in df_t.columns else ("close" if "close" in df_t.columns else None)
                    if c_col:
                        vals = df_t[c_col].dropna().values
                        if len(vals) >= 2:
                            ticker_rets = [float((vals[i] - vals[i-1]) / vals[i-1]) for i in range(1, len(vals))]

                df_b = mkt_svc.get_history_df(clean_bench, days=30)
                if df_b is not None and not df_b.empty:
                    c_col = "Close" if "Close" in df_b.columns else ("close" if "close" in df_b.columns else None)
                    if c_col:
                        vals = df_b[c_col].dropna().values
                        if len(vals) >= 2:
                            bench_rets = [float((vals[i] - vals[i-1]) / vals[i-1]) for i in range(1, len(vals))]
            except Exception as he:
                logger.debug("Failed fetching history for beta damping (%s/%s): %s", clean_ticker, clean_bench, he)

        hist_beta, hist_corr = self.calculate_historical_beta_and_correlation(ticker_rets, bench_rets)

        # 3. 抓取日內即時報價
        ticker_day_ret_pct = 0.0
        bench_day_ret_pct = 0.0

        if mkt_svc:
            try:
                # 標的報價
                t_quote_call = mkt_svc.get_quote(clean_ticker)
                t_quote = await t_quote_call if inspect.isawaitable(t_quote_call) else t_quote_call
                if t_quote:
                    chg = t_quote.get("change_pct")
                    if chg is not None:
                        ticker_day_ret_pct = float(chg) * 100.0 if abs(float(chg)) < 0.50 else float(chg)
                    else:
                        last_p = float(t_quote.get("last", 0.0) or t_quote.get("mid", 0.0) or 0.0)
                        open_p = float(t_quote.get("open", 0.0) or 0.0)
                        if last_p > 0 and open_p > 0:
                            ticker_day_ret_pct = ((last_p - open_p) / open_p) * 100.0

                # 基準報價 (SPY)
                b_quote_call = mkt_svc.get_quote(clean_bench)
                b_quote = await b_quote_call if inspect.isawaitable(b_quote_call) else b_quote_call
                if b_quote:
                    chg = b_quote.get("change_pct")
                    if chg is not None:
                        bench_day_ret_pct = float(chg) * 100.0 if abs(float(chg)) < 0.50 else float(chg)
                    else:
                        last_p = float(b_quote.get("last", 0.0) or b_quote.get("mid", 0.0) or 0.0)
                        open_p = float(b_quote.get("open", 0.0) or 0.0)
                        if last_p > 0 and open_p > 0:
                            bench_day_ret_pct = ((last_p - open_p) / open_p) * 100.0
            except Exception as qe:
                logger.debug("Failed fetching intraday quotes for %s/%s: %s", clean_ticker, clean_bench, qe)

        relative_strength_pct = round(ticker_day_ret_pct - bench_day_ret_pct, 4)

        # 4. 融合有效 Beta 與體制狀態機決策
        effective_beta = hist_beta
        if abs(bench_day_ret_pct) >= 0.20:
            intraday_implied_beta = ticker_day_ret_pct / bench_day_ret_pct
            clamped_implied = max(-0.5, min(2.5, intraday_implied_beta))
            effective_beta = 0.70 * hist_beta + 0.30 * max(0.1, clamped_implied)

        effective_beta = round(max(0.1, min(3.0, effective_beta)), 4)
        effective_corr = hist_corr

        # 5. 體制狀態機判定
        stress_mkt = self.market_stress_drawdown_pct
        contagion_beta = self.contagion_beta_threshold
        contagion_corr = self.correlation_contagion_threshold
        decoupled_beta = self.decoupled_beta_threshold
        decoupled_corr = self.DEFAULT_CORRELATION_DECOUPLED_THRESHOLD

        if bench_day_ret_pct <= stress_mkt and effective_beta >= 0.85:
            # 大盤重挫且標的高敏感 -> 剛性阻尼凍結追單
            regime = "MARKET_STRESS_DAMPED"
            damping_factor = 0.50
            stalking_action = "FREEZE_STALKING"
            rationale = (
                f"大盤急跌 ({bench_day_ret_pct:+.2f}%) 且標的貝塔 ({effective_beta:.2f}) 敏感；"
                f"啟動 0.50x 剛性阻尼並凍結向上追單，保護現金儲備"
            )
        elif effective_beta >= contagion_beta or (effective_beta >= 1.0 and effective_corr >= contagion_corr):
            # 高貝塔系統性傳染 -> 自適應阻尼縮小部位
            regime = "CONTAGION_AMPLIFIED"
            damping_factor = round(max(0.60, min(0.85, 1.0 / effective_beta)), 4)
            stalking_action = "DAMP_STALKING"
            rationale = (
                f"高貝塔系統性傳染 (Beta: {effective_beta:.2f} >= {contagion_beta:.2f}, 相關性: {effective_corr:.2f})；"
                f"啟動 {damping_factor:.2f}x 阻尼收縮掛單，防範接飛刀"
            )
        elif effective_beta <= decoupled_beta and effective_corr <= decoupled_corr:
            # 低貝塔解耦防守 -> 激勵向上追單吸籌
            regime = "DEFENSIVE_DECOUPLED"
            damping_factor = 1.15
            stalking_action = "BOOST_STALKING"
            rationale = (
                f"低貝塔與弱相關 (Beta: {effective_beta:.2f} <= {decoupled_beta:.2f}, 相關性: {effective_corr:.2f})；"
                f"具備真正防守多角化特性，啟動 1.15x 激勵追單以分散 HHI"
            )
        else:
            # 常規中性
            regime = "NEUTRAL_BALANCED"
            damping_factor = 1.00
            stalking_action = "STANDARD_STALKING"
            rationale = (
                f"貝塔 ({effective_beta:.2f}) 與相關性 ({effective_corr:.2f}) 處於正常中性區間；"
                f"維持標準 1.00x 追單改價"
            )

        metric = IntradayBetaMetric(
            ticker=clean_ticker,
            benchmark_ticker=clean_bench,
            beta=effective_beta,
            correlation=effective_corr,
            intraday_return_pct=round(ticker_day_ret_pct, 4),
            benchmark_return_pct=round(bench_day_ret_pct, 4),
            relative_strength_pct=relative_strength_pct,
            regime=regime,
            damping_factor=damping_factor,
            stalking_action=stalking_action,
            rationale=rationale,
            is_cross_sector_injected=True,
            injected_sector=sector,
        )

        # 寫入 Redis 快取
        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            cache_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{clean_ticker}"
            await r.setex(cache_key, self.REDIS_CACHE_TTL_SECONDS, json.dumps(metric.to_dict()))
        except Exception as we:
            logger.debug("Redis cache write error for beta metric: %s", we)

        return metric

    # ═══════════════════════════════════════════════════════════════════════
    # 3. 0-LLM 雙渠道戰報生成 (/betadamp 指令)
    # ═══════════════════════════════════════════════════════════════════════

    def format_beta_damping_report(
        self,
        metrics: List[IntradayBetaMetric],
        channel: str = "telegram",
    ) -> str:
        """
        產出符合 Telegram HTML 與 Email nl2br 雙渠道標準之貝塔阻尼儀表戰報。
        """
        if not metrics:
            return (
                "🛡️ <b>【跨板塊標的即時波動率相關性動態阻尼儀表】</b>\n"
                "• <i>今日暫無跨板塊自癒標的或無待評估訂單。</i>\n"
                "💡 <i>輸入 <code>/sector</code> 檢視板塊 HHI，輸入 <code>/batch</code> 檢視建倉計畫。</i>"
            )

        lines = [
            "🛡️ <b>【跨板塊標的即時波動率相關性動態阻尼儀表】</b>",
            "━━━━━━━━━━━━━━━━━━",
        ]

        for m in metrics:
            if m.regime == "DEFENSIVE_DECOUPLED":
                badge = "🟢 <b>低貝塔解耦 (DEFENSIVE_DECOUPLED)</b>"
            elif m.regime == "NEUTRAL_BALANCED":
                badge = "🟡 <b>中性平衡 (NEUTRAL_BALANCED)</b>"
            elif m.regime == "CONTAGION_AMPLIFIED":
                badge = "🟠 <b>高貝塔傳染 (CONTAGION_AMPLIFIED)</b>"
            else:
                badge = "🔴 <b>大盤跳水剛性阻尼 (MARKET_STRESS_DAMPED)</b>"

            sec_tag = f" <i>[{m.injected_sector}]</i>" if m.injected_sector else ""
            lines.append(f"• 標的：<b>{m.ticker}</b>{sec_tag} vs <b>{m.benchmark_ticker}</b>")
            lines.append(f"• 體制狀態：{badge}")
            lines.append(
                f"• 即時行情：{m.ticker} <code>{m.intraday_return_pct:+.2f}%</code> | "
                f"{m.benchmark_ticker} <code>{m.benchmark_return_pct:+.2f}%</code> | "
                f"相對強度 (RS): <code>{m.relative_strength_pct:+.2f}%</code>"
            )
            lines.append(
                f"• 核心指標：有效 Beta <code>{m.beta:.2f}</code> | 相關性 <code>{m.correlation:+.2f}</code>"
            )
            lines.append(
                f"• <b>阻尼調度決策</b>：乘數 <code><b>{m.damping_factor:.2f}x</b></code> "
                f"(追單策略: <code>{m.stalking_action}</code>)"
            )
            lines.append(f"• <i>處置說明</i>：{m.rationale}")
            lines.append("──────────────────")

        lines.append("💡 <b>調度聯動</b>：14:00 盤中追單自動調整折價收斂係數，15:50 尾盤 MOC 動態縮放執行金額。")
        lines.append("💡 <b>快捷指令</b>：輸入 <code>/spread</code> 檢視利差競標，輸入 <code>/dipbuy stalk</code> 檢視追單改價。")

        return "\n".join(lines)
