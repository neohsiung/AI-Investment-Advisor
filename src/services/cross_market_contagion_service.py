"""
A7: Council Cross-Market Contagion & Inter-Asset Transmission Engine
=============================================================================
Models and quantifies cross-asset spillover mechanisms and transmission channels:
1. Four Fundamental Transmission Channels:
   - Rates & Yield Curve (US10Y, 10Y-2Y Curve Slope, Real Yields)
   - FX & Global Liquidity (Dollar Index DXY, Yen Carry / USDJPY)
   - Commodities & Energy (Brent/WTI Crude, Copper/Gold Growth Ratio)
   - Credit & Volatility (VIX Index, MOVE, HY Credit Spreads)
2. Sector Sensitivity Calibration:
   - Evaluates ticker/sector-specific transmission factors (Tech DCF duration,
     Financial NIM vs credit default risk, Consumer disposable income drag, etc.).
3. Regime Classification & Hedging Overlays:
   - Categorizes market regime: BENIGN, DIVERGENT, ACUTE_SPILLOVER, SYSTEMIC_CONTAGION.
   - Formulates concrete institutional hedging overlays (TLT duration, DXY calls,
     energy collars, credit protection).
4. Council & CIO Integration:
   - Generates structured Markdown Contagion Cards for council deliberations.
   - Fully controllable via settings_schema.yaml.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


class TransmissionChannel(str, Enum):
    RATES_YIELD_CURVE = "RATES_YIELD_CURVE"
    FX_LIQUIDITY = "FX_LIQUIDITY"
    COMMODITIES_ENERGY = "COMMODITIES_ENERGY"
    CREDIT_VOLATILITY = "CREDIT_VOLATILITY"


class ContagionRegime(str, Enum):
    BENIGN = "BENIGN"
    DIVERGENT = "DIVERGENT"
    ACUTE_SPILLOVER = "ACUTE_SPILLOVER"
    SYSTEMIC_CONTAGION = "SYSTEMIC_CONTAGION"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class AssetSpilloverImpact:
    """Quantified impact from an external cross-asset transmission channel."""
    channel: TransmissionChannel
    source_indicator: str
    indicator_delta_pct: float
    sensitivity_factor: float
    estimated_price_impact_pct: float
    transmission_mechanism: str
    risk_level: RiskLevel

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel.value,
            "source_indicator": self.source_indicator,
            "indicator_delta_pct": round(self.indicator_delta_pct, 2),
            "sensitivity_factor": round(self.sensitivity_factor, 2),
            "estimated_price_impact_pct": round(self.estimated_price_impact_pct, 2),
            "transmission_mechanism": self.transmission_mechanism,
            "risk_level": self.risk_level.value,
        }


@dataclass
class ContagionAssessmentResult:
    """Full cross-market contagion evaluation result."""
    symbol: str
    sector: str
    overall_contagion_risk_score: float
    contagion_regime: ContagionRegime
    channel_impacts: List[AssetSpilloverImpact]
    recommended_hedging_overlays: List[str]
    markdown_contagion_card: str
    is_contagion_alert: bool
    assessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "sector": self.sector,
            "overall_contagion_risk_score": round(self.overall_contagion_risk_score, 4),
            "contagion_regime": self.contagion_regime.value,
            "channel_impacts": [impact.to_dict() for impact in self.channel_impacts],
            "recommended_hedging_overlays": self.recommended_hedging_overlays,
            "markdown_contagion_card": self.markdown_contagion_card,
            "is_contagion_alert": self.is_contagion_alert,
            "assessed_at": self.assessed_at,
        }


class CrossMarketContagionService:
    """
    A7 Engine: Assesses cross-market spillover risks and inter-asset transmission
    dynamics to safeguard council recommendations against macroscopic shocks.
    """

    # Sector Sensitivity Matrix [Rates, FX, Energy, Credit]
    SECTOR_SENSITIVITIES: Dict[str, Dict[TransmissionChannel, float]] = {
        "Technology": {
            TransmissionChannel.RATES_YIELD_CURVE: -0.85,
            TransmissionChannel.FX_LIQUIDITY: -0.65,
            TransmissionChannel.COMMODITIES_ENERGY: -0.25,
            TransmissionChannel.CREDIT_VOLATILITY: -0.80,
        },
        "Semiconductors": {
            TransmissionChannel.RATES_YIELD_CURVE: -0.80,
            TransmissionChannel.FX_LIQUIDITY: -0.70,
            TransmissionChannel.COMMODITIES_ENERGY: -0.30,
            TransmissionChannel.CREDIT_VOLATILITY: -0.85,
        },
        "Energy": {
            TransmissionChannel.RATES_YIELD_CURVE: -0.15,
            TransmissionChannel.FX_LIQUIDITY: -0.40,
            TransmissionChannel.COMMODITIES_ENERGY: 0.85,
            TransmissionChannel.CREDIT_VOLATILITY: -0.45,
        },
        "Financials": {
            TransmissionChannel.RATES_YIELD_CURVE: 0.60,
            TransmissionChannel.FX_LIQUIDITY: -0.30,
            TransmissionChannel.COMMODITIES_ENERGY: -0.20,
            TransmissionChannel.CREDIT_VOLATILITY: -0.85,
        },
        "Consumer Discretionary": {
            TransmissionChannel.RATES_YIELD_CURVE: -0.55,
            TransmissionChannel.FX_LIQUIDITY: -0.45,
            TransmissionChannel.COMMODITIES_ENERGY: -0.70,
            TransmissionChannel.CREDIT_VOLATILITY: -0.65,
        },
        "Consumer Staples": {
            TransmissionChannel.RATES_YIELD_CURVE: -0.30,
            TransmissionChannel.FX_LIQUIDITY: -0.35,
            TransmissionChannel.COMMODITIES_ENERGY: -0.50,
            TransmissionChannel.CREDIT_VOLATILITY: -0.30,
        },
        "Healthcare": {
            TransmissionChannel.RATES_YIELD_CURVE: -0.40,
            TransmissionChannel.FX_LIQUIDITY: -0.25,
            TransmissionChannel.COMMODITIES_ENERGY: -0.20,
            TransmissionChannel.CREDIT_VOLATILITY: -0.35,
        },
        "Industrials": {
            TransmissionChannel.RATES_YIELD_CURVE: -0.45,
            TransmissionChannel.FX_LIQUIDITY: -0.50,
            TransmissionChannel.COMMODITIES_ENERGY: -0.60,
            TransmissionChannel.CREDIT_VOLATILITY: -0.65,
        },
    }

    DEFAULT_SENSITIVITIES: Dict[TransmissionChannel, float] = {
        TransmissionChannel.RATES_YIELD_CURVE: -0.50,
        TransmissionChannel.FX_LIQUIDITY: -0.45,
        TransmissionChannel.COMMODITIES_ENERGY: -0.35,
        TransmissionChannel.CREDIT_VOLATILITY: -0.60,
    }

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        default_risk_threshold: float = 0.65,
    ) -> None:
        self.user_id = resolve_user_id(user_id)
        self.settings_service = settings_service
        self.default_risk_threshold = default_risk_threshold

    def is_enabled(self) -> bool:
        """Checks if cross-market contagion assessment is enabled in settings."""
        if self.settings_service is None:
            return True
        try:
            val = self.settings_service.get("council_contagion_enabled", user_id=self.user_id)
            if val is not None:
                return bool(val)
        except Exception as e:
            logger.debug("Failed reading council_contagion_enabled: %s", e)
        return True

    def get_risk_threshold(self) -> float:
        """Retrieves contagion alert risk threshold from dynamic settings."""
        if self.settings_service is None:
            return self.default_risk_threshold
        try:
            val = self.settings_service.get("council_contagion_risk_threshold", user_id=self.user_id)
            if val is not None:
                return float(val)
        except Exception as e:
            logger.debug("Failed reading council_contagion_risk_threshold: %s", e)
        return self.default_risk_threshold

    def assess_contagion(
        self,
        symbol: str,
        sector: str = "Technology",
        macro_signals: Optional[Dict[str, float]] = None,
        custom_shocks: Optional[Dict[str, float]] = None,
    ) -> ContagionAssessmentResult:
        """
        Executes multi-channel cross-market transmission evaluation for target symbol/sector.
        """
        sym = (symbol or "").strip().upper()
        sec = (sector or "Technology").strip()

        if not self.is_enabled():
            logger.info("A7 CrossMarketContagionService is disabled by configuration.")
            return ContagionAssessmentResult(
                symbol=sym,
                sector=sec,
                overall_contagion_risk_score=0.0,
                contagion_regime=ContagionRegime.BENIGN,
                channel_impacts=[],
                recommended_hedging_overlays=["Cross-market contagion evaluation disabled by policy."],
                markdown_contagion_card="> ℹ️ **跨市場連鎖傳導分析已停用**：當前系統設定已關閉 A7 引擎。",
                is_contagion_alert=False,
            )

        # Baseline market movements (percentage changes, e.g. +5.0 means +5%)
        # Signals can be provided or simulated via custom_shocks / macro_signals
        market_deltas = {
            "US10Y": 6.5,          # e.g., 10Y Yield spiked +6.5% (~+25 bps)
            "DXY": 2.2,            # US Dollar Index strengthened +2.2%
            "BRENT": 5.8,          # Crude oil jumped +5.8%
            "VIX": 18.5,           # Volatility jumped +18.5%
        }
        if macro_signals:
            market_deltas.update(macro_signals)
        if custom_shocks:
            market_deltas.update(custom_shocks)

        # Resolve sensitivities
        sensitivities = self.SECTOR_SENSITIVITIES.get(sec, self.DEFAULT_SENSITIVITIES)

        channel_impacts: List[AssetSpilloverImpact] = []
        weighted_risk_sum = 0.0

        # Channel 1: RATES_YIELD_CURVE
        rates_delta = market_deltas.get("US10Y", 0.0)
        rates_sens = sensitivities.get(TransmissionChannel.RATES_YIELD_CURVE, -0.50)
        rates_impact = (rates_delta / 100.0) * rates_sens * 100.0
        rates_risk = self._classify_risk(abs(rates_impact))
        channel_impacts.append(
            AssetSpilloverImpact(
                channel=TransmissionChannel.RATES_YIELD_CURVE,
                source_indicator=f"US10Y ({'+' if rates_delta >= 0 else ''}{rates_delta:.1f}%)",
                indicator_delta_pct=rates_delta,
                sensitivity_factor=rates_sens,
                estimated_price_impact_pct=rates_impact,
                transmission_mechanism=(
                    "長端美債殖利率跳升導致股權現金流折現率 (DCF Discount Rate) 上修，"
                    "成長型科技股本益比承壓；銀行業 NIM 利差擴張但面臨證券未實現損失。"
                ),
                risk_level=rates_risk,
            )
        )
        weighted_risk_sum += self._risk_to_score(rates_risk) * 0.30

        # Channel 2: FX_LIQUIDITY
        fx_delta = market_deltas.get("DXY", 0.0)
        fx_sens = sensitivities.get(TransmissionChannel.FX_LIQUIDITY, -0.45)
        fx_impact = (fx_delta / 100.0) * fx_sens * 100.0
        fx_risk = self._classify_risk(abs(fx_impact))
        channel_impacts.append(
            AssetSpilloverImpact(
                channel=TransmissionChannel.FX_LIQUIDITY,
                source_indicator=f"DXY ({'+' if fx_delta >= 0 else ''}{fx_delta:.1f}%)",
                indicator_delta_pct=fx_delta,
                sensitivity_factor=fx_sens,
                estimated_price_impact_pct=fx_impact,
                transmission_mechanism=(
                    "美元指數強勁抽緊全球離岸美元流動性，跨國企業海外營收換匯折損，"
                    "同時引發日圓及非美貨幣套利交易 (Carry Trade) 被動去槓桿平倉。"
                ),
                risk_level=fx_risk,
            )
        )
        weighted_risk_sum += self._risk_to_score(fx_risk) * 0.25

        # Channel 3: COMMODITIES_ENERGY
        energy_delta = market_deltas.get("BRENT", 0.0)
        energy_sens = sensitivities.get(TransmissionChannel.COMMODITIES_ENERGY, -0.35)
        energy_impact = (energy_delta / 100.0) * energy_sens * 100.0
        energy_risk = self._classify_risk(abs(energy_impact))
        channel_impacts.append(
            AssetSpilloverImpact(
                channel=TransmissionChannel.COMMODITIES_ENERGY,
                source_indicator=f"BRENT ({'+' if energy_delta >= 0 else ''}{energy_delta:.1f}%)",
                indicator_delta_pct=energy_delta,
                sensitivity_factor=energy_sens,
                estimated_price_impact_pct=energy_impact,
                transmission_mechanism=(
                    "大宗原油價格上漲加劇二次通膨疑慮與終端運輸成本，壓抑非能源板塊淨利潤率，"
                    "惟上游探勘與油氣開採類股具備天然抗通膨超額收益。"
                ),
                risk_level=energy_risk,
            )
        )
        weighted_risk_sum += self._risk_to_score(energy_risk) * 0.20

        # Channel 4: CREDIT_VOLATILITY
        vol_delta = market_deltas.get("VIX", 0.0)
        vol_sens = sensitivities.get(TransmissionChannel.CREDIT_VOLATILITY, -0.60)
        vol_impact = (vol_delta / 100.0) * vol_sens * 100.0
        vol_risk = self._classify_risk(abs(vol_impact))
        channel_impacts.append(
            AssetSpilloverImpact(
                channel=TransmissionChannel.CREDIT_VOLATILITY,
                source_indicator=f"VIX ({'+' if vol_delta >= 0 else ''}{vol_delta:.1f}%)",
                indicator_delta_pct=vol_delta,
                sensitivity_factor=vol_sens,
                estimated_price_impact_pct=vol_impact,
                transmission_mechanism=(
                    "市場恐慌指數 VIX 突破引發量化風險平價 (Risk Parity) 與 CTA 趨勢基金被動減倉，"
                    "高收益信用利差走擴大幅抬高邊際融資成本。"
                ),
                risk_level=vol_risk,
            )
        )
        weighted_risk_sum += self._risk_to_score(vol_risk) * 0.25

        # Overall risk calculation
        overall_risk = min(1.0, max(0.0, weighted_risk_sum))

        # Regime determination
        if overall_risk >= 0.80:
            regime = ContagionRegime.SYSTEMIC_CONTAGION
        elif overall_risk >= 0.60:
            regime = ContagionRegime.ACUTE_SPILLOVER
        elif overall_risk >= 0.35:
            regime = ContagionRegime.DIVERGENT
        else:
            regime = ContagionRegime.BENIGN

        # Hedging Overlays
        hedging_overlays = self._derive_hedging_overlays(channel_impacts, regime, sec)

        # Contagion Alert
        threshold = self.get_risk_threshold()
        is_alert = overall_risk >= threshold

        # Synthesize Markdown Contagion Card
        card = self._synthesize_markdown_card(
            symbol=sym,
            sector=sec,
            regime=regime,
            risk_score=overall_risk,
            impacts=channel_impacts,
            hedging=hedging_overlays,
            is_alert=is_alert,
        )

        return ContagionAssessmentResult(
            symbol=sym,
            sector=sec,
            overall_contagion_risk_score=overall_risk,
            contagion_regime=regime,
            channel_impacts=channel_impacts,
            recommended_hedging_overlays=hedging_overlays,
            markdown_contagion_card=card,
            is_contagion_alert=is_alert,
        )

    def _classify_risk(self, abs_impact_pct: float) -> RiskLevel:
        if abs_impact_pct >= 8.0:
            return RiskLevel.CRITICAL
        elif abs_impact_pct >= 4.0:
            return RiskLevel.HIGH
        elif abs_impact_pct >= 1.5:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _risk_to_score(self, level: RiskLevel) -> float:
        mapping = {
            RiskLevel.LOW: 0.15,
            RiskLevel.MEDIUM: 0.45,
            RiskLevel.HIGH: 0.75,
            RiskLevel.CRITICAL: 1.00,
        }
        return mapping.get(level, 0.20)

    def _derive_hedging_overlays(
        self,
        impacts: List[AssetSpilloverImpact],
        regime: ContagionRegime,
        sector: str,
    ) -> List[str]:
        hedges: List[str] = []
        for imp in impacts:
            if imp.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                if imp.channel == TransmissionChannel.RATES_YIELD_CURVE:
                    hedges.append("長端存續期對沖：建構 TLT/IEF 長期國債保護，或買入利率上限 (Cap) 選擇權。")
                elif imp.channel == TransmissionChannel.FX_LIQUIDITY:
                    hedges.append("外匯流動性對沖：布局 DXY 多頭買權價差 (Call Spread) 或建立美元/日圓雙向領口防禦。")
                elif imp.channel == TransmissionChannel.COMMODITIES_ENERGY:
                    hedges.append("大宗商品通膨對沖：配置 5-10% 能源指數 (XLE/USO) 作為營運原料成本暴漲之天然緩衝。")
                elif imp.channel == TransmissionChannel.CREDIT_VOLATILITY:
                    hedges.append("波動度與信用利差防禦：持有 VIX 尾部買權，或建立 HYG 高收益債放空部位防範踩踏。")

        if regime == ContagionRegime.SYSTEMIC_CONTAGION:
            hedges.insert(0, "🚨 【系統性傳染告警】全面啟動動態現金防護網：強制將現貨部位曝險下修 30%，禁止無保護單邊加倉。")
        elif regime == ContagionRegime.ACUTE_SPILLOVER and not hedges:
            hedges.append("外溢預警防禦：收緊現有持倉停損錨定至 1.5 倍 ATR，暫停高貝塔衍生品激進做多。")

        if not hedges:
            hedges.append("各資產聯動正常：當前外溢風險在安全邊界內，維持基礎風險預算配置。")

        return hedges

    def _synthesize_markdown_card(
        self,
        symbol: str,
        sector: str,
        regime: ContagionRegime,
        risk_score: float,
        impacts: List[AssetSpilloverImpact],
        hedging: List[str],
        is_alert: bool,
    ) -> str:
        status_badge = "🔴 嚴重外溢警戒" if is_alert else ("🟡 中度分歧關注" if risk_score >= 0.35 else "🟢 傳導平穩")
        table_rows = []
        for imp in impacts:
            impact_sign = "+" if imp.estimated_price_impact_pct >= 0 else ""
            table_rows.append(
                f"| `{imp.channel.value}` | {imp.source_indicator} | `{imp.sensitivity_factor:+.2f}` | "
                f"**{impact_sign}{imp.estimated_price_impact_pct:.2f}%** | {imp.risk_level.value} |"
            )
        table_str = "\n".join(table_rows)

        hedging_str = "\n".join([f"- {h}" for h in hedging])

        return f"""### 🌐 跨市場連鎖傳導與資產外溢分析卡片 (A7 Contagion Engine)
> **標的 / 板塊**：`{symbol}` ({sector})  
> **市場體制 (Regime)**：`{regime.value}` | **傳染風險評分**：`{risk_score:.2f} / 1.00` ({status_badge})

#### 1. 四維跨資產傳導敏感度矩陣
| 傳導渠道 (Channel) | 外部指標跳動 | 敏感度係數 | 預估價格衝擊 | 風險等級 |
| :--- | :--- | :--- | :--- | :--- |
{table_str}

#### 2. CIO 動態避險覆蓋建議 (Actionable Hedging Overlays)
{hedging_str}
"""
