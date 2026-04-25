
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
import logging
from src.domain.trading import Position, Account
from src.services.broker_factory import BrokerFactory
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.api.v1.exceptions import BrokerNotConfiguredError, BrokerDependencyError

logger = logging.getLogger(__name__)

class PortfolioAggregatorService:
    """
    Service for aggregating portfolio data from multiple broker sources into a unified view.
    投資組合整合服務：將多個券商來源的投資組合數據整合為統一視圖。
    """
    def __init__(self, user_id: str) -> None:
        """
        Initialize the portfolio aggregator service.
        初始化投資組合整合服務。
        """
        self.user_id = user_id
        # In future, we might want to check which brokers are actually enabled in settings
        self.brokers = BrokerFactory.get_enabled_brokers(user_id)

    async def get_aggregated_portfolio(self) -> Dict[str, Any]:
        """
        Fetch and merge positions and account summaries from all enabled brokers.
        獲取並合併所有已啟用券商的部位與帳戶摘要。
        
        Returns:
            Dict[str, Any]: Aggregated portfolio data including equity, cash, and positions.
        """
        aggregated_positions = {}
        total_equity = 0.0
        total_cash = 0.0
        
        accounts_by_broker = {}

        warnings = []
        for broker_name, broker in self.brokers.items():
            try:
                # 1. Account Summary
                account = await broker.get_account()
                if account:
                    total_equity += account.total_equity
                    total_cash += account.available_cash
                    accounts_by_broker[broker_name] = account
                
                # 2. Positions
                positions = await broker.get_positions()
                for pos in positions:
                    if pos.symbol in aggregated_positions:
                        # Merge logic
                        existing = aggregated_positions[pos.symbol]
                        
                        # Weighted Average Price
                        total_qty = existing.quantity + pos.quantity
                        if total_qty > 0:
                            avg_price = (existing.open_price * existing.quantity + pos.open_price * pos.quantity) / total_qty
                        else:
                            avg_price = 0
                        
                        existing.quantity = total_qty
                        existing.open_price = avg_price
                        existing.market_value += pos.market_value
                        existing.unrealized_pnl += pos.unrealized_pnl
                        # Current price should be similar, take latest
                        existing.current_price = pos.current_price 
                        existing.leverage = pos.leverage
                        
                    else:
                        # New Entry (Clone to avoid mutating original if ref shared)
                        aggregated_positions[pos.symbol] = Position(
                            symbol=pos.symbol,
                            quantity=pos.quantity,
                            open_price=pos.open_price,
                            current_price=pos.current_price,
                            market_value=pos.market_value,
                            unrealized_pnl=pos.unrealized_pnl,
                            leverage=pos.leverage
                        )
            except BrokerNotConfiguredError as e:
                logger.warning(f"Broker {broker_name} not configured: {e}")
                warnings.append({
                    "broker": broker_name,
                    "code": "BROKER_NOT_CONFIGURED",
                    "message": str(e)
                })
            except BrokerDependencyError as e:
                logger.error(f"Broker {broker_name} dependency error: {e}")
                warnings.append({
                    "broker": broker_name,
                    "code": "BROKER_DEPENDENCY_ERROR",
                    "message": str(e)
                })
            except Exception as e:
                logger.error(f"Error aggregating broker {broker_name}: {e}")
                warnings.append({
                    "broker": broker_name,
                    "code": "UNKNOWN_ERROR",
                    "message": f"An unexpected error occurred: {str(e)}"
                })

        return {
            "total_equity": total_equity,
            "total_cash": total_cash,
            "positions": list(aggregated_positions.values()),
            "broker_breakdown": accounts_by_broker,
            "warnings": warnings,
            "currency": "USD"
        }
