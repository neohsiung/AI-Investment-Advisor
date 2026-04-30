from sqlalchemy import text
import uuid
import json
from datetime import datetime
import pandas as pd
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
# from src.ingestor import TradeIngestor # Removed for Clean Clean Architecture
from src.services.analytics_service import update_daily_snapshot

class TransactionService:
    """
    Service for managing financial transactions and holdings.
    管理財務交易與持倉的服務。
    """
    def __init__(self, db_path: str = None, user_id: str = None, repository: Any = None):
        """
        Initialize the transaction service.
        初始化交易服務。
        """
        self.db_path = db_path
        self.user_id = user_id
        # Use Alchemy Repository for Postgres strictness
        from src.repositories.transaction_repository import AlchemyTransactionRepository
        self.repository = repository or AlchemyTransactionRepository()

    def get_transactions(self, user_id: str = None) -> pd.DataFrame:
        """
        Get all transactions for a user as a DataFrame.
        以 DataFrame 形式獲取使用者的所有交易。
        """
        uid = user_id or self.user_id
        if not uid:
            return pd.DataFrame()
        return self.repository.get_all_by_user_df(uid)

    def get_user_tickers(self, user_id: str, only_active: bool = False) -> List[str]:
        """
        Get unique tickers for a user.
        獲取使用者的唯一交易標的。
        """
        if only_active:
            # Need to cast/check if repository has get_active_tickers
            if hasattr(self.repository, 'get_active_tickers'):
                return self.repository.get_active_tickers(user_id)
            else:
                # Fallback if specific repo doesn't support it
                return self.repository.get_unique_tickers(user_id)
        return self.repository.get_unique_tickers(user_id)
        
    def get_holdings_map(self, user_id: str = None) -> Dict[str, Dict]:
        """
        Returns a map of { ticker: { quantity: float, avg_price: float } }
        """
        uid = user_id or self.user_id
        if not uid: return {}
        
        # v4.2.4: Use get_holdings() instead of summary to get avg_price
        holdings = self.repository.get_holdings(uid)
        res = {}
        for h in holdings:
            res[h['ticker']] = {
                'quantity': float(h['quantity']),
                'avg_price': float(h.get('avg_price', 0))
            }
        return res

    def add_manual_trade(self, ticker: str, date_str: str, action: str, quantity: float, price: float, fees: float) -> Tuple[bool, str]:
        """
        Adds a manual transaction via the repository and updates the daily snapshot.
        透過儲存庫新增手動交易並更新每日快照。
        """
        if not self.user_id:
             return False, "User ID not set."

        try:
            # Use Repository
            self.repository.add(
                user_id=self.user_id,
                ticker=ticker,
                date=date_str,
                action=action,
                quantity=quantity,
                price=price,
                fees=fees
            )

            # Trigger snapshot update
            update_daily_snapshot(db_path=self.db_path, user_id=self.user_id)
            return True, f"已新增交易: {action} {quantity} {ticker} @ {price}"
        except Exception as e:
            return False, f"交易新增失敗: {e}"

    def delete_transaction(self, transaction_id: str) -> Tuple[bool, str]:
        """
        Deletes a transaction by its ID and updates the daily snapshot.
        根據 ID 刪除交易並更新每日快照。
        """
        if not self.user_id:
             return False, "User ID not set."

        try:
            # Use Repository
            self.repository.delete(user_id=self.user_id, transaction_id=transaction_id)

            # Recalculate snapshot
            update_daily_snapshot(db_path=self.db_path, user_id=self.user_id)

            return True, f"Transaction {transaction_id} deleted."
        except Exception as e:
            return False, f"Failed to delete transaction: {e}"

    def get_active_positions(self, user_id: str = None) -> List[Dict]:
        """獲取活躍持倉列表，包含成本價與市場價值 (fallback)"""
        try:
            holdings = self.get_holdings_map(user_id or self.user_id)
            positions = []
            for ticker, data in holdings.items():
                qty = data.get('quantity', 0)
                if qty > 0:
                    avg_price = data.get('avg_price', 0)
                    # market_value 使用 avg_price 作為 fallback (SentinelService 會覆蓋即時價格)
                    market_value = avg_price * qty
                    positions.append({
                        'ticker': ticker,
                        'quantity': qty,
                        'avg_price': avg_price,
                        'current_price': avg_price,  # Fallback
                        'market_value': market_value,
                    })
            return positions
        except Exception as e:
            self._logger.error(f"get_active_positions failed: {e}")
            return []


    def get_cash_balance(self, user_id: str = None) -> float:
        """获取现金余额 (Cash Balance)"""
        try:
            uid = user_id or self.user_id
            # 先检查是否有 CASH 特殊头寸
            positions = self.get_active_positions(uid)
            for pos in positions:
                if pos.get('ticker', '').upper() == 'CASH':
                    return float(pos.get('quantity', 0))
            
            # 从 portfolios 表查询现金余额
            try:
                import psycopg2
                # 如果有 DB 连接属性，使用它
                if hasattr(self, 'db') and self.db:
                    cur = self.db.cursor()
                    cur.execute(
                        "SELECT COALESCE(cash_balance, 0) FROM portfolios WHERE user_id = %s LIMIT 1",
                        [uid]
                    )
                    result = cur.fetchone()
                    cur.close()
                    if result:
                        return float(result[0])
            except:
                pass
            
            # Fallback: 返回 0
            return 0.0
        except Exception as e:
            if hasattr(self, '_logger'):
                self._logger.warning(f"get_cash_balance failed: {e}")
            return 0.0
