"""
Council Diversity Entropy & Groupthink Shielder Service (A4 Engine)
專家意見歧異度與群體思維盲區熵值警戒
=============================================================================
Calculates Shannon Diversity Entropy of council expert agent votes and protects
decision-making from confirmation bias and echo-chamber groupthink.

Key Capabilities:
1. Shannon Diversity Entropy Formulation:
   - Aggregates weighted voting distribution P = [p_buy, p_hold, p_sell].
   - Computes normalized Shannon Diversity Entropy:
     H(P) = - sum(p_k * ln(p_k))
     H_norm = H(P) / ln(3) in [0.0, 1.0]
2. Groupthink & Echo Chamber Detection:
   - Evaluates multi-tiered consensus states:
     - DIVERSE: Healthy debate (H_norm >= 0.65).
     - MODERATE_CONSENSUS: Normal alignment (0.40 <= H_norm < 0.65).
     - GROUPTHINK_WARNING: Extreme uncritical herd behavior (H_norm < 0.40 and dominant_ratio >= 0.80).
3. Devil's Advocate Inoculation & Conviction Haircut:
   - When groupthink is detected, automatically synthesizes structured counter-theses
     (valuation compression, macro tightening, regulatory/geopolitical blindspots).
   - Injects mandatory review checkpoints into the CIO final prompt.
   - Applies an automatic protective position haircut (default 25%) to suppress
     overconfident capital allocation.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


class DiversityLevel(str, Enum):
    """Classification of expert debate diversity."""
    DIVERSE = "DIVERSE"
    MODERATE_CONSENSUS = "MODERATE_CONSENSUS"
    GROUPTHINK_WARNING = "GROUPTHINK_WARNING"


class VoteStance(str, Enum):
    """Voting stance options."""
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


@dataclass
class AgentVote:
    """Individual expert agent vote payload."""
    agent_name: str
    stance: VoteStance | str
    weight: float = 1.0
    confidence: float = 1.0
    rationale: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.stance, str):
            val = self.stance.upper().strip()
            if "BUY" in val:
                self.stance = VoteStance.BUY
            elif "SELL" in val:
                self.stance = VoteStance.SELL
            else:
                self.stance = VoteStance.HOLD
        self.weight = max(0.01, float(self.weight))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


@dataclass
class DevilsAdvocateChallenge:
    """Structured challenge packet generated when groupthink is flagged."""
    dominant_stance: str
    challenge_headline: str
    counter_arguments: List[str]
    required_checkpoints: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dominant_stance": self.dominant_stance,
            "challenge_headline": self.challenge_headline,
            "counter_arguments": self.counter_arguments,
            "required_checkpoints": self.required_checkpoints,
        }


@dataclass
class DiversityAssessment:
    """Comprehensive council diversity and groupthink assessment."""
    symbol: Optional[str]
    shannon_entropy: float
    normalized_entropy: float
    distribution: Dict[str, float]
    dominant_stance: str
    dominant_ratio: float
    diversity_level: DiversityLevel
    groupthink_detected: bool
    recommended_haircut_pct: float
    devils_advocate_challenge: Optional[DevilsAdvocateChallenge] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "shannon_entropy": round(self.shannon_entropy, 4),
            "normalized_entropy": round(self.normalized_entropy, 4),
            "distribution": {k: round(v, 4) for k, v in self.distribution.items()},
            "dominant_stance": self.dominant_stance,
            "dominant_ratio": round(self.dominant_ratio, 4),
            "diversity_level": self.diversity_level.value,
            "groupthink_detected": self.groupthink_detected,
            "recommended_haircut_pct": round(self.recommended_haircut_pct, 4),
            "devils_advocate_challenge": (
                self.devils_advocate_challenge.to_dict()
                if self.devils_advocate_challenge
                else None
            ),
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class CouncilDiversityEntropyService:
    """
    A4 Engine: Council Diversity Entropy & Groupthink Shielder Service.
    """

    DEFAULT_ENTROPY_THRESHOLD = 0.40       # Below this, normalized entropy triggers groupthink check
    DEFAULT_DOMINANT_RATIO_THRESHOLD = 0.80 # 80%+ consensus considered herd behavior
    DEFAULT_HAIRCUT_PCT = 0.25              # 25% conviction haircut under groupthink
    MAX_CLASSES = 3                         # BUY, HOLD, SELL

    def __init__(
        self,
        user_id: str = "default_user",
        settings_repo: Any = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.settings_repo = settings_repo

    def _get_setting(self, key: str, default: Any, val_type: type = float) -> Any:
        if not self.settings_repo:
            return default
        try:
            val = self.settings_repo.get(self.user_id, key)
            if val is None:
                return default
            if val_type is bool:
                return str(val).lower() in ("true", "1", "yes")
            return val_type(val)
        except Exception as e:
            logger.warning(f"Error loading setting '{key}' ({e}); using default {default}")
            return default

    @property
    def is_enabled(self) -> bool:
        return self._get_setting("council_diversity_enabled", True, bool)

    @property
    def groupthink_entropy_threshold(self) -> float:
        return float(self._get_setting("groupthink_entropy_threshold", self.DEFAULT_ENTROPY_THRESHOLD, float))

    @property
    def groupthink_dominant_ratio_threshold(self) -> float:
        return float(self._get_setting("groupthink_dominant_ratio_threshold", self.DEFAULT_DOMINANT_RATIO_THRESHOLD, float))

    @property
    def groupthink_haircut_pct(self) -> float:
        return float(self._get_setting("groupthink_haircut_pct", self.DEFAULT_HAIRCUT_PCT, float))

    def evaluate_diversity(
        self,
        votes: List[AgentVote | Dict[str, Any]],
        symbol: Optional[str] = None,
    ) -> DiversityAssessment:
        """
        Evaluate Shannon Diversity Entropy across submitted expert votes.
        """
        if not votes:
            return DiversityAssessment(
                symbol=symbol,
                shannon_entropy=0.0,
                normalized_entropy=0.0,
                distribution={"BUY": 0.0, "HOLD": 0.0, "SELL": 0.0},
                dominant_stance="HOLD",
                dominant_ratio=0.0,
                diversity_level=DiversityLevel.DIVERSE,
                groupthink_detected=False,
                recommended_haircut_pct=0.0,
                details={"reason": "No votes submitted"},
            )

        # 1. Normalize votes
        normalized_votes: List[AgentVote] = []
        for v in votes:
            if isinstance(v, AgentVote):
                normalized_votes.append(v)
            elif isinstance(v, dict):
                normalized_votes.append(
                    AgentVote(
                        agent_name=str(v.get("agent_name", "Unknown")),
                        stance=v.get("stance", VoteStance.HOLD),
                        weight=float(v.get("weight", 1.0)),
                        confidence=float(v.get("confidence", 1.0)),
                        rationale=v.get("rationale"),
                    )
                )

        # 2. Weighted stance probabilities
        weighted_counts: Dict[str, float] = {"BUY": 0.0, "HOLD": 0.0, "SELL": 0.0}
        total_weight = 0.0

        for v in normalized_votes:
            stance_key = v.stance.value if isinstance(v.stance, VoteStance) else str(v.stance).upper()
            w = max(0.01, v.weight * max(0.1, v.confidence))
            weighted_counts[stance_key] = weighted_counts.get(stance_key, 0.0) + w
            total_weight += w

        total_weight = max(1e-6, total_weight)
        distribution = {k: weighted_counts[k] / total_weight for k in ("BUY", "HOLD", "SELL")}

        # 3. Calculate Shannon Diversity Entropy
        # H(P) = - sum(p_k * ln(p_k))
        shannon_entropy = 0.0
        for p in distribution.values():
            if p > 1e-9:
                shannon_entropy -= p * math.log(p)

        max_entropy = math.log(self.MAX_CLASSES)  # ln(3) ~ 1.0986
        normalized_entropy = max(0.0, min(1.0, shannon_entropy / max_entropy))

        # 4. Find dominant stance
        dominant_stance = max(distribution, key=lambda k: distribution[k])
        dominant_ratio = distribution[dominant_stance]

        # 5. Groupthink evaluation
        entropy_threshold = self.groupthink_entropy_threshold
        dominant_threshold = self.groupthink_dominant_ratio_threshold

        groupthink_detected = False
        haircut = 0.0
        devils_advocate = None

        if not self.is_enabled:
            level = DiversityLevel.DIVERSE
        elif normalized_entropy < entropy_threshold and dominant_ratio >= dominant_threshold:
            level = DiversityLevel.GROUPTHINK_WARNING
            groupthink_detected = True
            haircut = self.groupthink_haircut_pct
            devils_advocate = self._build_devils_advocate(dominant_stance, symbol, normalized_votes)
        elif normalized_entropy < 0.65:
            level = DiversityLevel.MODERATE_CONSENSUS
        else:
            level = DiversityLevel.DIVERSE

        details = {
            "agent_count": len(normalized_votes),
            "max_possible_entropy": round(max_entropy, 4),
            "entropy_threshold": entropy_threshold,
            "dominant_threshold": dominant_threshold,
            "agent_stances": [
                {
                    "agent": v.agent_name,
                    "stance": v.stance.value if isinstance(v.stance, VoteStance) else str(v.stance),
                    "weight": round(v.weight, 2),
                    "confidence": round(v.confidence, 2),
                }
                for v in normalized_votes
            ],
        }

        return DiversityAssessment(
            symbol=symbol,
            shannon_entropy=shannon_entropy,
            normalized_entropy=normalized_entropy,
            distribution=distribution,
            dominant_stance=dominant_stance,
            dominant_ratio=dominant_ratio,
            diversity_level=level,
            groupthink_detected=groupthink_detected,
            recommended_haircut_pct=haircut,
            devils_advocate_challenge=devils_advocate,
            details=details,
        )

    def _build_devils_advocate(
        self,
        dominant_stance: str,
        symbol: Optional[str],
        votes: List[AgentVote],
    ) -> DevilsAdvocateChallenge:
        """
        Synthesize rigorous counter-arguments when uncritical herd consensus is detected.
        """
        sym_str = symbol.upper() if symbol else "Target Asset"

        if dominant_stance == "BUY":
            headline = f"🚨 群體思維警戒：評議會壓倒性一面倒看多 {sym_str}，啟動魔鬼代言人強制反向審查"
            counter_arguments = [
                f"【估值與多重擴張頂點】市場對 {sym_str} 的樂觀預期可能已完全 Price-in，面臨本益比/市銷率估值壓縮 (Multiple Contraction) 風險。",
                "【宏觀流動性背離】若基準利率或央行流動性邊際收緊，高 Beta 成長型資產之現金流折現將面臨重挫。",
                "【過度擁擠交易 (Crowded Trade)】所有專家一致看多常為籌碼面散戶狂熱或主力出貨陷阱，短期稍有利空將爆發多殺多踩踏。",
                "【非對稱下行風險】極端看多情緒忽視了供應鏈突發斷鏈、競爭對手價格戰或地緣監管衝擊之肥尾情境。",
            ]
            checkpoints = [
                "要求 CIO 確認：若隔夜下跌 10%，是否有明確結構性止損與流動性退場方案？",
                "要求 Risk Agent 重新評估：極端黑天鵝情境下，該持倉的最大可能實施缺口損失是多少？",
                "要求強制執行 25% 建議部位保守折減 (Conviction Haircut)，抑制過度自信槓桿。",
            ]
        elif dominant_stance == "SELL":
            headline = f"🚨 群體思維警戒：評議會壓倒性一面倒恐慌看空 {sym_str}，啟動魔鬼代言人反向軋空審查"
            counter_arguments = [
                f"【悲觀過度反映】{sym_str} 當前市場悲觀情緒可能已達極致，基本面利空鈍化，極易觸發強勁技術性反彈。",
                "【軋空與空頭回補風險 (Short Squeeze)】擁擠看空將使空頭部位脆弱，稍有正面訊號或回購將遭逢暴力軋空吃穿。",
                "【錯失長期複利機會】在恐慌低點全面出清優質核心資產，將產生不可逆的換庫機會成本與 Alpha 鈍化損失。",
            ]
            checkpoints = [
                "要求 CIO 確認：目前賣出是否屬於非理性追殺恐慌盤？",
                "要求 Valuation Agent 重新驗證：當前價格是否已顯著低於內在價值支撐防線？",
                "評估分批被動限價掛單退場，杜絕市價市價急殺造成的嚴重滑價衝擊。",
            ]
        else:
            headline = f"🚨 群體思維警戒：評議會全員陷入觀望僵局 (HOLD)，啟動催化劑機會成本審查"
            counter_arguments = [
                "【決策拖延與機會成本】全員觀望可能反映出分析麻痺 (Analysis Paralysis)，導致資本閒置並承受通貨膨脹與時間價值耗損。",
                "【忽略潛在突發催化劑】低估了短期財報或產業政策突破對資產估值的階躍性推動。",
            ]
            checkpoints = [
                "要求 CIO 釐清：需要何種特定驗證指標或邊際數據變化方能解鎖行動？",
            ]

        return DevilsAdvocateChallenge(
            dominant_stance=dominant_stance,
            challenge_headline=headline,
            counter_arguments=counter_arguments,
            required_checkpoints=checkpoints,
        )

    def inject_devils_advocate_into_prompt(
        self,
        assessment: DiversityAssessment,
        base_prompt: str,
    ) -> str:
        """
        Inject structured devil's advocate challenge into CIO final arbitration system/user prompt.
        """
        if not assessment.groupthink_detected or not assessment.devils_advocate_challenge:
            return base_prompt

        challenge = assessment.devils_advocate_challenge
        injection = f"""

