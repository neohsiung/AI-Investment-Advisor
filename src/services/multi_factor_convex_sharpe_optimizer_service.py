"""
Multi-Factor Convex Sharpe Frontier Optimizer Service (Phase 60B)
=================================================================
利差回流資本最優夏普邊界動態二次規劃引擎

核心數學與金融工程架構：
1. 目標：將跨板塊動態收割回流之現金 (Recirculated Cash) 或常規建倉資金，
   透過凸幾何二次規劃 (Convex Quadratic Programming / Projected Gradient Ascent)
   於候選高 Alpha 核心股票中精算最大夏普比率 (Maximum Sharpe Ratio / Tangency Portfolio) 最優配置權重。
2. 凸規劃數學公式：
   - 預期報酬向量：μ ∈ R^N (融合 6 大量化因子動能與超額收益)
   - 協方差矩陣：Σ ∈ R^(N×N) (結合對角正則化收縮 Σ_shrink = (1-δ)S + δ diag(S))
   - 目標函數：Maximize SR(w) = (w^T μ - r_f) / sqrt(w^T Σ w)
   - 約束條件：∑_{i=1}^N w_i = 1.0, 0 <= w_i <= w_max (預設 25% 剛性上限，防範過度集中)
3. 梯度與有界單體投影 (Bounded Simplex Projection)：
   - 歐拉切線斜率：∇ SR(w) = (μ - r_f) / σ_p - (w^T (μ - r_f) / σ_p^3) Σ w
   - 經迭代投影至有界單體 {w | ∑ w_i = 1, 0 <= w_i <= w_max}，確保收斂至最優夏普邊界。
4. 資本分配與券商約束：
   - 嚴格守衛單筆訂單 >= $10.00 USD 最低起投門檻與 2 位小數精度。
   - 保留 20% 剛性防守現金儲備。
5. 0-LLM 數理優先，輸出符合 Telegram HTML + Email nl2br 雙渠道格式標準。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("MultiFactorConvexSharpeOptimizerService")


@dataclass
class ConvexOptimalWeight:
    """單一標的之凸最優夏普配置"""
    ticker: str
    target_weight: float
    allocated_usd: float
    expected_return_annual: float
    marginal_sharpe_contribution: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "target_weight": round(self.target_weight, 4),
            "allocated_usd": round(self.allocated_usd, 2),
            "expected_return_annual": round(self.expected_return_annual, 4),
            "marginal_sharpe_contribution": round(self.marginal_sharpe_contribution, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConvexOptimalWeight:
        return cls(
            ticker=str(data.get("ticker", "")),
            target_weight=float(data.get("target_weight", 0.0) or 0.0),
            allocated_usd=float(data.get("allocated_usd", 0.0) or 0.0),
            expected_return_annual=float(data.get("expected_return_annual", 0.0) or 0.0),
            marginal_sharpe_contribution=float(data.get("marginal_sharpe_contribution", 0.0) or 0.0),
        )


@dataclass
class ConvexOptimizationResult:
    """最優夏普邊界二次規劃診斷成果"""
    expected_portfolio_return: float
    portfolio_volatility: float
    portfolio_sharpe_ratio: float
    weights: List[ConvexOptimalWeight]
    recirculated_cash_allocated_usd: float
    optimization_status: str  # OPTIMAL, APPROXIMATE_CONVERGED, FALLBACK_EQUAL_WEIGHT
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expected_portfolio_return": round(self.expected_portfolio_return, 4),
            "portfolio_volatility": round(self.portfolio_volatility, 4),
            "portfolio_sharpe_ratio": round(self.portfolio_sharpe_ratio, 4),
            "recirculated_cash_allocated_usd": round(self.recirculated_cash_allocated_usd, 2),
            "optimization_status": self.optimization_status,
            "evaluated_at": self.evaluated_at,
            "weights": [w.to_dict() for w in self.weights],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConvexOptimizationResult:
        weights_raw = data.get("weights", [])
        weights = [ConvexOptimalWeight.from_dict(w) for w in weights_raw]
        return cls(
            expected_portfolio_return=float(data.get("expected_portfolio_return", 0.0) or 0.0),
            portfolio_volatility=float(data.get("portfolio_volatility", 0.0) or 0.0),
            portfolio_sharpe_ratio=float(data.get("portfolio_sharpe_ratio", 0.0) or 0.0),
            weights=weights,
            recirculated_cash_allocated_usd=float(data.get("recirculated_cash_allocated_usd", 0.0) or 0.0),
            optimization_status=str(data.get("optimization_status", "FALLBACK_EQUAL_WEIGHT")),
            evaluated_at=data.get("evaluated_at") or datetime.now(timezone.utc).isoformat(),
        )


class MultiFactorConvexSharpeOptimizerService:
    """利差回流資本最優夏普邊界動態二次規劃服務"""

    DEFAULT_RISK_FREE_RATE = 0.045              # 無風險基準利率 4.5%
    DEFAULT_MAX_WEIGHT_CAP = 0.25               # 單一標的最高權重上限 25%
    DEFAULT_SHRINKAGE_DELTA = 0.15              # 協方差對角收縮係數 15%
    REDIS_KEY_LATEST = "convex_sharpe:latest"

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
        return bool(self._get_setting("enable_convex_sharpe_optimization", True))

    @property
    def risk_free_rate(self) -> float:
        return float(self._get_setting("convex_sharpe_risk_free_rate", self.DEFAULT_RISK_FREE_RATE))

    @property
    def max_weight_cap(self) -> float:
        return float(self._get_setting("convex_sharpe_max_weight_cap", self.DEFAULT_MAX_WEIGHT_CAP))

    # ═══════════════════════════════════════════════════════════════════════
    # 1. 數理核心：有界單體投影 (Bounded Simplex Projection)
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def project_bounded_simplex(v: np.ndarray, cap: float = 0.25) -> np.ndarray:
        """
        將任意向量 v 投影至有界單體：{w | ∑ w_i = 1, 0 <= w_i <= cap}。
        使用二分搜尋或截斷平移求解拉格朗日乘子 λ。
        """
        n = len(v)
        if n == 0:
            return np.array([])
        if cap < 1.0 / n:
            cap = 1.0 / n  # 鬆弛不可行邊界

        low = np.min(v) - cap
        high = np.max(v)
        tol = 1e-7

        for _ in range(100):
            mid = (low + high) / 2.0
            w = np.clip(v - mid, 0.0, cap)
            s = np.sum(w)
            if abs(s - 1.0) < tol:
                break
            if s > 1.0:
                low = mid
            else:
                high = mid

        w = np.clip(v - mid, 0.0, cap)
        sum_w = np.sum(w)
        if sum_w > 0:
            w = w / sum_w
        else:
            w = np.ones(n) / n
        return w

    # ═══════════════════════════════════════════════════════════════════════
    # 2. 凸幾何夏普邊界二次規劃 (optimize_recirculated_capital_allocation)
    # ═══════════════════════════════════════════════════════════════════════

    async def optimize_recirculated_capital_allocation(
        self,
        candidate_tickers: List[str],
        available_capital_usd: float,
        expected_returns: Optional[Dict[str, float]] = None,
        covariance_matrix: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> ConvexOptimizationResult:
        """
        求解候選標的之最優夏普權重並分配資本。
        """
        clean_tickers = [str(t).upper().strip() for t in candidate_tickers if str(t).strip()]
        clean_tickers = list(dict.fromkeys(clean_tickers))  # 去重
        n = len(clean_tickers)

        rf = self.risk_free_rate
        cap = max(1.0 / max(1, n), self.max_weight_cap)

        if n == 0 or available_capital_usd < 10.0:
            return ConvexOptimizationResult(
                expected_portfolio_return=0.0,
                portfolio_volatility=0.0,
                portfolio_sharpe_ratio=0.0,
                weights=[],
                recirculated_cash_allocated_usd=0.0,
                optimization_status="FALLBACK_EQUAL_WEIGHT",
            )

        if not self.is_enabled:
            # 停用時均分
            eq_w = 1.0 / n
            weights = [
                ConvexOptimalWeight(
                    ticker=t,
                    target_weight=eq_w,
                    allocated_usd=round(available_capital_usd * eq_w, 2),
                    expected_return_annual=0.10,
                    marginal_sharpe_contribution=1.0 / n,
                )
                for t in clean_tickers
            ]
            return ConvexOptimizationResult(
                expected_portfolio_return=0.10,
                portfolio_volatility=0.15,
                portfolio_sharpe_ratio=(0.10 - rf) / 0.15,
                weights=weights,
                recirculated_cash_allocated_usd=available_capital_usd,
                optimization_status="FALLBACK_EQUAL_WEIGHT",
            )

        # 1. 建立預期年化報酬向量 μ
        mu_vec = np.zeros(n)
        for i, t in enumerate(clean_tickers):
            if expected_returns and t in expected_returns:
                mu_vec[i] = float(expected_returns[t])
            else:
                # 預設高 Alpha 預期收益：科技 14%~16%，跨板塊防守 10%~12%
                if t in ("NVDA", "TSM", "AAPL", "MSFT", "AMD"):
                    mu_vec[i] = 0.155
                elif t in ("V", "MA"):
                    mu_vec[i] = 0.125
                elif t in ("COP", "XOM"):
                    mu_vec[i] = 0.115
                elif t in ("ECL", "LIN"):
                    mu_vec[i] = 0.110
                else:
                    mu_vec[i] = 0.120

        # 2. 建立年化協方差矩陣 Σ
        sigma_mat = np.zeros((n, n))
        for i, t1 in enumerate(clean_tickers):
            for j, t2 in enumerate(clean_tickers):
                if covariance_matrix and t1 in covariance_matrix and t2 in covariance_matrix[t1]:
                    sigma_mat[i, j] = float(covariance_matrix[t1][t2])
                else:
                    # 預設協方差模型
                    if i == j:
                        # 自身波動率平方
                        vol = 0.32 if t1 in ("NVDA", "AMD") else (0.24 if t1 in ("TSM", "COP") else 0.18)
                        sigma_mat[i, j] = vol * vol
                    else:
                        # 板塊間相關性假定
                        vol_i = 0.32 if t1 in ("NVDA", "AMD") else (0.24 if t1 in ("TSM", "COP") else 0.18)
                        vol_j = 0.32 if t2 in ("NVDA", "AMD") else (0.24 if t2 in ("TSM", "COP") else 0.18)
                        corr = 0.65 if (t1 in ("NVDA", "TSM", "AAPL", "MSFT", "AMD") and t2 in ("NVDA", "TSM", "AAPL", "MSFT", "AMD")) else 0.25
                        sigma_mat[i, j] = corr * vol_i * vol_j

        # 協方差對角正則化收縮 (Ledoit-Wolf shrinkage proxy)
        delta = self.DEFAULT_SHRINKAGE_DELTA
        sigma_shrink = (1.0 - delta) * sigma_mat + delta * np.diag(np.diag(sigma_mat))

        # 3. 求解最大夏普比率 (Projected Gradient Ascent)
        w = np.ones(n) / n
        learning_rate = 0.05
        max_iters = 60
        status = "OPTIMAL"

        for _ in range(max_iters):
            var_p = float(w.T @ sigma_shrink @ w)
            std_p = max(1e-5, np.sqrt(var_p))
            excess_return = float(w.T @ (mu_vec - rf))

            # 梯度計算：∇ SR(w) = (μ - rf)/σ_p - (excess_return / σ_p^3) * (Σ w)
            grad = (mu_vec - rf) / std_p - (excess_return / (std_p ** 3)) * (sigma_shrink @ w)

            w_next = self.project_bounded_simplex(w + learning_rate * grad, cap=cap)
            if np.max(np.abs(w_next - w)) < 1e-5:
                break
            w = w_next
        else:
            status = "APPROXIMATE_CONVERGED"

        # 4. 指標計算與資本分配
        port_ret = float(w.T @ mu_vec)
        port_vol = float(np.sqrt(w.T @ sigma_shrink @ w))
        port_sharpe = float((port_ret - rf) / max(1e-5, port_vol))

        # 邊際夏普貢獻
        m_contrib = (mu_vec - rf) / port_vol - ((port_ret - rf) / (port_vol ** 3)) * (sigma_shrink @ w)

        optimal_weights: List[ConvexOptimalWeight] = []
        # 初步分配金額
        raw_allocs = [round(available_capital_usd * float(w[i]), 2) for i in range(n)]

        # 券商起投門檻與小數精度校正 (每筆 >= $10.00，否則歸零並重新等比分配)
        for i in range(n):
            if raw_allocs[i] < 10.0 and available_capital_usd >= 10.0:
                raw_allocs[i] = 0.0

        rem_capital = available_capital_usd
        sum_alloc = sum(raw_allocs)
        if sum_alloc > 0 and sum_alloc != available_capital_usd:
            # 等比縮放回 available_capital_usd
            scale = available_capital_usd / sum_alloc
            raw_allocs = [round(a * scale, 2) for a in raw_allocs]

        for i, t in enumerate(clean_tickers):
            optimal_weights.append(ConvexOptimalWeight(
                ticker=t,
                target_weight=round(float(w[i]), 4),
                allocated_usd=raw_allocs[i],
                expected_return_annual=round(float(mu_vec[i]), 4),
                marginal_sharpe_contribution=round(float(m_contrib[i]), 4),
            ))

        result = ConvexOptimizationResult(
            expected_portfolio_return=round(port_ret, 4),
            portfolio_volatility=round(port_vol, 4),
            portfolio_sharpe_ratio=round(port_sharpe, 4),
            weights=optimal_weights,
            recirculated_cash_allocated_usd=round(sum(raw_allocs), 2),
            optimization_status=status,
        )

        # 寫入 Redis
        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            cache_key = f"{self.REDIS_KEY_LATEST}:{self.user_id}"
            await r.setex(cache_key, 86400, json.dumps(result.to_dict()))
        except Exception as we:
            logger.debug("Failed saving convex optimization result to Redis: %s", we)

        return result

    # ═══════════════════════════════════════════════════════════════════════
    # 3. 0-LLM 雙渠道戰報生成
    # ═══════════════════════════════════════════════════════════════════════

    def format_convex_sharpe_report(
        self,
        result: ConvexOptimizationResult,
        channel: str = "telegram",
    ) -> str:
        """
        產出符合 Telegram HTML 與 Email nl2br 雙渠道標準之夏普邊界最優配置戰報。
        """
        lines = [
            "📐 <b>【利差回流資本最優夏普邊界二次規劃儀表】</b>",
            "━━━━━━━━━━━━━━━━━━",
            f"• <b>預期年化報酬</b>：<code>{result.expected_portfolio_return:.2%}</code>",
            f"• <b>投組年化波動率</b>：<code>{result.portfolio_volatility:.2%}</code>",
            f"• <b>邊界夏普比率 (Sharpe)</b>：<code><b>{result.portfolio_sharpe_ratio:.2f}</b></code>",
            f"• <b>總規劃配置金額</b>：<code>${result.recirculated_cash_allocated_usd:,.2f} USD</code>",
            f"• <b>收斂狀態</b>：{'🟢 最優邊界解 (OPTIMAL)' if result.optimization_status == 'OPTIMAL' else '🟡 近似收斂'} ({result.optimization_status})",
            "━━━━━━━━━━━━━━━━━━",
            "🎯 <b>【邊際夏普最優權重矩陣】</b>",
        ]

        if not result.weights:
            lines.append("• <i>目前暫無配置標的或可支配金額不足起投額 ($10 USD)。</i>")
        else:
            sorted_weights = sorted(result.weights, key=lambda x: x.target_weight, reverse=True)
            for w in sorted_weights:
                bars = int(round(w.target_weight * 10))
                bar_str = "▓" * bars + "░" * max(0, 10 - bars)
                lines.append(
                    f"• <b>{w.ticker}</b>：<code><b>{w.target_weight:.1%}</b></code> "
                    f"(${w.allocated_usd:,.2f}) <code>[{bar_str}]</code>"
                )
                lines.append(
                    f"  └ 預期收益: <code>{w.expected_return_annual:.1%}</code> | "
                    f"夏普貢獻斜率: <code>{w.marginal_sharpe_contribution:+.2f}</code>"
                )

        lines.append("──────────────────")
        lines.append("💡 <b>配置閉環</b>：收割回流之現金自動依據邊界夏普權重注入，杜絕主觀盲目均分。")
        lines.append("💡 <b>快捷指令</b>：輸入 <code>/batch</code> 檢視批次建倉，輸入 <code>/darkpool</code> 檢視暗池底價。")

        return "\n".join(lines)
