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
        
    def get_holdings_map(self, user_id: str = None) -> Dict[str, Dict[str, float]]:
        """
        Get a dictionary of current holdings for the user.
        獲取使用者目前持倉的字典。
        """
        uid = user_id or self.user_id
        if not uid: return {}
        
        # Use existing summary method
        summary = self.repository.get_holdings_summary(uid) # returns [(ticker, qty)]
        
        res = {}
        for t, q in summary:
            res[t] = {'quantity': float(q)}
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
        """获取活跃持仓列表"""
        try:
            holdings = self.get_holdings_map(user_id or self.user_id)
            positions = []
            for ticker, data in holdings.items():
                if data.get('quantity', 0) > 0:
                    positions.append({
                        'ticker': ticker,
                        'quantity': data['quantity'],
                        'avg_price': data.get('avg_price', 0),
                        'current_price': data.get('current_price', 0),
                        'market_value': data.get('market_value', 0)
                    })
            return positions
        except Exception as e:
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