================================================================================
🚨 [COUNCIL GROUPTHINK SHIELDER - DEVIL'S ADVOCATE INOCULATION (A4)] 🚨
Normalized Entropy: {assessment.normalized_entropy:.3f} | Dominant Stance: {assessment.dominant_stance} ({assessment.dominant_ratio * 100:.1f}%)
Status: CRITICAL GROUPTHINK DETECTED - ECHO CHAMBER RISK ACTIVE
--------------------------------------------------------------------------------
{challenge.challenge_headline}

【魔鬼代言人強制反面論證 (Mandatory Counter-Theses)】:
"""
        for i, arg in enumerate(challenge.counter_arguments, 1):
            injection += f"{i}. {arg}\n"

        injection += "\n【CIO 終審必須回應之檢查點 (Mandatory Arbitrator Checkpoints)】:\n"
        for i, cp in enumerate(challenge.required_checkpoints, 1):
            injection += f"[{i}] {cp}\n"

        injection += f"""
【系統強制安全防護 (Enforced Protection)】:
- 建議部位或信號置信度已自動施加 {assessment.recommended_haircut_pct * 100:.1f}% 保守折減 (Conviction Haircut)。
================================================================================
"""
        return base_prompt + injection

    def apply_conviction_haircut(
        self,
        base_conviction: float,
        assessment: DiversityAssessment,
    ) -> float:
        """
        Apply protective conviction haircut if groupthink echo chamber is flagged.
        """
        conv = max(0.0, float(base_conviction))
        if assessment.groupthink_detected and assessment.recommended_haircut_pct > 0:
            adjusted = conv * (1.0 - assessment.recommended_haircut_pct)
            logger.info(
                f"🛡️ Groupthink haircut applied: {conv:.4f} -> {adjusted:.4f} "
                f"(-{assessment.recommended_haircut_pct * 100:.1f}%)"
            )
            return max(0.0, round(adjusted, 4))
        return conv
