
from typing import Dict, Any, Optional
from src.services.etoro_service import EtoroService
from src.utils.logger import setup_logger

logger = setup_logger("EtoroTool")

class EtoroTradingTool:
    """
    Tool for AI Agents to execute trades on Etoro.
    Restricted by EtoroService constraints (Max Trades, Circuit Breaker).
    """
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.service = EtoroService()

    def get_portfolio(self) -> Dict[str, Any]:
        """
        Get current portfolio status.
        """
        return self.service.get_portfolio()

    def place_order(self, ticker: str, action: str, amount: float, leverage: int = 1, reason: str = "AI Decision") -> Dict[str, Any]:
        """
        Place a trade order.
        Args:
            ticker: Symbol (e.g. AAPL)
            action: BUY or SELL
            amount: Amount in USD
            leverage: Leverage (X1, X2, X5...)
            reason: Why this trade is made (for logging/review)
        """
        logger.info(f"Agent Request: {action} {ticker} ${amount} (Lev {leverage}) Reason: {reason}")
        
        # Normalize action
        action = action.upper()
        if action not in ['BUY', 'SELL']:
            return {"status": "error", "message": "Invalid action. Use BUY or SELL."}

        return self.service.execute_trade(
            user_id=self.user_id,
            ticker=ticker,
            action=action,
            amount=amount,
            leverage=leverage,
            reason=reason
        )

    def check_status(self) -> Dict[str, Any]:
        """
        Check if trading is enabled and current constraints status.
        """
        enabled = self.service.check_constraints(self.user_id)
        # We can expose more details if we add getters to service
        return {
            "trading_enabled": enabled,
            "system_status": "NORMAL" if enabled else "PAUSED_RISK_CONTROL"
        }
