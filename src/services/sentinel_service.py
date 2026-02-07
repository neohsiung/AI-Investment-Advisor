import logging
import asyncio
from typing import Dict, Any

from src.services.market_data_service import MarketDataService
from src.services.council_service import CouncilService
from src.infrastructure.channels.line_adapter import LineBotAdapter
from src.domain.interfaces import IChannelAdapter

logger = logging.getLogger(__name__)

class SentinelService:
    """
    The Sentinel: 24/7 Proactive Monitoring Service.
    哨兵服務：24/7 主動監控與事件驅動核心。
    
    Responsibilities (職責):
    1. 'Tick' execution (Minutely) - 分鐘級掃描。
    2. Market Sensing (VIX, News, Prices) - 市場感知。
    3. Anomaly Detection (Rule-based Triggers) - 異常偵測。
    4. Council Convener (Triggering Debates) - 召集評議會。
    """

    def __init__(self):
        self.market_service = MarketDataService()
        self.council_service = CouncilService()
        # Dependency Injection (Manual for now)
        self.line_adapter: IChannelAdapter = LineBotAdapter()
        
        # Thresholds (Config should be in DB/Settings, hardcoded for Phase 1)
        self.thresholds = {
            "vix_high": 25.0,
            "vix_extreme": 40.0
        }
        
    async def process_tick(self):
        """
        Main Event Loop Entry Point.
        Called by Scheduler (Local) or Cloud Function (GCP).
        主要事件迴圈入口。由 Scheduler (地端) 或 Cloud Function (雲端) 呼叫。
        """
        try:
            # 1. SENSE: Get Market Context & History for Adaptive Logic
            # We need history for Volatility Regime (MA, StdDev)
            history_data = self.market_service.get_ohlcv("^VIX", days=60)
            
            current_vix = 0.0
            is_anomaly = False
            triggers = []
            
            if history_data and history_data.get("close"):
                 closes = history_data["close"]
                 if len(closes) > 0:
                     current_vix = closes[-1]
                     
                     # Adaptive Logic: Calculate Regime
                     # Use last 30 days (excluding today potentially if live, but here we just take tail)
                     window = 30
                     if len(closes) >= window:
                         recent_closes = closes[-window:]
                         avg_vix = sum(recent_closes) / len(recent_closes)
                         
                         # StdDev Calculation
                         variance = sum([((x - avg_vix) ** 2) for x in recent_closes]) / len(recent_closes)
                         std_dev = variance ** 0.5
                         
                         # Z-Score (How many sigmas away is today?)
                         # Avoid division by zero
                         z_score = (current_vix - avg_vix) / std_dev if std_dev > 0 else 0
                         
                         # Dynamic Trigger Rule: VIX > Mean + 1.5 StdDev
                         # This adapts: In calm markets (VIX=12), trigger might be 15. In crisis (VIX=30), trigger might be 40.
                         threshold = avg_vix + (1.5 * std_dev)
                         
                         logger.info(f"Sentinel Regime: VIX={current_vix:.2f} (MA={avg_vix:.2f}, Sigma={std_dev:.2f}, Threshold={threshold:.2f})")
                         
                         if current_vix > threshold:
                             is_anomaly = True
                             triggers.append(f"Adaptive Volatility Alert (VIX {current_vix:.2f} > {threshold:.2f}, Z-Score={z_score:.1f})")
                     else:
                         # Fallback to static if not enough history
                         if current_vix > self.thresholds["vix_high"]:
                             triggers.append(f"Static Volatility Alert (VIX={current_vix:.2f})")
            
            # 2. ACT: Summon Council if needed
            if triggers:
                topic = f"SENTINEL ALERT: {'; '.join(triggers)}"
                logger.info(f"Sentinel: Triggering Council for {topic}")
                
                context = {
                    "source": "Sentinel",
                    "market_data": {
                        "vix": current_vix,
                        "regime": "High Volatility" if is_anomaly else "Normal"
                    },
                    "triggered_rules": triggers
                }
                
                # Execute Council Session
                result = self.council_service.start_session(topic, context)
                decision = result.get('consensus', 'No Consensus')
                logger.info(f"Sentinel: Council Result Verified. Decision: {decision}")
                
                # 3. NOTIFY: Send LINE Alert if actionable
                # We broadcast to a default user or all users. For Phase 3, we might need a specific USER_ID env.
                # In typical Line Bot, you push to a known user_id.
                import os
                target_user = os.getenv("LINE_USER_ID", "broadcast") 
                
                # Construct Actions based on decision keywords
                actions = []
                if "sell" in decision.lower() or "reduce" in decision.lower():
                     # eToro Signal Mode
                     actions.append({"label": "前往 eToro 下單", "data": "action=etoro_link"})
                elif "buy" in decision.lower():
                     actions.append({"label": "前往 eToro 下單", "data": "action=etoro_link"})
                
                self.line_adapter.send_flex_alert(
                    user_id=target_user,
                    title="⚠️ Sentinel Alert",
                    content=f"**Topic**: {topic}\n\n**Council Consensus**:\n{decision}",
                    actions=actions
                )
                
            else:
                logger.info("Sentinel: Market Normal. No triggers.")
                pass
                
        except Exception as e:
            logger.error(f"Sentinel Tick Error: {e}", exc_info=True)
