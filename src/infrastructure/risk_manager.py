
from typing import Dict, Any, List
from datetime import datetime
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.repositories.settings_repository import SqliteSettingsRepository
from src.utils.logger import setup_logger

logger = setup_logger("RiskManager")

class RiskManager:
    """
    Centralized Risk Management Component.
    Enforces limits and circuit breakers across all brokers.
    """
    def __init__(self):
        self.transaction_repo = SqliteTransactionRepository()
        self.settings_repo = SqliteSettingsRepository()
        
        # Default Limits
        self.default_max_daily_trades = 10
        self.default_loss_streak_limit = 3
        self.default_holding_days_limit = 30
        self.default_loss_pct_threshold = 0.20 # 20%

    def _get_setting(self, user_id: str, key: str, default: Any) -> Any:
        val = self.settings_repo.get(user_id, key)
        return val if val is not None else default

    def _set_setting(self, user_id: str, key: str, value: str):
        self.settings_repo.set(user_id, key, str(value))

    def check_constraints(self, user_id: str, history: List[Dict[str, Any]] = None, current_positions: List[Any] = None) -> bool:
        """
        Check if trading is allowed for this user based on:
        1. Global Switch
        2. Daily Limits
        3. Circuit Breakers (Loss Streak, Drawdown)
        """
        # 0. Global Check
        enabled = self._get_setting(user_id, "ai_trading_enabled", "true")
        if enabled.lower() != "true":
            logger.warning(f"Risk Check: Global trading disabled for {user_id}")
            return False

        # 1. Daily Limit
        max_daily = int(self._get_setting(user_id, "ai_max_daily_trades", self.default_max_daily_trades))
        today_str = datetime.now().strftime('%Y-%m-%d')
        daily_count = self._get_daily_trade_count(user_id, today_str)
        if daily_count >= max_daily:
            logger.warning(f"Risk Check: Daily trade limit reached ({daily_count}/{max_daily}) for {user_id}")
            return False

        # 2. Circuit Breaker (Loss Analysis)
        if self._is_circuit_breaker_triggered(user_id, history, current_positions):
            # Auto-disable and return False
            self._set_setting(user_id, "ai_trading_enabled", "false")
            logger.error(f"RISK ALERT: Circuit Breaker Triggered for {user_id}. AI Trading Disabled.")
            return False

        return True

    def _get_daily_trade_count(self, user_id: str, date_str: str) -> int:
        """
        Count trades in DB for today.
        """
        txs = self.transaction_repo.get_all_by_user(user_id)
        count = 0
        for tx in txs:
            if str(tx.trade_date).startswith(date_str):
                count += 1
        return count

    def _is_circuit_breaker_triggered(self, user_id: str, history=None, positions=None) -> bool:
        """
        Analyze losses and drawdowns.
        Required: history list (dicts with 'Profit', 'CloseDateTime' keys roughly)
                  positions list (objects with open_date, unrealized_pnl)
        If data is missing, we skip the check (fail open/safe based on philosophy).
        Here we fail open (allow trading) but log warning if data missing? No, safer to be conservative?
        Let's assume data is provided by Broker adapter.
        """
        consecutive_limit = int(self._get_setting(user_id, "cb_loss_streak", self.default_loss_streak_limit))
        loss_pct_limit = float(self._get_setting(user_id, "cb_loss_pct", self.default_loss_pct_threshold))
        holding_days_limit = int(self._get_setting(user_id, "cb_holding_days", self.default_holding_days_limit))

        # Check Consecutive Losses
        if history:
            # Sort history by close date desc
            # Attempt to normalize key access
            # Assuming history is normalized by Broker Adapter before passing, OR we handle generic dicts here
            # Let's try to sort by 'date' if available
            try:
                sorted_hist = sorted(history, key=lambda x: x.get('date', ''), reverse=True)
                streak = 0
                for trade in sorted_hist:
                    try:
                        profit = float(trade.get('profit', 0))
                        if profit < 0:
                            streak += 1
                        else:
                            break
                    except:
                        continue
                
                if streak >= consecutive_limit:
                    logger.warning(f"CB Trigger: {streak} consecutive losses.")
                    return True
            except Exception as e:
                logger.warning(f"Risk Manager could not parse history for streak check: {e}")

        # Check Holding Time & Loss (Deep Drawdown)
        if positions:
            now = datetime.now()
            for pos in positions:
                # Expecting Position object
                try:
                    # Access attribute or dict
                    open_date = getattr(pos, 'open_date', None)
                    current_val = getattr(pos, 'market_value', 0)
                    pnl = getattr(pos, 'unrealized_pnl', 0) # Absolute PnL
                    cost = current_val - pnl # Approx basis if not provided
                    
                    if not open_date: continue
                    
                    days_held = (now - open_date).days
                    
                    # ROI %
                    roi = (pnl / cost) if cost > 0 else 0
                    
                    if days_held >= holding_days_limit and roi < -loss_pct_limit:
                         logger.warning(f"CB Trigger: Position {getattr(pos, 'symbol', '?')} held {days_held} days with {roi*100:.1f}% loss.")
                         return True
                except Exception as e:
                    logger.warning(f"Risk Manager position check error: {e}")
                    continue

        return False
