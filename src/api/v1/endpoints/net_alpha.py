"""
Net alpha API — exposes NetAlphaAttributionService so the project's one success
metric (annualised excess return over SPY, net of model + subscription cost) is
visible outside Telegram. Pure SQL/market-data, zero LLM cost.
淨 Alpha API：把專案唯一的成功指標（扣除模型與訂閱成本後相對 SPY 的年化超額報酬）
從 Telegram 延伸到 Dashboard，不消耗任何 LLM。
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.v1.dependencies import get_current_user_id
from src.utils.logger import setup_logger

logger = setup_logger("API_NetAlpha")
router = APIRouter()


@router.get("")
async def get_net_alpha(
    lookback_days: int = Query(30, ge=7, le=365),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """Time-weighted gross alpha, cost drag and net alpha with data-quality markers.
    時間加權毛 Alpha、成本拖累與淨 Alpha，並附資料品質標記。"""
    try:
        from src.services.net_alpha_attribution_service import NetAlphaAttributionService

        report = await NetAlphaAttributionService(user_id=user_id).calculate_complete_report(
            lookback_days=lookback_days
        )
        return {"status": "success", "data": report.to_dict()}
    except Exception as e:
        logger.error(f"get_net_alpha failed: {e}", exc_info=True)
        # Generic detail: the cause is in the log above, never echoed to the client (CodeQL py/stack-trace-exposure).
        # 對外只回通用訊息；原因已記錄在上方日誌。
        raise HTTPException(status_code=500, detail="Net alpha report failed")
