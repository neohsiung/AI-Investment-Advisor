"""
Order Reconciliation & Lifecycle State Machine Service.
掛單生命週期狀態機與成交對賬引擎服務。

Responsible for:
1. Tracking pending orders in the local transaction ledger.
2. Polling broker status (eToro/IBKR) for unconfirmed/pending orders.
3. Performing state transitions (PENDING -> FILLED / CANCELLED / REJECTED / UNRESOLVED).
4. On FILLED: Promoting to entry_category='trade', re-seeding position_lots,
   recording outcome reflections, releasing in-flight locks, and broadcasting notifications.
5. Ghost Order Reconciliation: Tracking unknown attempts with exponential retry backoff,
   cross-referencing live positions, transitioning unresolved orders, and clearing in-flight locks.
6. Syncing external broker history and refreshing portfolio snapshots.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from src.utils.logger import setup_logger
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.repositories.position_lot_repository import AlchemyPositionLotRepository
from src.services.broker_factory import BrokerFactory
from src.domain.broker import IBroker
from src.services.order_inflight_lock_service import OrderInflightLockService
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
        lock_svc: Optional[OrderInflightLockService] = None,
        notification_service: Any = None,
    ) -> None:
        self.user_id = resolve_user_id(user_id)
        self.broker = broker
        self.tx_repo = tx_repo or AlchemyTransactionRepository()
        self.lot_repo = lot_repo or AlchemyPositionLotRepository(self.tx_repo.engine)
        self.lock_svc = lock_svc or OrderInflightLockService(user_id=self.user_id)
        self.notification_service = notification_service

    def _get_broker(self, user_id: str) -> Optional[IBroker]:
        if self.broker:
            return self.broker
        try:
            return BrokerFactory.get_broker(user_id)
        except Exception as e:
            logger.warning(f"Failed to resolve broker for user {user_id}: {e}")
            return None

    def _get_retry_limit(self, user_id: str) -> int:
        """Fetch max retry limit for unknown order status before resolving."""
        try:
            from src.services.settings_service import SettingsService
            limit = SettingsService(user_id=user_id).get("order_reconciliation_retry_limit")
            return max(1, int(limit)) if limit is not None else 5
        except Exception:
            return 5

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
            "unresolved": 0,
            "still_pending": 0,
            "errors": [],
        }

        # 0. Self-repair any historical zero-price entries in DB
        lots_need_resync = False
        try:
            repaired_count = self.tx_repo.repair_zero_price_transactions(uid)
            if repaired_count > 0:
                lots_need_resync = True
                logger.info(f"Self-repaired {repaired_count} zero-price transactions during reconciliation.")
        except Exception as rep_e:
            logger.debug(f"Zero price repair routine skipped: {rep_e}")

        # 1. Fetch pending orders from local DB
        pending_txs = self.tx_repo.get_pending_transactions(uid)
        summary["pending_checked"] = len(pending_txs)

        retry_limit = self._get_retry_limit(uid)

        # Cache live positions for cross-check if needed
        cached_positions = None

        async def _get_live_positions():
            nonlocal cached_positions
            if cached_positions is None:
                try:
                    cached_positions = await broker.get_positions()
                except Exception as p_err:
                    logger.warning(f"Failed to fetch live positions for reconciliation cross-check: {p_err}")
                    cached_positions = []
            return cached_positions

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

                    # Ensure non-zero price
                    if fill_price <= 0.0:
                        try:
                            from src.services.market_data_service import MarketDataService
                            m_price = MarketDataService().get_latest_price(ticker)
                            if m_price and float(m_price) > 0:
                                fill_price = float(m_price)
                        except Exception:
                            pass
                    if fill_price <= 0.0:
                        fill_price = float(tx.get("price") or 1.0)

                    extra_raw = {
                        "filled_at": datetime.now(timezone.utc).isoformat(),
                        "broker_trade_info": status_res.get("raw", {}),
                        "unknown_reconcile_count": 0,
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

                    # Release ticker in-flight lock
                    await self.lock_svc.release_lock(ticker, user_id=uid)

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
                        "unknown_reconcile_count": 0,
                    }
                    self.tx_repo.update_transaction_status(
                        transaction_id=tx_id,
                        new_status=broker_status,
                        entry_category="sync_adjustment",  # Keep as sync_adjustment so it never counts as a trade
                        extra_raw=extra_raw,
                    )
                    summary["cancelled"] += 1
                    logger.info(f"Order {broker_order_id} ({ticker}) {broker_status.upper()}.")

                    # Release in-flight lock
                    await self.lock_svc.release_lock(ticker, user_id=uid)

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
                        await self.lock_svc.release_lock(ticker, user_id=uid)
                    else:
                        summary["still_pending"] += 1

                else:
                    # Unknown status handling with Ghost Order Reconciliation Guard
                    unknown_count = int(raw.get("unknown_reconcile_count", 0)) + 1
                    logger.warning(
                        f"Reconciliation: Order {broker_order_id} ({ticker}) returned status '{broker_status}' "
                        f"(attempt {unknown_count}/{retry_limit})."
                    )

                    # When reaching retry limit, attempt position cross-check
                    confirmed_via_position = False
                    inferred_price = float(tx.get("price") or 0.0)
                    inferred_qty = float(tx.get("quantity") or 0.0)

                    if unknown_count >= retry_limit:
                        live_pos = await _get_live_positions()
                        pos_match = next((p for p in live_pos if getattr(p, "symbol", "").strip().upper() == ticker.strip().upper()), None)

                        if str(action).upper() == "BUY" and pos_match and float(getattr(pos_match, "quantity", 0) or 0) >= (inferred_qty * 0.95):
                            # BUY confirmed: position exists on broker!
                            confirmed_via_position = True
                            inferred_price = float(getattr(pos_match, "current_price", 0.0) or inferred_price or 1.0)
                            inferred_qty = float(getattr(pos_match, "quantity", 0.0) or inferred_qty)
                            logger.info(f"Cross-Check: Inferred BUY FILLED for {ticker} via live position match ({inferred_qty} units).")
                        elif str(action).upper() == "SELL" and not pos_match:
                            # SELL confirmed: position no longer on broker!
                            confirmed_via_position = True
                            if inferred_price <= 0:
                                inferred_price = 1.0
                            logger.info(f"Cross-Check: Inferred SELL FILLED for {ticker} via closed position.")

                    if confirmed_via_position:
                        extra_raw = {
                            "filled_at": datetime.now(timezone.utc).isoformat(),
                            "reconciled_via": "position_cross_check",
                            "unknown_reconcile_count": unknown_count,
                        }
                        self.tx_repo.update_transaction_status(
                            transaction_id=tx_id,
                            new_status="filled",
                            entry_category="trade",
                            price=inferred_price,
                            quantity=inferred_qty,
                            fees=0.0,
                            extra_raw=extra_raw,
                        )
                        summary["filled"] += 1
                        lots_need_resync = True
                        await self.lock_svc.release_lock(ticker, user_id=uid)

                        title = f"🎉 掛單撮合成交 (持倉交叉核驗確認) - {ticker}"
                        content = (
                            f"**標的 (Ticker):** {ticker}\n"
                            f"**動作 (Action):** {action}\n"
                            f"**成交數量 (Units):** {inferred_qty:.4f}\n"
                            f"**成交均價 (Fill Price):** ${inferred_price:.2f}\n"
                            f"**狀態 (Status):** 已由持倉交叉核驗確認撮合\n"
                            f"**券商單號 (Broker ID):** {broker_order_id}"
                        )
                        await self._notify(title, content, uid)

                    elif unknown_count >= retry_limit:
                        # Exceeded retries and cross-check inconclusive -> mark unresolved & release lock
                        extra_raw = {
                            "unresolved_at": datetime.now(timezone.utc).isoformat(),
                            "unresolved_reason": f"Exceeded {retry_limit} unknown reconciliation attempts",
                            "unknown_reconcile_count": unknown_count,
                        }
                        self.tx_repo.update_transaction_status(
                            transaction_id=tx_id,
                            new_status="unresolved",
                            entry_category="sync_adjustment",
                            extra_raw=extra_raw,
                        )
                        summary["unresolved"] += 1
                        summary["cancelled"] += 1
                        logger.warning(
                            f"🚨 [GhostOrder] Order {broker_order_id} ({ticker}) marked UNRESOLVED after {unknown_count} retries. "
                            f"Releasing in-flight lock to unblock future trading."
                        )
                        await self.lock_svc.release_lock(ticker, user_id=uid)

                        title = f"🚨 [幽靈訂單警報] 掛單多次對賬未知已自動結案釋放 - {ticker}"
                        content = (
                            f"**標的 (Ticker):** {ticker}\n"
                            f"**動作 (Action):** {action}\n"
                            f"**券商單號 (Broker ID):** {broker_order_id}\n"
                            f"**重試次數 (Attempts):** {unknown_count}/{retry_limit}\n"
                            f"**處置結果 (Resolution):** 已標記為 unresolved 並解鎖標的交易，避免帳戶操作阻塞。"
                        )
                        await self._notify(title, content, uid)

                    else:
                        # Still pending within retry budget
                        extra_raw = {
                            "unknown_reconcile_count": unknown_count,
                            "last_unknown_at": datetime.now(timezone.utc).isoformat(),
                        }
                        self.tx_repo.update_transaction_status(
                            transaction_id=tx_id,
                            new_status="pending",
                            extra_raw=extra_raw,
                        )
                        summary["still_pending"] += 1

            except Exception as order_err:
                logger.error(f"Error checking status for order {broker_order_id} ({ticker}): {order_err}")
                summary["errors"].append(f"{ticker} ({broker_order_id}): {str(order_err)}")

        # 2. Reseed position_lots if any pending order was filled or repaired
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
            f"{summary['filled']} filled, {summary['cancelled']} cancelled/unresolved, "
            f"{summary['still_pending']} still pending."
        )

        return {"status": "success", "summary": summary}
