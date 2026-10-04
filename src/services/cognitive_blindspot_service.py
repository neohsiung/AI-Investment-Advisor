"""
Cognitive Blindspot Service (A2 Engine).
在線認知盲區偵測與自動反省校準服務：
1. 分析專家 Agent 在歷史 decision_outcomes 中的連續決策失誤 (streak) 與體制勝率。
2. 辨識認知盲區模式（TREND_OVERCONFIDENCE, DOWNTREND_DENIAL, ANCHORING_BIAS, FALSE_ALARM_PARANOIA, REGIME_MISMATCH）。
3. 自動生成自我反省約束（Corrective Guidance），剛性注入至下次辯論 Prompt 及 CIO 共識審查上下文。
4. 提供自動解除或手動解除校準機制。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, text

from src.config.owner import resolve_user_id
from src.data.database import get_db_engine
from src.data.models import AgentCognitiveBlindspot
from src.utils.logger import setup_logger

logger = setup_logger("CognitiveBlindspotService")


class BiasPattern(str, Enum):
    TREND_OVERCONFIDENCE = "TREND_OVERCONFIDENCE"  # 趨勢過度自信：多頭慣性下逆勢做多造成嚴重回撤
    DOWNTREND_DENIAL = "DOWNTREND_DENIAL"          # 下行否認：在熊市或震盪市中拒絕減倉
    ANCHORING_BIAS = "ANCHORING_BIAS"              # 錨定偏誤：執著於歷史估值或目標價忽視宏觀轉變
    FALSE_ALARM_PARANOIA = "FALSE_ALARM_PARANOIA"  # 虛警妄想：防禦性過度、錯失顯著正 Alpha
    REGIME_MISMATCH = "REGIME_MISMATCH"            # 體制錯配：策略在當前體制下勝率顯著低落


class BlindspotSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class BlindspotDetectionResult:
    agent_name: str
    bias_pattern: BiasPattern
    regime: str
    consecutive_failures: int
    avg_alpha_loss: float
    severity: BlindspotSeverity
    corrective_guidance: str


# 標準專家名冊
STANDARD_AGENT_ROSTER = ["Technical", "Fundamental", "Sentiment", "Valuation", "Risk"]


class CognitiveBlindspotService:
    """
    A2 專家在線認知偏誤偵測與反省校準服務。
    """

    def __init__(
        self,
        user_id: str,
        engine: Any = None,
        consecutive_failure_threshold: int = 2,
        alpha_loss_threshold: float = 0.0,
    ):
        self.user_id = resolve_user_id(user_id)
        self.engine = engine or get_db_engine()
        self.failure_threshold = max(2, consecutive_failure_threshold)
        self.alpha_loss_threshold = alpha_loss_threshold

    def scan_and_detect_blindspots(self, current_regime: str = "SIDEWAYS_HIGH_VOL") -> List[AgentCognitiveBlindspot]:
        """
        全量掃描歷史決策記錄，偵測各專家的盲區模式，並持久化至 agent_cognitive_blindspots 表中。
        """
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT agent_name, signal, realized_return_pct, benchmark_return_pct, alpha_pct, resolved_at
                    FROM decision_outcomes
                    WHERE user_id = :user_id
                      AND resolved_at IS NOT NULL
                    ORDER BY resolved_at DESC
                    LIMIT 200
                """)
                rows = conn.execute(query, {"user_id": self.user_id}).fetchall()
        except Exception as e:
            logger.error(f"CognitiveBlindspot: Failed to query decision_outcomes: {e}", exc_info=True)
            return []

        # 整理每個 Agent 的決策序列
        agent_outcomes: Dict[str, List[Dict[str, Any]]] = {agent: [] for agent in STANDARD_AGENT_ROSTER}

        for row in rows:
            agent = row[0] or ""
            signal = (row[1] or "").upper()
            realized = float(row[2] or 0.0)
            benchmark = float(row[3] or 0.0)
            alpha = float(row[4] or 0.0)
            resolved_at = row[5]

            # 判定勝負:
            # BUY/LONG: 需 alpha > 0 或 realized > 0.01
            # SELL/BEARISH: 需 alpha < 0 或 realized < -0.01 (成功逃頂或迴避損失)
            is_hit = False
            if any(k in signal for k in ("BUY", "LONG", "BULLISH")):
                is_hit = (alpha > 0.0) or (realized > 0.01)
            elif any(k in signal for k in ("SELL", "SHORT", "BEARISH", "DEFENSIVE", "CASH")):
                is_hit = (alpha < 0.0) or (realized < -0.01)
            else:
                is_hit = abs(alpha) < 0.02

            matched_agent = None
            for std_agent in STANDARD_AGENT_ROSTER:
                if std_agent.lower() in agent.lower():
                    matched_agent = std_agent
                    break
            if not matched_agent:
                matched_agent = agent if agent in STANDARD_AGENT_ROSTER else "Fundamental"

            if matched_agent not in agent_outcomes:
                agent_outcomes[matched_agent] = []

            agent_outcomes[matched_agent].append({
                "signal": signal,
                "realized": realized,
                "benchmark": benchmark,
                "alpha": alpha,
                "is_hit": is_hit,
                "resolved_at": resolved_at,
            })

        new_blindspots: List[AgentCognitiveBlindspot] = []

        for agent, records in agent_outcomes.items():
            if not records:
                continue

            # 計算連續失敗次數 (Consecutive Failures Streak from newest records)
            streak = 0
            accum_alpha_loss = 0.0
            failed_signals = []

            for r in records:
                if not r["is_hit"]:
                    streak += 1
                    accum_alpha_loss += abs(min(0.0, r["alpha"]))
                    failed_signals.append(r["signal"])
                else:
                    break

            if streak >= self.failure_threshold:
                avg_loss = accum_alpha_loss / streak
                pattern, severity = self._classify_bias_pattern(agent, failed_signals, avg_loss, current_regime)
                guidance = self._generate_corrective_guidance(agent, pattern, streak, avg_loss, current_regime)

                # 儲存或更新至 DB
                blindspot = self._persist_blindspot(
                    agent_name=agent,
                    bias_pattern=pattern.value,
                    regime=current_regime,
                    consecutive_failures=streak,
                    avg_alpha_loss=round(avg_loss, 4),
                    severity=severity.value,
                    corrective_guidance=guidance,
                )
                if blindspot:
                    new_blindspots.append(blindspot)

        return new_blindspots

    def _classify_bias_pattern(
        self,
        agent_name: str,
        failed_signals: List[str],
        avg_loss: float,
        current_regime: str,
    ) -> Tuple[BiasPattern, BlindspotSeverity]:
        """
        根據失敗訊號特徵與體制分類偏誤模式與嚴重性。
        """
        has_buy = any("BUY" in s or "LONG" in s or "BULLISH" in s for s in failed_signals)
        has_sell = any("SELL" in s or "SHORT" in s or "BEARISH" in s for s in failed_signals)

        if "BEAR" in current_regime.upper() and has_buy:
            pattern = BiasPattern.DOWNTREND_DENIAL
        elif agent_name == "Technical" and has_buy:
            pattern = BiasPattern.TREND_OVERCONFIDENCE
        elif agent_name == "Valuation":
            pattern = BiasPattern.ANCHORING_BIAS
        elif agent_name == "Risk" and has_sell:
            pattern = BiasPattern.FALSE_ALARM_PARANOIA
        else:
            pattern = BiasPattern.REGIME_MISMATCH

        # 嚴重性判定
        if avg_loss >= 0.05 or len(failed_signals) >= 4:
            severity = BlindspotSeverity.CRITICAL
        elif avg_loss >= 0.025 or len(failed_signals) >= 3:
            severity = BlindspotSeverity.HIGH
        elif avg_loss >= 0.01:
            severity = BlindspotSeverity.MEDIUM
        else:
            severity = BlindspotSeverity.LOW

        return pattern, severity

    def _generate_corrective_guidance(
        self,
        agent_name: str,
        pattern: BiasPattern,
        streak: int,
        avg_loss: float,
        current_regime: str,
    ) -> str:
        """
        生成結構化約束反省引導 (Corrective Guidance Prompt)。
        """
        header = f"⚠️ COGNITIVE BLINDSPOT ALERT: [{agent_name}] has failed {streak} consecutive decisions (avg alpha loss: -{avg_loss*100:.2f}%) under {current_regime}."
        
        rules = []
        if pattern == BiasPattern.TREND_OVERCONFIDENCE:
            rules.append("1. CRITICAL: You are exhibiting TREND OVERCONFIDENCE. Stop assuming momentum persistence.")
            rules.append("2. You MUST verify volume exhaustion, divergence indicators, and multi-timeframe moving average breakdowns before confirming any BUY.")
            rules.append("3. Lower your default conviction rating by at least 1 notch (e.g., STRONG_BUY -> SPECULATIVE_BUY).")
        elif pattern == BiasPattern.DOWNTREND_DENIAL:
            rules.append("1. CRITICAL: You are exhibiting DOWNTREND DENIAL in a bearish/volatile regime.")
            rules.append("2. You MUST prioritize capital preservation over dip-buying. Assume lower lows until structural reversal is confirmed.")
            rules.append("3. Any BUY recommendation must include an explicit stop-loss and invalidation thesis.")
        elif pattern == BiasPattern.ANCHORING_BIAS:
            rules.append("1. CRITICAL: You are ANCHORING to outdated valuation multiples or DCF price targets.")
            rules.append("2. You MUST re-evaluate your cost of capital (WACC) and terminal growth assumptions under current macro conditions.")
            rules.append("3. Acknowledge that cheap assets can become cheaper (value traps) without near-term operational catalysts.")
        elif pattern == BiasPattern.FALSE_ALARM_PARANOIA:
            rules.append("1. CRITICAL: You are generating FALSE ALARMS causing the council to miss upside opportunities.")
            rules.append("2. Distinguish between systemic risk and standard market volatility. Do not call for full cash defensive mode without concrete EVT tail warnings.")
            rules.append("3. State clear probabilistic risk criteria instead of deterministic panic.")
        else:
            rules.append(f"1. CRITICAL: REGIME MISMATCH detected under {current_regime}.")
            rules.append("2. Actively adjust your baseline priors and align with other experts before finalizing your recommendation.")

        return f"{header}\n" + "\n".join(rules)

    def _persist_blindspot(
        self,
        agent_name: str,
        bias_pattern: str,
        regime: str,
        consecutive_failures: int,
        avg_alpha_loss: float,
        severity: str,
        corrective_guidance: str,
    ) -> Optional[AgentCognitiveBlindspot]:
        """
        將盲區寫入或更新至 agent_cognitive_blindspots。
        """
        try:
            with self.engine.begin() as conn:
                # 檢查是否已存在作用中的相同盲區記錄
                check_q = text("""
                    SELECT id FROM agent_cognitive_blindspots
                    WHERE user_id = :user_id
                      AND agent_name = :agent_name
                      AND is_active = TRUE
                    LIMIT 1
                """)
                existing = conn.execute(check_q, {"user_id": self.user_id, "agent_name": agent_name}).fetchone()

                now = datetime.now(timezone.utc)
                if existing:
                    blindspot_id = existing[0]
                    update_q = text("""
                        UPDATE agent_cognitive_blindspots
                        SET bias_pattern = :bias_pattern,
                            regime = :regime,
                            consecutive_failures = :consecutive_failures,
                            avg_alpha_loss = :avg_alpha_loss,
                            severity = :severity,
                            corrective_guidance = :corrective_guidance,
                            detected_at = :detected_at
                        WHERE id = :id
                    """)
                    conn.execute(update_q, {
                        "id": blindspot_id,
                        "bias_pattern": bias_pattern,
                        "regime": regime,
                        "consecutive_failures": consecutive_failures,
                        "avg_alpha_loss": avg_alpha_loss,
                        "severity": severity,
                        "corrective_guidance": corrective_guidance,
                        "detected_at": now,
                    })
                else:
                    blindspot_id = str(uuid.uuid4())
                    insert_q = text("""
                        INSERT INTO agent_cognitive_blindspots (
                            id, user_id, agent_name, bias_pattern, regime,
                            consecutive_failures, avg_alpha_loss, severity,
                            corrective_guidance, is_active, detected_at
                        ) VALUES (
                            :id, :user_id, :agent_name, :bias_pattern, :regime,
                            :consecutive_failures, :avg_alpha_loss, :severity,
                            :corrective_guidance, TRUE, :detected_at
                        )
                    """)
                    conn.execute(insert_q, {
                        "id": blindspot_id,
                        "user_id": self.user_id,
                        "agent_name": agent_name,
                        "bias_pattern": bias_pattern,
                        "regime": regime,
                        "consecutive_failures": consecutive_failures,
                        "avg_alpha_loss": avg_alpha_loss,
                        "severity": severity,
                        "corrective_guidance": corrective_guidance,
                        "detected_at": now,
                    })

            return AgentCognitiveBlindspot(
                id=blindspot_id,
                user_id=self.user_id,
                agent_name=agent_name,
                bias_pattern=bias_pattern,
                regime=regime,
                consecutive_failures=consecutive_failures,
                avg_alpha_loss=avg_alpha_loss,
                severity=severity,
                corrective_guidance=corrective_guidance,
                is_active=True,
                detected_at=now,
            )
        except Exception as e:
            logger.error(f"CognitiveBlindspot: Failed to persist blindspot for {agent_name}: {e}", exc_info=True)
            return None

    def get_agent_guidance(self, agent_name: str) -> Optional[str]:
        """
        獲取特定 Agent 當前活躍的反省約束引導（若有）。
        """
        try:
            with self.engine.connect() as conn:
                q = text("""
                    SELECT corrective_guidance FROM agent_cognitive_blindspots
                    WHERE user_id = :user_id
                      AND agent_name = :agent_name
                      AND is_active = TRUE
                    ORDER BY detected_at DESC
                    LIMIT 1
                """)
                row = conn.execute(q, {"user_id": self.user_id, "agent_name": agent_name}).fetchone()
                if row:
                    return str(row[0])
        except Exception as e:
            logger.debug(f"CognitiveBlindspot: Failed to load guidance for {agent_name}: {e}")
        return None

    def get_active_blindspots(self) -> List[AgentCognitiveBlindspot]:
        """
        查詢當前使用者的所有活躍盲區。
        """
        results = []
        try:
            with self.engine.connect() as conn:
                q = text("""
                    SELECT id, user_id, agent_name, bias_pattern, regime,
                           consecutive_failures, avg_alpha_loss, severity,
                           corrective_guidance, is_active, detected_at, resolved_at
                    FROM agent_cognitive_blindspots
                    WHERE user_id = :user_id
                      AND is_active = TRUE
                    ORDER BY detected_at DESC
                """)
                rows = conn.execute(q, {"user_id": self.user_id}).fetchall()
                for r in rows:
                    results.append(AgentCognitiveBlindspot(
                        id=str(r[0]),
                        user_id=str(r[1]),
                        agent_name=str(r[2]),
                        bias_pattern=str(r[3]),
                        regime=str(r[4]),
                        consecutive_failures=int(r[5]),
                        avg_alpha_loss=float(r[6] or 0.0),
                        severity=str(r[7]),
                        corrective_guidance=str(r[8]),
                        is_active=bool(r[9]),
                        detected_at=r[10],
                        resolved_at=r[11],
                    ))
        except Exception as e:
            logger.error(f"CognitiveBlindspot: Failed to list active blindspots: {e}", exc_info=True)
        return results

    def get_cio_blindspot_summary(self) -> str:
        """
        為 CIO 產生專家盲區總覽提示詞，以便在綜合裁決時對具備盲區的專家進行降權與審查。
        """
        active = self.get_active_blindspots()
        if not active:
            return ""

        lines = ["## Cognitive Blindspot Warnings for Debate Participants:"]
        for b in active:
            lines.append(
                f"- **{b.agent_name}** ({b.bias_pattern}, Severity: {b.severity}): "
                f"{b.consecutive_failures} consecutive misjudgments under {b.regime} (avg alpha loss: -{float(b.avg_alpha_loss or 0.0)*100:.1f}%). "
                f"CIO Directive: Cross-examine this expert's assumptions and discount high-conviction claims."
            )
        return "\n".join(lines)

    def resolve_blindspot(self, blindspot_id: str) -> bool:
        """
        解除指定的盲區記錄。
        """
        try:
            now = datetime.now(timezone.utc)
            with self.engine.begin() as conn:
                q = text("""
                    UPDATE agent_cognitive_blindspots
                    SET is_active = FALSE,
                        resolved_at = :resolved_at
                    WHERE id = :id AND user_id = :user_id
                """)
                res = conn.execute(q, {"id": blindspot_id, "user_id": self.user_id, "resolved_at": now})
                return res.rowcount > 0
        except Exception as e:
            logger.error(f"CognitiveBlindspot: Failed to resolve blindspot {blindspot_id}: {e}", exc_info=True)
            return False
