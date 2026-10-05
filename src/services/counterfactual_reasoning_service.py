"""
A6: Council Counterfactual Reasoning & Stress Scenario Generation Service
=============================================================================
Before the Chief Investment Officer (CIO) renders a final executive verdict,
generates dynamic counterfactual "What-if" stress scenario inoculation cards:
1. Counterfactual Scenario Engine:
   - Probes consensus vulnerabilities (e.g. "What if core inflation rebounds +50 bps?",
     "What if export license restrictions tighten?", "What if hyperscaler Capex cuts 25%?").
   - Categorizes scenarios across Macro, Geopolitical, Liquidity, and Idiosyncratic dimensions.
2. Inoculation Prompt Synthesis:
   - Compiles markdown-formatted Counterfactual Inoculation blocks into CIO final review prompts.
   - Enforces 3 mandatory defense checkpoints (Drawdown threshold, Risk veto criteria, Hedge buffer).
3. Configurable Strictness:
   - Fully controllable via settings_schema.yaml (enabled, max_scenarios, conviction_threshold).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


class ScenarioCategory(str, Enum):
    MACRO = "MACRO"
    GEOPOLITICAL = "GEOPOLITICAL"
    LIQUIDITY = "LIQUIDITY"
    IDIOSYNCRATIC = "IDIOSYNCRATIC"


class ScenarioSeverity(str, Enum):
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME_TAIL = "EXTREME_TAIL"


@dataclass
class CounterfactualScenario:
    """Individual counterfactual stress hypothesis."""
    scenario_id: str
    title: str
    category: ScenarioCategory
    shock_hypothesis: str
    assumed_market_impact: str
    targeted_vulnerabilities: List[str]
    challenge_questions_for_experts: List[str]
    severity_level: ScenarioSeverity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "category": self.category.value,
            "shock_hypothesis": self.shock_hypothesis,
            "assumed_market_impact": self.assumed_market_impact,
            "targeted_vulnerabilities": self.targeted_vulnerabilities,
            "challenge_questions_for_experts": self.challenge_questions_for_experts,
            "severity_level": self.severity_level.value,
        }


@dataclass
class CounterfactualInoculationResult:
    """Full counterfactual stress testing result ready for CIO prompt injection."""
    symbol: str
    consensus_stance: str
    scenarios: List[CounterfactualScenario]
    cio_inoculation_prompt: str
    required_defense_checkpoints: List[str]
    is_stress_tested: bool
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "consensus_stance": self.consensus_stance,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "cio_inoculation_prompt": self.cio_inoculation_prompt,
            "required_defense_checkpoints": self.required_defense_checkpoints,
            "is_stress_tested": self.is_stress_tested,
            "evaluated_at": self.evaluated_at,
        }


class CounterfactualReasoningService:
    """
    A6 Engine: Dynamically generates counterfactual stress scenarios and
    synthesizes CIO prompt inoculation blocks to stress-test consensus decisions.
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        default_max_scenarios: int = 3,
        default_conviction_threshold: float = 0.70,
    ) -> None:
        self.user_id = resolve_user_id(user_id)
        self.settings_service = settings_service
        self._max_scenarios = default_max_scenarios
        self._conviction_threshold = default_conviction_threshold

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service and hasattr(self.settings_service, "get"):
            try:
                val = self.settings_service.get(key)
                if val is not None:
                    return val
            except Exception as e:
                logger.debug(f"Failed to fetch setting '{key}': {e}. Using default {default}")
        return default

    @property
    def is_enabled(self) -> bool:
        return bool(self._get_setting("council_counterfactual_enabled", True))

    @property
    def max_scenarios(self) -> int:
        return int(self._get_setting("council_counterfactual_max_scenarios", self._max_scenarios))

    @property
    def conviction_threshold(self) -> float:
        return float(self._get_setting("council_counterfactual_conviction_threshold", self._conviction_threshold))

    def generate_scenarios(
        self,
        symbol: str,
        consensus_stance: str = "BUY",
        conviction: float = 0.85,
        key_drivers: Optional[List[str]] = None,
        sector: Optional[str] = None,
        max_scenarios: Optional[int] = None,
    ) -> List[CounterfactualScenario]:
        """
        Synthesizes domain-specific counterfactual stress scenarios probing the consensus stance.
        """
        symbol_upper = symbol.upper()
        stance_upper = consensus_stance.upper()
        sec_upper = (sector or "TECHNOLOGY").upper()
        limit = max_scenarios or self.max_scenarios

        scenarios: List[CounterfactualScenario] = []

        if "BUY" in stance_upper:
            # Bullish consensus: Stress-test downside vulnerabilities
            # 1. Macro rate shock
            scenarios.append(
                CounterfactualScenario(
                    scenario_id=f"CF_MACRO_RATES_{symbol_upper}",
                    title="【宏觀反事實】基準利率與通膨再度抬頭 (Rates Rebound +50 bps)",
                    category=ScenarioCategory.MACRO,
                    shock_hypothesis="假設美國核心 PCE 或 CPI 意外月增 0.5%，10年期公債殖利率短線急升 35~50 bps。",
                    assumed_market_impact="長天期科技股折現率攀升，高本益比成長股面臨 -8% ~ -12% 估值倍數壓縮 (Multiple Compression)。",
                    targeted_vulnerabilities=[
                        "估值倍數過度擴張 (P/E / EV/Sales 過高)",
                        "市場完全 Price-in 降息預期之非對稱下行風險",
                    ],
                    challenge_questions_for_experts=[
                        f"若估值下修 10%，{symbol_upper} 是否具備足夠的自由現金流與獲利護城河維持開倉？",
                        "基本面專家：預估降息延後 6 個月，對該標的營收增長影響幅度為何？",
                    ],
                    severity_level=ScenarioSeverity.HIGH,
                )
            )

            # 2. Tech / Sector specific Capex / Supply chain shock
            if any(tech_kw in sec_upper for tech_kw in ["TECH", "SEMICONDUCTOR", "COMMUNICATION"]):
                scenarios.append(
                    CounterfactualScenario(
                        scenario_id=f"CF_SECTOR_CAPEX_{symbol_upper}",
                        title="【產業反事實】巨頭資本支出急踩剎車 (Cloud Capex Moderation)",
                        category=ScenarioCategory.IDIOSYNCRATIC,
                        shock_hypothesis="假設一線雲端巨頭 (Hyperscalers) 宣布將下半年 AI/伺服器資本支出增速由 +40% 下修至持平。",
                        assumed_market_impact="供應鏈訂單能見度驟降，產業鏈上游單季營收與毛利增長面臨腰斬風險。",
                        targeted_vulnerabilities=[
                            "過度依賴少數大型客戶訂單集中度",
                            "高基期下訂單重複下單 (Double Ordering) 庫存修正風險",
                        ],
                        challenge_questions_for_experts=[
                            f"若大客戶砍單 20%，{symbol_upper} 的毛利率防守下限在哪裡？",
                            "估值專家：在獲利成長降至 15% 的情境下，目標公允價值是多少？",
                        ],
                        severity_level=ScenarioSeverity.HIGH,
                    )
                )
            else:
                scenarios.append(
                    CounterfactualScenario(
                        scenario_id=f"CF_CONSUMER_SQUEEZE_{symbol_upper}",
                        title="【消費反事實】末端消費力道疲弱與利潤率擠壓 (Margin Squeeze)",
                        category=ScenarioCategory.IDIOSYNCRATIC,
                        shock_hypothesis="假設終端消費者實質購買力受通膨高檔侵蝕，客單價與銷量出現雙重降溫。",
                        assumed_market_impact="定價權受阻，營收成長鈍化伴隨促銷費用上升，淨利率下滑 200~300 bps。",
                        targeted_vulnerabilities=[
                            "產品缺乏剛性定價權",
                            "庫存周轉天數拉長",
                        ],
                        challenge_questions_for_experts=[
                            f"{symbol_upper} 是否具備抗通膨轉嫁能力？若無法轉嫁，毛利率將侵蝕多少？",
                        ],
                        severity_level=ScenarioSeverity.MODERATE,
                    )
                )

            # 3. Geopolitical / Regulatory shock
            scenarios.append(
                CounterfactualScenario(
                    scenario_id=f"CF_GEOPOLITICAL_{symbol_upper}",
                    title="【地緣反事實】出口監管與關鍵供應鏈摩擦升級 (Regulatory / Export Ban)",
                    category=ScenarioCategory.GEOPOLITICAL,
                    shock_hypothesis="假設跨國主管機關頒布更嚴格之先進技術出口許可或外國投資審查管制。",
                    assumed_market_impact="特定受限市場即刻斷供，全球供應鏈物流與重置成本顯著暴增。",
                    targeted_vulnerabilities=[
                        "單一地理區域營收敞口過大",
                        "關鍵零組件代工產能過度集中",
                    ],
                    challenge_questions_for_experts=[
                        f"若失去特定海外區域 15% 營收來源，{symbol_upper} 剩餘市場能否彌補缺口？",
                        "風控專家：地緣肥尾極端情境下，停損與部位規模折減機制為何？",
                    ],
                    severity_level=ScenarioSeverity.EXTREME_TAIL,
                )
            )

        elif "SELL" in stance_upper:
            # Bearish consensus: Stress-test short squeeze and turnaround surprises
            scenarios.append(
                CounterfactualScenario(
                    scenario_id=f"CF_SHORT_SQUEEZE_{symbol_upper}",
                    title="【軋空反事實】突發超預期利多帶動軋空爆發 (Epic Short Squeeze)",
                    category=ScenarioCategory.LIQUIDITY,
                    shock_hypothesis="假設該標的發布突破性策略轉型或重磅合作夥伴協議，引發極度擁擠空頭倉位踩踏平倉。",
                    assumed_market_impact="短線單日急拉 +15% ~ +25%，空頭保證金被強制追繳。",
                    targeted_vulnerabilities=[
                        "空方部位過度擁擠 (High Short Interest)",
                        "未預留左側軋空停損安全緩衝",
                    ],
                    challenge_questions_for_experts=[
                        f"若 {symbol_upper} 股價逆勢跳空開高 12%，評議會有無剛性止損與槓桿熔斷策略？",
                        "情緒專家：融券借券費率與空頭持倉集中度是否已處於極限狀態？",
                    ],
                    severity_level=ScenarioSeverity.HIGH,
                )
            )
            scenarios.append(
                CounterfactualScenario(
                    scenario_id=f"CF_EARNINGS_SURPRISE_{symbol_upper}",
                    title="【業績反事實】成本控制大幅優於悲觀預期 (Margin Turnaround)",
                    category=ScenarioCategory.IDIOSYNCRATIC,
                    shock_hypothesis="假設公司透過激進組織精簡與供應鏈重組，單季營業利益率超預期飆升 400 bps。",
                    assumed_market_impact="市場悲觀預期全面落空，分析師集體上調目標價 20%。",
                    targeted_vulnerabilities=[
                        "線性外推過往虧損與衰退趨勢",
                        "低估管理層降本增效的營運槓桿彈性",
                    ],
                    challenge_questions_for_experts=[
                        f"評議會是否考慮過 {symbol_upper} 營運槓桿反轉的向上非對稱可能？",
                    ],
                    severity_level=ScenarioSeverity.MODERATE,
                )
            )
        else:
            # Neutral / HOLD consensus
            scenarios.append(
                CounterfactualScenario(
                    scenario_id=f"CF_BREAKOUT_DIRECTION_{symbol_upper}",
                    title="【突破反事實】強趨勢單邊脫離震盪區間 (Decisive Volatility Breakout)",
                    category=ScenarioCategory.LIQUIDITY,
                    shock_hypothesis="假設大盤伴隨突發總體事件強行走出單邊趨勢，帶動該標的突破長期均線收斂區。",
                    assumed_market_impact="觀望者面臨大幅錯失 Alpha 踏空機會成本或被動追高風險。",
                    targeted_vulnerabilities=[
                        "缺乏預設之突破觸發委託單",
                        "機會成本非線性侵蝕",
                    ],
                    challenge_questions_for_experts=[
                        f"若 {symbol_upper} 向上突破頸線，評議會是否具備即時自動提拔進場機制？",
                    ],
                    severity_level=ScenarioSeverity.MODERATE,
                )
            )

        return scenarios[:limit]

    def build_cio_inoculation_prompt(
        self,
        symbol: str,
        consensus_stance: str,
        scenarios: List[CounterfactualScenario],
    ) -> str:
        """
        Formats scenarios into a structured Markdown prompt block
        ready for insertion into the CIO's executive decision context.
        """
        lines = [
            "### 🔮 【A6 評議會反事實推理與情境壓力假設卡】(Counterfactual Stress Inoculation)",
            f"**審查標的**：`{symbol}` | **共識立場**：`{consensus_stance}`",
            "> ⚠️ **審查指令**：在簽署最終裁決前，CIO 必須針對以下極端反事實情境進行抗跌防禦檢驗，不得盲從單邊狂熱：",
            "",
        ]

        for idx, sc in enumerate(scenarios, 1):
            lines.append(f"#### 情境 {idx}：{sc.title} [嚴重度: `{sc.severity_level.value}`]")
            lines.append(f"- **反事實前提**：{sc.shock_hypothesis}")
            lines.append(f"- **市場傳導衝擊**：{sc.assumed_market_impact}")
            lines.append(f"- **暴露弱點**：{', '.join(sc.targeted_vulnerabilities)}")
            lines.append("- **專家質詢問題**：")
            for q in sc.challenge_questions_for_experts:
                lines.append(f"  - ❓ {q}")
            lines.append("")

        lines.extend([
            "#### 🛡️ CIO 終審強制防禦核准檢查清單 (Mandatory Checkpoints)",
            "1. **結構性停損防線**：確認是否已具備技術點位或主力籌碼 (AVWAP) 錨定之剛性停損策略？",
            "2. **尾部風險對沖**：若上述極端假設發生，投組最大單日預期虧損是否被控制在 2.5% 以內？",
            "3. **持倉部位安全係數**：是否已依據不確定性調整凱利部位大小（如套用 0.25x 分數凱利）？",
        ])

        return "\n".join(lines)

    def evaluate_inoculation(
        self,
        symbol: str,
        consensus_stance: str = "BUY",
        conviction: float = 0.85,
        key_drivers: Optional[List[str]] = None,
        sector: Optional[str] = None,
        max_scenarios: Optional[int] = None,
    ) -> CounterfactualInoculationResult:
        """
        Generates scenarios and formats inoculation packet for CIO.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        if not self.is_enabled:
            return CounterfactualInoculationResult(
                symbol=symbol,
                consensus_stance=consensus_stance,
                scenarios=[],
                cio_inoculation_prompt="",
                required_defense_checkpoints=[],
                is_stress_tested=False,
                evaluated_at=now_iso,
            )

        scenarios = self.generate_scenarios(
            symbol=symbol,
            consensus_stance=consensus_stance,
            conviction=conviction,
            key_drivers=key_drivers,
            sector=sector,
            max_scenarios=max_scenarios,
        )

        inoculation_prompt = self.build_cio_inoculation_prompt(
            symbol=symbol,
            consensus_stance=consensus_stance,
            scenarios=scenarios,
        )

        checkpoints = [
            "結構性停損防線檢驗",
            "尾部風險最大回撤承受度",
            "部位規模凱利係數防禦折減",
        ]

        return CounterfactualInoculationResult(
            symbol=symbol,
            consensus_stance=consensus_stance,
            scenarios=scenarios,
            cio_inoculation_prompt=inoculation_prompt,
            required_defense_checkpoints=checkpoints,
            is_stress_tested=True,
            evaluated_at=now_iso,
        )
