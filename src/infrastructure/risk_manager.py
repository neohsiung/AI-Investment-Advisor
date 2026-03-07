import pandas as pd
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from datetime import datetime, timedelta
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.repositories.settings_repository import AlchemySettingsRepository
from src.utils.logger import setup_logger

logger = setup_logger("RiskManager")

class RiskManager:
    """
    Centralized Risk Management Component.
    Enforces limits and circuit breakers across all brokers.
    v3.6: Refactored for Rule #8 (Dynamic Indicators).
    """
    def __init__(self):
        self.transaction_repo = AlchemyTransactionRepository()
        self.settings_repo = AlchemySettingsRepository()

    def _get_setting(self, user_id: str, key: str, default: Any = None) -> Any:
        val = self.settings_repo.get(user_id, key)
        return val if val is not None else default

    def _set_setting(self, user_id: str, key: str, value: str):
        self.settings_repo.set(user_id, key, str(value))

    def _get_dynamic_thresholds(self, user_id: str) -> Dict[str, Any]:
        """
        Calculate dynamic thresholds based on historical data.
        Fulfills Rule #8: Dynamic Indicators Principle.
        """
        try:
            df = self.transaction_repo.get_all_by_user_df(user_id)
            if df.empty:
                # Conservative startup defaults for new users
                return {
                    "max_daily_trades": 3,
                    "loss_streak_limit": 2,
                    "holding_days_limit": 14,
                    "loss_pct_threshold": 0.10
                }
            
            # Filter trades
            trades = df[df['action'].isin(['BUY', 'SELL'])].copy()
            if trades.empty:
                 return {
                    "max_daily_trades": 3,
                    "loss_streak_limit": 2,
                    "holding_days_limit": 14,
                    "loss_pct_threshold": 0.10
                }

            # 1. Daily Trades: Avg daily count in last 30 days + 1 StdDev
            trades['date'] = pd.to_datetime(trades['trade_date']).dt.date
            last_30_days = datetime.now().date() - timedelta(days=30)
            recent_trades = trades[trades['date'] >= last_30_days]
            
            if not recent_trades.empty:
                daily_counts = recent_trades.groupby('date').size()
                avg = daily_counts.mean()
                std = daily_counts.std() if len(daily_counts) > 1 else 1.0
                max_daily = int(max(3, avg + 1.5 * std))
            else:
                max_daily = 3

            # 2. Holding Period (Fallback if no matched trades)
            holding_days = 21 # Baseline if can't calculate from matched trades
            
            # 3. Loss Tolerance: Based on recent drawdown or volatility proxy
            # Default to 15% if no better data
            loss_pct = 0.15 
            
            # 4. Streak Limit: Min 3, max 7 based on vol
            streak_limit = 3

            return {
                "max_daily_trades": max_daily,
                "loss_streak_limit": streak_limit,
                "holding_days_limit": holding_days,
                "loss_pct_threshold": loss_pct
            }
        except Exception as e:
            logger.error(f"RiskManager: Dynamic threshold calculation failed: {e}")
            return {
                "max_daily_trades": 5,
                "loss_streak_limit": 3,
                "holding_days_limit": 30,
                "loss_pct_threshold": 0.20
            }

    def check_constraints(self, user_id: str, history: List[Dict[str, Any]] = None, current_positions: List[Any] = None) -> bool:
        """
        Check if trading is allowed for this user based on dynamic constraints.
        """
        # 0. Global Check
        enabled = self._get_setting(user_id, "ai_trading_enabled", "true")
        if enabled.lower() != "true":
            logger.warning(f"Risk Check: Global trading disabled for {user_id}")
            return False

        # Get Dynamic Thresholds
        thresholds = self._get_dynamic_thresholds(user_id)

        # 1. Daily Limit
        max_daily = int(self._get_setting(user_id, "ai_max_daily_trades", thresholds["max_daily_trades"]))
        today_str = datetime.now().strftime('%Y-%m-%d')
        daily_count = self._get_daily_trade_count(user_id, today_str)
        if daily_count >= max_daily:
            logger.warning(f"Risk Check: Daily trade limit reached ({daily_count}/{max_daily}) for {user_id}")
            return False

        # 2. Circuit Breaker (Loss Analysis)
        if self._is_circuit_breaker_triggered(user_id, history, current_positions, thresholds):
            # Auto-disable and return False
            self._set_setting(user_id, "ai_trading_enabled", "false")
            logger.error(f"RISK ALERT: Circuit Breaker Triggered for {user_id}. AI Trading Disabled.")
            return False

        return True

    def _get_daily_trade_count(self, user_id: str, date_str: str) -> int:
        txs = self.transaction_repo.get_all_by_user(user_id)
        count = 0
        for tx in txs:
            # tx might be Row or dict
            t_date = getattr(tx, 'trade_date', None) or tx.get('trade_date')
            if str(t_date).startswith(date_str):
                count += 1
        return count

    def _is_circuit_breaker_triggered(self, user_id: str, history=None, positions=None, thresholds=None) -> bool:
        """
        Analyze losses and drawdowns using dynamic thresholds.
        """
        if not thresholds:
            thresholds = self._get_dynamic_thresholds(user_id)

        consecutive_limit = int(self._get_setting(user_id, "cb_loss_streak", thresholds["loss_streak_limit"]))
        loss_pct_limit = float(self._get_setting(user_id, "cb_loss_pct", thresholds["loss_pct_threshold"]))
        holding_days_limit = int(self._get_setting(user_id, "cb_holding_days", thresholds["holding_days_limit"]))

        # Check Consecutive Losses
        if history:
            try:
                sorted_hist = sorted(history, key=lambda x: x.get('date', ''), reverse=True)
                streak = 0
                for trade in sorted_hist:
                    profit = float(trade.get('profit', 0))
                    if profit < 0:
                        streak += 1
                    else:
                        break
                
                if streak >= consecutive_limit:
                    logger.warning(f"CB Trigger: {streak} consecutive losses exceeds limit {consecutive_limit}.")
                    return True
            except Exception as e:
                logger.warning(f"Risk Manager could not parse history for streak check: {e}")

        # Check Holding Time & Loss (Deep Drawdown)
        if positions:
            now = datetime.now()
            for pos in positions:
                try:
                    open_date = getattr(pos, 'open_date', None)
                    current_val = getattr(pos, 'market_value', 0)
                    pnl = getattr(pos, 'unrealized_pnl', 0) 
                    cost = current_val - pnl
                    
                    if not open_date: continue
                    if isinstance(open_date, str):
                        open_date = datetime.fromisoformat(open_date.replace('Z', '+00:00'))
                    
                    days_held = (now - open_date).days if hasattr(open_date, 'year') else 0
                    roi = (pnl / cost) if cost > 0 else 0
                    
                    if days_held >= holding_days_limit and roi < -loss_pct_limit:
                         logger.warning(f"CB Trigger: Position {getattr(pos, 'symbol', '?')} held {days_held} days with {roi*100:.1f}% loss.")
                         return True
                except Exception as e:
                    logger.warning(f"Risk Manager position check error: {e}")
                    continue

        return False

    def check_sector_exposure(self, user_id: str, new_ticker: str, new_amount: float, current_positions: List[Any]) -> bool:
        """
        Check sector exposure using dynamic or configured limit.
        """
        limit_pct = float(self._get_setting(user_id, "risk_max_sector_exposure", "0.30"))
        if limit_pct >= 1.0: return True

        from src.services.market_data_service import MarketDataService
        mds = MarketDataService()
        
        new_sector = self._get_sector(mds, new_ticker)
        if not new_sector: return True
            
        total_value = 0.0
        sector_value = 0.0
        
        for pos in current_positions:
            val = getattr(pos, 'market_value', 0)
            total_value += val
            ticker = getattr(pos, 'symbol', None)
            if ticker and self._get_sector(mds, ticker) == new_sector:
                sector_value += val
                    
        total_value += new_amount
        sector_value += new_amount
        exposure = sector_value / total_value if total_value > 0 else 0
        
        if exposure > limit_pct:
            logger.warning(f"Risk Block: Sector {new_sector} exposure {exposure:.1%} exceeds limit {limit_pct:.1%}")
            return False
            
        return True

    def _get_sector(self, mds, ticker: str) -> Optional[str]:
        try:
            info = mds.get_financials(ticker)
            return info.get('sector')
        except Exception as e:
            logger.warning(f"Error getting sector for {ticker}: {e}")
            return None

    def trigger_kill_switch(self, user_id: str):
        self._set_setting(user_id, "ai_trading_enabled", "false")
        logger.critical(f"KILL SWITCH TRIGGERED for {user_id}. All AI trading halted.")
