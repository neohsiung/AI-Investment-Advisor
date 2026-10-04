"""
Adaptive Council Meta-Learning Service (A1 Engine).
自適應評議會元學習閉環服務：
整合 D1 健康雷達、O1 貝氏體制與 O2 EVT 極值黑天鵝告警為評議會前置先驗，
並依歷史決策事後績效歸因動態校準各專家 Agent 的體制投票權重。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from src.config.owner import resolve_user_id
from src.data.database import get_db_engine
from src.utils.logger import setup_logger

logger = setup_logger("AdaptiveCouncilMetaLearningService")

# 預設各體制下的基礎專家先驗權重 (Regime Prior Weights)
DEFAULT_REGIME_PRIORS: Dict[str, Dict[str, float]] = {
    "BULL_LOW_VOL": {
        "Technical": 0.28,
        "Sentiment": 0.20,
        "Fundamental": 0.20,
        "Valuation": 0.12,
        "Risk": 0.20,
    },
    "BULL_HIGH_VOL": {
        "Technical": 0.22,
        "Sentiment": 0.18,
        "Fundamental": 0.20,
        "Valuation": 0.15,
        "Risk": 0.25,
    },
    "SIDEWAYS_LOW_VOL": {
        "Fundamental": 0.28,
        "Valuation": 0.26,
        "Technical": 0.18,
        "Sentiment": 0.10,
        "Risk": 0.18,
    },
    "SIDEWAYS_HIGH_VOL": {
        "Fundamental": 0.25,
        "Valuation": 0.25,
        "Risk": 0.25,
        "Technical": 0.15,
        "Sentiment": 0.10,
    },
    "BEAR_LOW_VOL": {
        "Valuation": 0.30,
        "Fundamental": 0.25,
        "Risk": 0.30,
        "Technical": 0.10,
        "Sentiment": 0.05,
    },
    "BEAR_HIGH_VOL": {
        "Risk": 0.40,
        "Valuation": 0.22,
        "Fundamental": 0.20,
        "Technical": 0.10,
        "Sentiment": 0.08,
    },
    "BULL": {
        "Technical": 0.28,
        "Sentiment": 0.20,
        "Fundamental": 0.20,
        "Valuation": 0.12,
        "Risk": 0.20,
    },
    "NEUTRAL": {
        "Fundamental": 0.25,
        "Valuation": 0.25,
        "Risk": 0.25,
        "Technical": 0.15,
        "Sentiment": 0.10,
    },
    "BEAR": {
        "Risk": 0.40,
        "Valuation": 0.22,
        "Fundamental": 0.20,
        "Technical": 0.10,
        "Sentiment": 0.08,
    },
    "CRITICAL_BLACK_SWAN": {
        "Risk": 0.55,
        "Valuation": 0.18,
        "Fundamental": 0.15,
        "Technical": 0.07,
        "Sentiment": 0.05,
    },
}

STANDARD_AGENT_ROSTER = ["Technical", "Fundamental", "Sentiment", "Valuation", "Risk"]


@dataclass
class AgentAttributionMetrics:
    agent_name: str
    total_calls: int = 0
    correct_calls: int = 0
    rolling_win_rate: float = 0.50
    avg_alpha_contribution: float = 0.0
    regime_win_rates: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_calls": self.total_calls,
            "correct_calls": self.correct_calls,
            "rolling_win_rate": round(self.rolling_win_rate, 4),
            "avg_alpha_contribution": round(self.avg_alpha_contribution, 4),
            "regime_win_rates": {k: round(v, 4) for k, v in self.regime_win_rates.items()},
        }


@dataclass
class AdaptiveCouncilContext:
    current_regime: str
    regime_confidence: float
    black_swan_alert_level: str
    var_999: float
    cvar_999: float
    fat_tail_ratio: float
    health_score: float
    health_rating: str
    target_cash_buffer: float
    target_beta: float
    meta_weights: Dict[str, float]
    agent_attributions: Dict[str, AgentAttributionMetrics]
    prompt_guidance: str
    veto_power_active: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_regime": self.current_regime,
            "regime_confidence": round(self.regime_confidence, 4),
            "black_swan_alert_level": self.black_swan_alert_level,
            "var_999": round(self.var_999, 4),
            "cvar_999": round(self.cvar_999, 4),
            "fat_tail_ratio": round(self.fat_tail_ratio, 2),
            "health_score": round(self.health_score, 1),
            "health_rating": self.health_rating,
            "target_cash_buffer": round(self.target_cash_buffer, 4),
            "target_beta": round(self.target_beta, 2),
            "meta_weights": {k: round(v, 4) for k, v in self.meta_weights.items()},
            "agent_attributions": {k: v.to_dict() for k, v in self.agent_attributions.items()},
            "prompt_guidance": self.prompt_guidance,
            "veto_power_active": self.veto_power_active,
        }


class AdaptiveCouncilMetaLearningService:
    """
    A1 Engine: 自適應評議會元學習閉環協調服務。
    負責：
    1. 整合 D1/O1/O2 即時宏觀體制與極值尾部風險指標
    2. 事後決策表現歸因 (Outcome Attribution & Accuracy Tracking)
    3. 貝氏在線元權重校準 (Regime-Conditioned Meta-Weights Calibration)
    4. 生成結構化先驗上下文並注入 Council 辯論與 CIO 裁決管線
    """

    def __init__(
        self,
        user_id: str,
        db_path: Optional[str] = None,
        adaptive_service: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.engine = get_db_engine(db_path)
        self._adaptive_service = adaptive_service

    def get_adaptive_service(self) -> Any:
        if self._adaptive_service is not None:
            return self._adaptive_service
        try:
            from src.services.portfolio_adaptive_intelligence_service import (
                PortfolioAdaptiveIntelligenceService,
            )
            self._adaptive_service = PortfolioAdaptiveIntelligenceService(user_id=self.user_id)
            return self._adaptive_service
        except Exception as e:
            logger.warning(f"Failed to initialize PortfolioAdaptiveIntelligenceService: {e}")
            return None

    # ── 1. 事後績效歸因分析 (Outcome Attribution) ──────────────────────

    def compute_agent_attributions(
        self,
        lookback_days: int = 90,
    ) -> Dict[str, AgentAttributionMetrics]:
        """
        從 decision_outcomes 表讀取已結算的歷史決策，按 Agent 計算滾動勝率與體制特化精準度。
        """
        attributions: Dict[str, AgentAttributionMetrics] = {
            agent: AgentAttributionMetrics(agent_name=agent) for agent in STANDARD_AGENT_ROSTER
        }

        try:
            with self.engine.connect() as conn:
                # 撈取已結算之決策資料
                query = text("""
                    SELECT agent_name, signal, realized_return_pct, benchmark_return_pct, alpha_pct, resolved_at
                    FROM decision_outcomes
                    WHERE user_id = :user_id
                      AND resolved_at IS NOT NULL
                    ORDER BY resolved_at DESC
                    LIMIT 200
                """)
                rows = conn.execute(query, {"user_id": self.user_id}).fetchall()

            agent_stats: Dict[str, List[Tuple[bool, float]]] = {agent: [] for agent in STANDARD_AGENT_ROSTER}

            for row in rows:
                agent = row[0]
                signal = (row[1] or "").upper()
                realized = float(row[2] or 0.0)
                alpha = float(row[4] or 0.0)

                # 判斷是否為預測成功 (Hit):
                # Bullish/Buy 訊號且創造正 Alpha (或絕對正報酬 > 1%)
                # Bearish/Sell 訊號且 Alpha < 0 (或市場下行時迴避損失)
                is_hit = False
                if any(k in signal for k in ("BUY", "LONG", "BULLISH")):
                    is_hit = (alpha > 0.0) or (realized > 0.01)
                elif any(k in signal for k in ("SELL", "SHORT", "BEARISH", "DEFENSIVE", "CASH")):
                    is_hit = (alpha < 0.0) or (realized < -0.01)
                else:
                    is_hit = abs(alpha) < 0.02  # Neutral call

                # 標準化 agent 名稱匹配
                matched_agent = None
                for std_agent in STANDARD_AGENT_ROSTER:
                    if std_agent.lower() in agent.lower():
                        matched_agent = std_agent
                        break
                if not matched_agent:
                    matched_agent = agent if agent in STANDARD_AGENT_ROSTER else "Fundamental"

                if matched_agent not in agent_stats:
                    agent_stats[matched_agent] = []
                agent_stats[matched_agent].append((is_hit, alpha))

            # 計算各 Agent 統計量（採用拉普拉斯平滑，避免小樣本極端偏誤）
            for agent, samples in agent_stats.items():
                total = len(samples)
                hits = sum(1 for h, _ in samples if h)
                alphas = [a for _, a in samples]
                avg_alpha = sum(alphas) / total if total > 0 else 0.0

                # Laplace Smoothing: (hits + 1) / (total + 2)
                win_rate = (hits + 1.0) / (total + 2.0) if total > 0 else 0.50

                attributions[agent] = AgentAttributionMetrics(
                    agent_name=agent,
                    total_calls=total,
                    correct_calls=hits,
                    rolling_win_rate=win_rate,
                    avg_alpha_contribution=avg_alpha,
                )

        except Exception as e:
            logger.warning(f"Error computing agent attributions (fallback to prior defaults): {e}")

        return attributions

    # ── 2. 體制條件下的貝氏元權重校準 (Meta-Weights Calibration) ─────

    def calibrate_meta_weights(
        self,
        current_regime: str,
        is_black_swan_alert: bool = False,
        attributions: Optional[Dict[str, AgentAttributionMetrics]] = None,
    ) -> Dict[str, float]:
        """
        結合市場體制先驗與歷史滾動勝率，計算各專家 Agent 的動態投票權重。
        """
        if is_black_swan_alert:
            regime_key = "CRITICAL_BLACK_SWAN"
        elif current_regime in DEFAULT_REGIME_PRIORS:
            regime_key = current_regime
        elif "BULL" in current_regime:
            regime_key = "BULL"
        elif "BEAR" in current_regime:
            regime_key = "BEAR"
        else:
            regime_key = "NEUTRAL"

        priors = DEFAULT_REGIME_PRIORS.get(regime_key, DEFAULT_REGIME_PRIORS["NEUTRAL"])

        if not attributions:
            attributions = self.compute_agent_attributions()

        # 貝氏微調：Score_i = Prior_i * (1 + 0.6 * (WinRate_i - 0.5)) * exp(Alpha_i)
        unnormalized: Dict[str, float] = {}
        for agent in STANDARD_AGENT_ROSTER:
            prior_w = priors.get(agent, 0.20)
            attr = attributions.get(agent, AgentAttributionMetrics(agent_name=agent))

            # 勝率激勵項 (WinRate in [0.2, 0.8] -> scale [0.82, 1.18])
            win_factor = 1.0 + 0.6 * (attr.rolling_win_rate - 0.50)
            # Alpha 溢價微調 (上限阻尼防止權重爆炸)
            alpha_dampened = max(-0.15, min(0.15, attr.avg_alpha_contribution))
            alpha_factor = math.exp(alpha_dampened)

            raw_score = prior_w * win_factor * alpha_factor
            unnormalized[agent] = max(0.02, raw_score)

        # 歸一化
        total_score = sum(unnormalized.values())
        calibrated: Dict[str, float] = {}
        for agent, score in unnormalized.items():
            calibrated[agent] = score / total_score if total_score > 0 else 0.20

        # 若黑天鵝警戒，強制確保 Risk Agent 擁有不低於 0.50 的權重
        if is_black_swan_alert and calibrated.get("Risk", 0.0) < 0.50:
            calibrated["Risk"] = 0.50
            # 重新歸一化其餘 Agent
            remaining_w = 0.50
            other_total = sum(v for k, v in calibrated.items() if k != "Risk")
            for k in calibrated:
                if k != "Risk":
                    calibrated[k] = (calibrated[k] / other_total) * remaining_w

        return calibrated

    # ── 3. 自適應評議會上下文生成 (Prior Context Generation) ─────────

    def generate_adaptive_council_context(
        self,
        current_weights: Optional[Dict[str, float]] = None,
        market_observation: Optional[Dict[str, float]] = None,
    ) -> AdaptiveCouncilContext:
        """
        全量合成 D1/O1/O2 即時指標與元學習權重，產生注入給 Council 辯論與 CIO 的上下文。
        """
        adaptive_service = self.get_adaptive_service()

        # 預設基準值
        regime = "SIDEWAYS_HIGH_VOL"
        regime_conf = 0.75
        alert_level = "NORMAL"
        var_999 = 0.038
        cvar_999 = 0.052
        fat_tail = 1.18
        health_score = 75.0
        health_rating = "BALANCED"
        target_cash = 0.15
        target_beta = 0.90

        if current_weights is None:
            current_weights = {"SPY": 0.6, "QQQ": 0.2, "CASH": 0.2}

        if adaptive_service:
            try:
                report = adaptive_service.diagnose_portfolio(
                    current_weights=current_weights,
                    market_observation=market_observation,
                )
                health_score = report.health_score
                health_rating = report.health_rating.value
                regime = report.regime_analysis.get("current_regime", regime)
                regime_conf = report.regime_analysis.get("regime_confidence", regime_conf)
                target_cash = report.regime_analysis.get("target_cash_buffer", target_cash)
                target_beta = report.regime_analysis.get("target_beta", target_beta)

                tail_info = report.tail_risk_analysis or {}
                alert_level = tail_info.get("alert_level", alert_level)
                var_999 = tail_info.get("var_999", var_999)
                cvar_999 = tail_info.get("cvar_999", cvar_999)
                fat_tail = tail_info.get("fat_tail_ratio", fat_tail)
            except Exception as e:
                logger.warning(f"Error diagnosing portfolio for council context: {e}")

        is_black_swan = alert_level in ("WARNING", "CRITICAL")
        attributions = self.compute_agent_attributions()
        meta_weights = self.calibrate_meta_weights(
            current_regime=regime,
            is_black_swan_alert=is_black_swan,
            attributions=attributions,
        )

        # 構造專門注入給 LLM 的清晰指引文字
        guidance_lines = [
            f"## [A1 Meta-Learning Prior Context] 市場體制與動態專家權重",
            f"- **宏觀體制 (O1 Bayesian HMM)**: {regime} (置信度: {regime_conf*100:.1f}%)",
            f"- **黑天鵝預警 (O2 EVT)**: {alert_level} | 99.9% VaR: {var_999*100:.2f}%, CVaR: {cvar_999*100:.2f}%, 肥尾倍數: {fat_tail:.2f}x",
            f"- **投組健康狀態 (D1)**: 總分 {health_score:.1f}/100 ({health_rating}) | 建議防禦現金: {target_cash*100:.1f}%, 目標 Beta: {target_beta:.2f}",
            f"- **當前專家動態決策影響力權重 (Meta-Weights)**:",
        ]
        for agent in STANDARD_AGENT_ROSTER:
            w = meta_weights.get(agent, 0.20)
            attr = attributions.get(agent, AgentAttributionMetrics(agent_name=agent))
            guidance_lines.append(
                f"  • {agent}: {w*100:.1f}% (歷史滾動勝率: {attr.rolling_win_rate*100:.1f}%, 累積 Alpha: {attr.avg_alpha_contribution*100:+.2f}pp)"
            )

        if is_black_swan:
            guidance_lines.append(
                f"\n⚠️ **【黑天鵝危機防禦指令】**: 極值理論檢測到異常尾部風險 (Alert Level: {alert_level})。"
                f"Risk Agent 已獲授權【一票否決權 (Veto Power)】。嚴禁在此體制下逆勢激進做多高 Beta 標的！"
            )
        elif regime.startswith("BULL"):
            guidance_lines.append(
                f"\n🚀 **【牛市動態進攻指令】**: 當前處於 {regime} 體制，Technical 與 Sentiment 專家權重獲優先加權，但不得跌破 5% 剛性現金防線。"
            )
        else:
            guidance_lines.append(
                f"\n⚖️ **【震盪均衡指引】**: 當前處於 {regime} 體制，加權 Fundamental 與 Valuation 價值專家，要求堅實的安全邊際。"
            )

        prompt_guidance = "\n".join(guidance_lines)

        return AdaptiveCouncilContext(
            current_regime=regime,
            regime_confidence=regime_conf,
            black_swan_alert_level=alert_level,
            var_999=var_999,
            cvar_999=cvar_999,
            fat_tail_ratio=fat_tail,
            health_score=health_score,
            health_rating=health_rating,
            target_cash_buffer=target_cash,
            target_beta=target_beta,
            meta_weights=meta_weights,
            agent_attributions=attributions,
            prompt_guidance=prompt_guidance,
            veto_power_active=is_black_swan,
        )
