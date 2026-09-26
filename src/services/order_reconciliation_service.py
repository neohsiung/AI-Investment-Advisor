"""
Order Reconciliation & Lifecycle State Machine Service.
掛單生命週期狀態機與成交對賬引擎服務。

Responsible for:
1. Tracking pending orders in the local transaction ledger.
2. Polling broker status (eToro/IBKR) for unconfirmed/pending orders.
3. Performing state transitions (PENDING -> FILLED / CANCELLED / REJECTED).
4. On FILLED: Promoting to entry_category='trade', re-seeding position_lots,
   recording outcome reflections, and broadcasting notifications.
5. Syncing external broker history and refreshing portfolio snapshots.
"""

import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from src.utils.logger import setup_logger
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.repositories.position_lot_repository import AlchemyPositionLotRepository
from src.services.broker_factory import BrokerFactory
from src.domain.broker import IBroker
from src.config.owner import resolve_user_id

logger = setup_logger("OrderReconciliationService")


class OrderReconciliationService:
    """
    Lifecycle manager and reconciliation engine for pending orders and trade settlement.
    掛單生命週期管理與撮合成交對賬引擎。
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        broker: Optional[IBroker] = None,
        tx_repo: Optional[AlchemyTransactionRepository] = None,
        lot_repo: Optional[AlchemyPositionLotRepository] = None,
        notification_service: Any = None,
    ) -> None:
        self.user_id = resolve_user_id(user_id)
        self.broker = broker
        self.tx_repo = tx_repo or AlchemyTransactionRepository()
        self.lot_repo = lot_repo or AlchemyPositionLotRepository(self.tx_repo.engine)
        self.notification_service = notification_service

    def _get_broker(self, user_id: str) -> Optional[IBroker]:
        if self.broker:
            return self.broker
        try:
            return BrokerFactory.get_broker(user_id)
        except Exception as e:
            logger.warning(f"Failed to resolve broker for user {user_id}: {e}")
            return None

    async def _notify(self, title: str, content: str, user_id: str) -> None:
        """Helper to send notifications safely."""
        try:
            if not self.notification_service:
                from src.services.notification_service import NotificationService
                from src.services.settings_service import SettingsService
                settings_svc = SettingsService(user_id=user_id)
                self.notification_service = NotificationService.create_with_settings(
                    settings_service=settings_svc, user_id=user_id
                )
            await self.notification_service.notify_all(
                title=title,
                content=content,
                channels=["telegram", "web"],
                category="trading",
            )
        except Exception as notif_err:
            logger.warning(f"OrderReconciliationService notification skipped: {notif_err}")

    async def reconcile_pending_orders(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Reconcile all pending orders against the broker API.
        向券商對賬所有未確認掛單與成交狀態。

        Returns summary of checks and transitions performed.
        """
        uid = resolve_user_id(user_id or self.user_id)
        if not uid:
            logger.error("OrderReconciliationService: user_id is required for reconciliation.")
            return {
                "status": "error",
                "message": "user_id is required",
                "_fallback_reason": "missing_user_id",
            }

        broker = self._get_broker(uid)
        if not broker:
            logger.warning(f"OrderReconciliationService: No broker configured for user {uid}.")
            return {
                "status": "skipped",
                "message": "No broker configured",
                "_fallback_reason": "no_broker_configured",
            }

        logger.info(f"Starting order reconciliation for user {uid} via {broker.get_name()}...")

        summary = {
            "user_id": uid,
            "broker": broker.get_name(),
            "pending_checked": 0,
            "filled": 0,
            "cancelled": 0,
            "still_pending": 0,
            "errors": [],
        }

        # 1. Fetch pending orders from local DB
        pending_txs = self.tx_repo.get_pending_transactions(uid)
        summary["pending_checked"] = len(pending_txs)

        lots_need_resync = False

        for tx in pending_txs:
            tx_id = tx["id"]
            ticker = tx["ticker"]
            action = tx["action"]
            raw = tx.get("raw_data", {})
            broker_order_id = str(raw.get("broker_order_id", "")).strip()

            if not broker_order_id:
                logger.warning(f"Pending tx {tx_id} for {ticker} has no broker_order_id. Skipping.")
                continue

            try:
                status_res = await broker.get_order_status(broker_order_id)
                broker_status = status_res.get("status", "unknown").lower()

                if broker_status == "filled":
                    # Order executed on exchange!
                    fill_price = float(status_res.get("fill_price") or tx["price"] or 0.0)
                    fill_qty = float(status_res.get("quantity") or tx["quantity"] or 0.0)
                    fees = float(status_res.get("fees") or 0.0)

                    extra_raw = {
                        "filled_at": datetime.now(timezone.utc).isoformat(),
                        "broker_trade_info": status_res.get("raw", {}),
                    }

                    # Promote entry_category to 'trade'
                    self.tx_repo.update_transaction_status(
                        transaction_id=tx_id,
                        new_status="filled",
                        entry_category="trade",
                        price=fill_price,
                        quantity=fill_qty,
                        fees=fees,
                        extra_raw=extra_raw,
                    )
                    summary["filled"] += 1
                    lots_need_resync = True
                    logger.info(f"Order {broker_order_id} ({ticker}) FILLED at ${fill_price:.2f} ({fill_qty} units).")

                    # Record outcome reflection for alpha learning
                    try:
                        from src.services.outcome_reflection_service import OutcomeReflectionService
                        outcome_svc = OutcomeReflectionService(user_id=uid)
                        agent_id = raw.get("strategy_name") or "AutomatedTrading"
                        dec_id = outcome_svc.record_decision(
                            ticker=ticker,
                            agent_name=agent_id,
                            signal=action,
                            price=fill_price,
                            horizon_days=5,
                        )
                        logger.info(f"Recorded post-fill decision outcome {dec_id} for {ticker}")
                    except Exception as outcome_e:
                        logger.warning(f"Failed to record outcome reflection on fill: {outcome_e}")

                    # Notify user of successful execution
                    title = f"🎉 掛單撮合成交 (Order Filled) - {ticker}"
                    content = (
                        f"**標的 (Ticker):** {ticker}\n"
                        f"**動作 (Action):** {action}\n"
                        f"**成交數量 (Units):** {fill_qty:.4f}\n"
                        f"**成交均價 (Fill Price):** ${fill_price:.2f}\n"
                        f"**手續費 (Fees):** ${fees:.2f}\n"
                        f"**券商單號 (Broker ID):** {broker_order_id}"
                    )
                    await self._notify(title, content, uid)

                elif broker_status in ("cancelled", "rejected", "expired"):
                    # Order cancelled or rejected by broker
                    extra_raw = {
                        "cancelled_at": datetime.now(timezone.utc).isoformat(),
                        "cancellation_reason": status_res.get("message", "Cancelled by broker"),
                    }
                    self.tx_repo.update_transaction_status(
                        transaction_id=tx_id,
                        new_status=broker_status,
                        entry_category="sync_adjustment",  # Keep as sync_adjustment so it never counts as a trade
                        extra_raw=extra_raw,
                    )
                    summary["cancelled"] += 1
                    logger.info(f"Order {broker_order_id} ({ticker}) {broker_status.upper()}.")

                    title = f"⚠️ 掛單已失效或取消 (Order {broker_status.capitalize()}) - {ticker}"
                    content = (
                        f"**標的 (Ticker):** {ticker}\n"
                        f"**動作 (Action):** {action}\n"
                        f"**狀態 (Status):** {broker_status}\n"
                        f"**券商單號 (Broker ID):** {broker_order_id}"
                    )
                    await self._notify(title, content, uid)

                elif broker_status == "pending":
                    # Check if pending order has exceeded max TTL (e.g. 72 hours)
                    created_at = tx.get("created_at")
                    is_expired = False
                    if created_at:
                        if isinstance(created_at, str):
                            try:
                                created_at = datetime.fromisoformat(created_at)
                            except Exception:
                                created_at = None
                        if created_at and (datetime.now() - created_at.replace(tzinfo=None) > timedelta(hours=72)):
                            is_expired = True

                    if is_expired:
                        logger.warning(f"Pending order {broker_order_id} ({ticker}) exceeded 72h TTL. Marking expired.")
                        self.tx_repo.update_transaction_status(
                            transaction_id=tx_id,
                            new_status="expired",
                            entry_category="sync_adjustment",
                        )
                        summary["cancelled"] += 1
                    else:
                        summary["still_pending"] += 1

                else:
                    # Unknown status - log warning per Rule 0
                    logger.warning(
                        f"Reconciliation: Order {broker_order_id} ({ticker}) returned status '{broker_status}'. "
                        f"Preserving pending state until definitive confirmation."
                    )
                    summary["still_pending"] += 1

            except Exception as order_err:
                logger.error(f"Error checking status for order {broker_order_id} ({ticker}): {order_err}")
                summary["errors"].append(f"{ticker} ({broker_order_id}): {str(order_err)}")

        # 2. Reseed position_lots if any pending order was filled
        if lots_need_resync:
            try:
                lots_seeded = self.lot_repo.backfill_from_transactions(uid)
                summary["position_lots_seeded"] = lots_seeded
                logger.info(f"Reseeded {lots_seeded} position lots after order execution for {uid}")
            except Exception as lot_err:
                logger.warning(f"Position lots reseed failed after fill: {lot_err}")

        # 3. Pull latest trade history from broker to capture any external/manual trades
        try:
            history_sync = await broker.sync_history(uid)
            summary["history_sync"] = history_sync
        except Exception as sync_err:
            logger.warning(f"Broker history sync failed during reconciliation: {sync_err}")
            summary["errors"].append(f"history_sync: {str(sync_err)}")

        # 4. Refresh daily portfolio snapshot
        try:
            from src.services.analytics_service import update_daily_snapshot
            await update_daily_snapshot(user_id=uid)
        except Exception as snap_err:
            logger.warning(f"Daily snapshot update failed after reconciliation: {snap_err}")

        logger.info(
            f"Order reconciliation complete for {uid}: "
            f"{summary['filled']} filled, {summary['cancelled']} cancelled, "
            f"{summary['still_pending']} still pending."
        )

        return {"status": "success", "summary": summary}
