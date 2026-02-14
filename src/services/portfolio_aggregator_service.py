
from typing import Dict, List, Any
import logging
from src.domain.trading import Position, Account
from src.services.broker_factory import BrokerFactory
from src.repositories.transaction_repository import SqliteTransactionRepository

logger = logging.getLogger(__name__)

class PortfolioAggregatorService:
    """
    Aggregates data from multiple brokers into a unified view.
    """
    def __init__(self, user_id: str):
        self.user_id = user_id
        # In future, we might want to check which brokers are actually enabled in settings
        self.brokers = BrokerFactory.get_enabled_brokers(user_id)

    def get_aggregated_portfolio(self) -> Dict[str, Any]:
        """
        Fetch positions and account summaries from all brokers.
        Merge them into a single view.
        """
        aggregated_positions = {}
        total_equity = 0.0
        total_cash = 0.0
        
        accounts_by_broker = {}

        for broker_name, broker in self.brokers.items():
            try:
                # 1. Account Summary
                account = broker.get_account()
                if account:
                    total_equity += account.total_equity
                    total_cash += account.available_cash
                    accounts_by_broker[broker_name] = account
                
                # 2. Positions
                positions = broker.get_positions()
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
            except Exception as e:
                logger.error(f"Error aggregating broker {broker_name}: {e}")

        return {
            "total_equity": total_equity,
            "total_cash": total_cash,
            "positions": list(aggregated_positions.values()),
            "broker_breakdown": accounts_by_broker,
            "currency": "USD"
        }
