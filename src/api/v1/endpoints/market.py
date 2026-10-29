"""
Market-day API — whether the New York date is a NYSE trading day. One cheap call with no database and no LLM,
so the dashboard can say "closed today" while its slower data is still loading.
美股日 API：紐約日期那天是不是 NYSE 交易日。不查資料庫、不用 LLM，儀表板的資料還在載入時就能先說「今天休市」。
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from src.api.v1.dependencies import get_current_user_id
from src.utils.logger import setup_logger
from src.utils.market_clock import MarketClock

logger = setup_logger("API_Market")
router = APIRouter()


@router.get("/today")
async def get_market_today(user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    """state: closed | trading_day | unknown (no exchange calendar installed: never a guess).
    state：closed 休市、trading_day 交易日、unknown 沒有交易所日曆（不猜）。"""
    try:
        session = MarketClock().session_today()
    except Exception as e:
        logger.error(f"get_market_today failed: {e}", exc_info=True)
        # Generic detail: the cause is in the log above, never echoed to the client (CodeQL py/stack-trace-exposure).
        raise HTTPException(status_code=500, detail="Market day lookup failed") from None
    state = "unknown" if session is None else ("trading_day" if session else "closed")
    return {"status": "success", "data": {"state": state}}
