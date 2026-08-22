from sqlalchemy import text
import uuid
import json
from datetime import datetime
import pandas as pd
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
# from src.ingestor import TradeIngestor # Removed for Clean Clean Architecture
from src.services.analytics_service import update_daily_snapshot
from src.utils.logger import setup_logger

logger = setup_logger("TransactionService")

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
        self.logger = logger

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
            logger.error(f"Error deleting transaction: {e}", exc_info=True)
            return False, "交易刪除失敗，該交易可能不存在或權限不足。"

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
            self.logger.error(f"get_active_positions failed: {e}")
            return []


    def get_cash_balance(self, user_id: str = None) -> float:
        """获取现金余额 (Cash Balance)"""
        try:
            uid = user_id or self.user_id
            if not uid:
                return 0.0
            return self.repository.get_cash_balance(uid)
        except Exception as e:
            self.logger.warning(f"get_cash_balance failed: {e}")
            return 0.0

    async def sync_broker_positions(self, user_id: str = None) -> Dict[str, Any]:
        """
        Synchronize local transactions with live broker positions and cash.
        將本地交易與券商即時持倉及現金進行同步。
        """
        uid = user_id or self.user_id
        if not uid:
            return {"status": "error", "message": "No user_id provided"}

        self.logger.info(f"Starting broker sync for user {uid}...")
        
        try:
            from src.services.portfolio_aggregator_service import PortfolioAggregatorService
            aggregator = PortfolioAggregatorService(user_id=uid)
            
            # Fetch unified data
            data = await aggregator.get_aggregated_portfolio()
            
            summary = {
                "accounts_processed": 0,
                "adjustments_made": 0,
                "errors": data.get("warnings", [])
            }

            # Sync individual brokers
            for broker_name, account in data.get("broker_breakdown", {}).items():
                self.logger.info(f"Syncing broker {broker_name}: Cash={account.available_cash}")
                
                # 1. Reconcile Cash for this broker/account
                self.repository.reconcile_cash_balance(uid, account.available_cash, broker_name)
                
                # 2. Reconcile Positions
                # We need the positions for this specific broker. 
                # Since get_aggregated_portfolio merges them, we'll fetch them again or 
                # we could optimize by having the aggregator return positions per broker.
                # For now, fetching again from the broker instance is safe.
                broker_instance = aggregator.brokers.get(broker_name)
                if broker_instance:
                    live_positions_raw = await broker_instance.get_positions()
                    live_positions = [
                        {
                            "ticker": p.symbol,
                            "quantity": p.quantity,
                            "current_price": p.current_price,
                            "leverage": p.leverage
                        } for p in live_positions_raw
                    ]
                    self.repository.reconcile_positions(uid, live_positions, broker_name)
                    # 3. Save live positions snapshot to positions table
                    self.repository.save_positions(uid, live_positions, broker_name)
                
                summary["accounts_processed"] += 1

            # 3. Seed position_lots from the reconciled transaction history.
            #
            # 2026-08-10: position_lots was empty in production (0 rows) even
            # though this task had run 4,059 times. Nothing on this path ever
            # populated it — the only writers were etoro_service.sync_history()
            # and transaction_repository._sync_position_lots, neither of which
            # sync_broker_positions calls. That mattered well beyond reporting:
            # TradingProtectionsService's three BUY guards (max drawdown,
            # per-ticker cooldown, consecutive-loss lockout) all return None
            # when they see fewer than three rows of history, so an empty
            # ledger meant every guard silently passed. The protections looked
            # active and enforced nothing.
            #
            # backfill_from_transactions() is idempotent — it deletes this
            # user's lots and replays the full FIFO history — so running it per
            # sync is safe. It is O(N) in transactions each time; at the
            # current scale (tens of rows) that is negligible, but it is the
            # thing to revisit first if this task ever gets slow.
            #
            # 2026-08-10：position_lots 在 production 為 0 筆，即使此任務已執行
            # 4059 次——此路徑從未寫入該表。影響不只報表：TradingProtectionsService
            # 的三道 BUY 護欄在歷史少於三筆時一律回傳 None，空帳本等於所有護欄
            # 靜默放行，看似啟用實則毫無作用。backfill 具冪等性，可每次同步執行。
            try:
                from src.repositories.position_lot_repository import AlchemyPositionLotRepository

                lot_repo = AlchemyPositionLotRepository(self.repository.engine)
                lots_created = lot_repo.backfill_from_transactions(uid)
                summary["position_lots_seeded"] = lots_created
            except Exception as e:
                # Non-fatal: reconciliation already succeeded and is the point
                # of this task. Surfaced at warning (not debug) so a silently
                # empty ledger cannot hide again.
                # 非致命：對帳已完成。以 warning 顯示，避免空帳本再次無聲無息。
                self.logger.warning(f"position_lots backfill failed for user {uid}: {e}")
                summary["errors"].append(f"position_lots backfill failed: {e}")

            # Update daily snapshot to reflect changes
            await update_daily_snapshot(uid)

            return {"status": "success", "summary": summary}
            
        except Exception as e:
            self.logger.error(f"Broker sync failed for user {uid}: {e}")
            return {"status": "error", "message": str(e)}
