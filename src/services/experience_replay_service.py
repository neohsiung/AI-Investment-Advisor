import logging
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from src.repositories.sentinel_repository import AlchemySentinelRepository, ISentinelRepository
from src.repositories.transaction_repository import AlchemyTransactionRepository, ITransactionRepository
from src.data.database import get_db_connection
from sqlalchemy import text

logger = logging.getLogger(__name__)

class ExperienceReplayService:
    """
    Experience Replay Service (Rule #8/Rule #9).
    復盤服務：分析警報歷史與投資組合表現以動態調整參數。
    
    Analyses: 
    1. Signal-to-Noise Ratio (SNR): Did an alert lead to correct action?
    2. False Positive Mitigation: Adjust thresholds upwards if ROI didn't justify the alert.
    """
    
    def __init__(
        self, 
        sentinel_repo: ISentinelRepository = None,
        trans_repo: ITransactionRepository = None
    ):
        self.sentinel_repo = sentinel_repo or AlchemySentinelRepository()
        self.trans_repo = trans_repo or AlchemyTransactionRepository()

    def optimize_thresholds(self, user_id: str) -> Dict[str, Any]:
        """
        Main optimization loop.
        主優化迴圈。
        """
        results = {}
        logger.info(f"Starting Experience Replay optimization for user: {user_id}")
        
        # 1. Analyze Alert Density vs Portfolio Volatility
        # 2. Adjust VIX thresholds if alerts are too frequent (> 3 per day)
        vix_adj = self._optimize_vix_thresholds(user_id)
        if vix_adj:
            results["vix"] = vix_adj
            
        return results

    def _optimize_vix_thresholds(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Adjust VIX thresholds based on recent alert frequency.
        基於近期警報頻率調整 VIX 閾值。
        """
        try:
            # Count Sentinel alerts in the last 7 days
            with get_db_connection() as conn:
                query = text("""
                    SELECT COUNT(*) FROM event_logs 
                    WHERE source = 'Sentinel' 
                    AND title LIKE '%VIX%'
                    AND timestamp >= datetime('now', '-7 days')
                """)
                alert_count = conn.execute(query).scalar() or 0
                
            if alert_count > 10: # More than ~1.5 per day is "noisy"
                current = self.sentinel_repo.get_all_thresholds()
                v_high = current.get("vix_high", 25.0)
                
                # Increase threshold by 5% to reduce noise
                new_val = round(v_high * 1.05, 2)
                self.sentinel_repo.update_threshold(
                    "vix_high", 
                    new_val, 
                    "ExperienceReplay", 
                    f"Reduced noise: {alert_count} alerts in 7d detected."
                )
                return {"key": "vix_high", "old": v_high, "new": new_val, "reason": "High frequency noise suppression"}
                
        except Exception as e:
            logger.error(f"VIX optimization failed: {e}")
        return None

    def record_feedback(self, signal_id: str, success: bool, roi_hint: float = 0.0) -> None:
        """
        Manual or semi-automated feedback loop for specific signals.
        針對特定訊號的手動或半自動回饋迴圈。
        """
        # Future enhancement: correlate signal with 30d forward returns
        pass
