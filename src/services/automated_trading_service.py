from src.utils.logger import setup_logger
logger = setup_logger("AutomatedTradingService")

import os
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from datetime import datetime
import asyncio
import httpx
from src.repositories.settings_repository import AlchemySettingsRepository
from src.services.interaction_service import InteractionService
from src.services.notification_service import NotificationService
from src.domain.trading import Order, OrderAction, OrderType, OrderSizingMode
from src.services.broker_factory import BrokerFactory
from src.config.owner import resolve_user_id

RESERVED_NON_EQUITY_SYMBOLS = {
    "CASH", "USD", "USDT", "CURRENCY", "RESERVE", "HOLDING", "PORTFOLIO", "INDEX", "MONEY"
}


class _ApprovalSlot:
    """
    A budget limiting how many workers may sit blocked awaiting approval.
    限制同時有多少 worker 卡在等待核准的名額預算。

    `InteractionService.request_approval` polls for up to 300 seconds inside
    the calling Celery task. Production runs 2 worker containers at
    concurrency 2 — four slots total — while `sentinel_tick` fires every
    minute. Four concurrent approvals therefore stall the sentinel entirely
    for five minutes, stop-loss checks included.

    Backed by Redis so the budget spans processes; an in-process counter
    would be as useless here as the instance-dict debounce that let the
    2026-08-10 rebalance cooldown do nothing across workers.

    request_approval 會在呼叫端的 Celery task 內輪詢最多 300 秒，而 production 只
    有 4 個並行槽、sentinel_tick 每分鐘觸發，四筆同時待核准就會讓哨兵（含停損
    檢查）停擺五分鐘。以 Redis 為底讓預算跨行程生效——行程內計數器在此會和
    2026-08-10 那個跨行程失效的 instance-dict 防抖一樣毫無作用。
    """

    # Long enough to outlive a 300s approval wait, short enough that a worker
    # killed mid-wait returns its slot rather than shrinking the budget forever.
    # 長於 300 秒的等待，又短到 worker 中途被砍時名額會歸還而非永久縮減。
    _TTL_SECONDS = 420

    def __init__(self, user_id: str, settings_repo: Any):
        self.user_id = resolve_user_id(user_id)
        self._settings_repo = settings_repo
        self._key = f"approval:slots:{user_id}"
        self._held = False

    def _limit(self) -> int:
        try:
            raw = self._settings_repo.get(self.user_id, "max_pending_approvals")
            return max(1, int(raw)) if raw is not None else 2
        except Exception as e:
            # Say so. A silent fallback here means the operator's configured
            # budget is being ignored while they believe it applies.
            # 必須說出來：靜默退回預設值等於操作者設定的預算被忽略，而他以為生效中。
            logger.warning(f"max_pending_approvals unreadable ({e}); using default of 2")
            return 2

    async def acquire(self) -> bool:
        try:
            from src.infrastructure.cache.redis_client import get_redis

            redis = await get_redis()
            count = await redis.incr(self._key)
            if count == 1:
                await redis.expire(self._key, self._TTL_SECONDS)
            if count > self._limit():
                await redis.decr(self._key)
                return False
            self._held = True
            return True
        except Exception as e:
            # Fail OPEN. Redis being down must not stop the user being asked
            # about a trade — the budget is a fairness guard, not a safety
            # control, and refusing every approval would be a worse outcome
            # than briefly risking worker contention.
            # 採 fail-open：Redis 故障不應讓使用者收不到交易詢問。此預算是公平性
            # 保護而非安全控制，全面拒絕核准比短暫的 worker 競用更糟。
            logger.warning(f"Approval slot budget unavailable ({e}); proceeding without it")
            return True

    async def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            from src.infrastructure.cache.redis_client import get_redis

            redis = await get_redis()
            if await redis.decr(self._key) < 0:
                await redis.set(self._key, 0)
        except Exception as e:
            logger.warning(f"Could not release approval slot ({e}); TTL will reclaim it")


class AutomatedTradingService:
    """
    Automated Trading Service.
    自動化交易服務。
    
    Handles the execution of trades based on AI confidence scores and user-defined thresholds.
    根據 AI 信心分數與使用者定義的閾值處理交易執行。
    """
    
    def __init__(self, settings_repo: Optional[AlchemySettingsRepository] = None, 
                 interaction_service: Optional[InteractionService] = None,
                 notification_service: Optional[NotificationService] = None):
        self.settings_repo = settings_repo or AlchemySettingsRepository()
        self.interaction_service = interaction_service or InteractionService()
        self.notification_service = notification_service

    async def evaluate_and_execute_trade(self, user_id: str, ticker: str, action: str, quantity: float = None,
                                         confidence_score: int = None, rationale: str = None,
                                         target_weight: float = None, current_weight: float = None,
                                         delta_weight: float = None, portfolio_value: float = None,
                                         confidence_breakdown: list = None,
                                         strategy_name: str = None) -> Dict[str, Any]:
        """
        Evaluate and potentially execute a trade based on confidence score.
        評估並可能根據信心分數執行交易。
        
        v7.0: Support weight-based position sizing (fractional shares)
        - If target_weight/current_weight/delta_weight provided: calculate quantity from weights
        - Otherwise: use legacy quantity-based approach
        """
        
        # 0. Non-equity pseudo symbol guard (杜絕偽標的如 CASH/USD 下單)
        sym_upper = (ticker or "").strip().upper()
        if not sym_upper or sym_upper in RESERVED_NON_EQUITY_SYMBOLS:
            logger.info(f"Skipping non-equity pseudo symbol '{ticker}' (liquidity/cash instruction, not trade order)")
            return {"status": "skipped", "reason": f"Non-equity pseudo symbol '{ticker}' is not an executable asset"}

        # v4.2.2: Ensure notification service is correctly configured for this user
        if not self.notification_service:
            from src.services.settings_service import SettingsService
            from src.services.notification_service import NotificationService
            settings_svc = SettingsService(user_id=user_id)
            self.notification_service = NotificationService.create_with_settings(settings_service=settings_svc, user_id=user_id)

        # [NEW v7.0 / v8.3] Weight-based quantity calculation
        # If target_weight is provided, calculate quantity from delta_weight:
        # BUY: quantity is in USD (eToro /market-open-orders/by-amount and downstream cash guards expect USD)
        # SELL: quantity is in shares (eToro /market-close-orders/positions/{id} UnitsToDeduct expects shares)
        # 依權重計算交易量：BUY 端點與後續風控需美元金額；SELL 平倉端點需扣減股數。
        if delta_weight is not None and portfolio_value is not None and quantity is None:
            try:
                broker = BrokerFactory.get_broker(user_id)
                if broker:
                    delta_amount = abs(float(delta_weight) * float(portfolio_value))
                    if str(action).upper() == "BUY":
                        # For BUY orders, keep quantity as the dollar amount
                        quantity = delta_amount
                        logger.info(
                            f"Weight-based BUY calculation: delta_weight={delta_weight:+.4f}, "
                            f"portfolio_value=${portfolio_value:.2f}, amount_usd=${quantity:.2f}"
                        )
                    else:
                        # For SELL orders, calculate required shares from current price
                        current_price = await self._get_current_price(broker, ticker, user_id=user_id)
                        if current_price and current_price > 0:
                            quantity = delta_amount / current_price
                            logger.info(
                                f"Weight-based SELL calculation: delta_weight={delta_weight:+.4f}, "
                                f"portfolio_value=${portfolio_value:.2f}, current_price=${current_price:.2f}, shares={quantity:.4f}"
                            )
                        else:
                            logger.warning(f"Could not get current price for {ticker}, falling back to legacy quantity")
                            if quantity is None:
                                quantity = 1.0  # Default fallback
            except Exception as e:
                logger.warning(f"Weight-based calculation failed: {e}, using quantity parameter")
                if quantity is None:
                    quantity = 1.0  # Default fallback
        
        # Ensure quantity is set
        if quantity is None:
            quantity = 1.0

        # 2026-08-02: rationale defaults to None but is used in `in` substring
        # tests below (excess-cash detection) and interpolated into user-facing
        # notification text. Normalize once here so a caller omitting it cannot
        # raise TypeError: argument of type 'NoneType' is not iterable.
        # 2026-08-02：rationale 預設 None 但下面會做 `in` 子字串比對，先正規化避免 TypeError。
        rationale = rationale or ""

        # 1. Check if trading is enabled
        trading_enabled = self.settings_repo.get(user_id, "ai_trading_enabled")
        if trading_enabled is None:
            enable_etoro = self.settings_repo.get(user_id, "enable_etoro")
            enable_ibkr = self.settings_repo.get(user_id, "enable_ibkr")
            trading_enabled = (
                enable_etoro is True or str(enable_etoro).lower() in ("true", "1") or
                enable_ibkr is True or str(enable_ibkr).lower() in ("true", "1")
            )
            # Default to enabled if no explicit setting present
            if enable_etoro is None and enable_ibkr is None:
                trading_enabled = True

        if str(trading_enabled).lower() not in ("true", "1"):
            logger.warning(f"Trade Execution Blocked: AI Trading is disabled for user {user_id}")
            return {"status": "blocked", "reason": "Trading is disabled in settings"}

        # 1b. P4.2 (2026-07-11): declarative protections — global drawdown
        # halt, per-ticker cooldown after a loss, consecutive-loss lockout.
        # Grounded in real resolved decision_outcomes (P1), not self-graded.
        # 2026-08-02: fails CLOSED for BUY. check() now returns a block reason
        # rather than None on internal error, so this outer catch only ever
        # sees import/constructor failures — which are still a reason to refuse
        # a BUY. SELL stays permitted so a user is never trapped in a position.
        # 2026-08-02：BUY 改為 fail-closed；SELL 維持放行，避免把人鎖在部位裡。
        try:
            from src.services.trading_protections_service import TradingProtectionsService
            block_reason = TradingProtectionsService(user_id=user_id).check(ticker, action)
            if block_reason:
                logger.warning(f"Trade Execution Blocked by protection: {block_reason}")
                return {"status": "blocked", "reason": block_reason}
        except Exception as e:
            if str(action).upper() == "BUY":
                logger.error(f"Trading protections unavailable — blocking BUY: {e}")
                return {
                    "status": "blocked",
                    "reason": f"Protection subsystem unavailable ({type(e).__name__}); BUY blocked for safety",
                }
            logger.warning(f"Trading protections check failed (allowing {action}): {e}")

        # 1c. Strategy validation gate (2026-08-10).
        #
        # Context: this system was configured to trade a live eToro account
        # with auto-execution at >= 7.5/10 while `backtest_runs` held ZERO
        # rows. Nothing had ever been measured against history. The rule
        # driving automated sells was a concentration heuristic ("trim any
        # position over 25%") whose expected return is simply unknown.
        #
        # So: in live mode, a named strategy must have a stored backtest that
        # cleared StrategyValidationService's thresholds. Demo/paper mode is
        # untouched by design — paper trading is how a strategy earns its way
        # to a live allocation, and gating it would prevent the very evidence
        # the gate asks for.
        #
        # SELL is downgraded rather than blocked. Refusing to sell can trap a
        # user in a position, which is its own harm; the rest of this file
        # already takes that stance (see the protections block above). An
        # unvalidated SELL therefore loses its auto-execute privilege and must
        # go through human approval instead.
        #
        # 2026-08-10：本系統原本在 backtest_runs 為 0 筆的情況下，就對實盤帳戶
        # 以 ≥7.5 分自動成交，而驅動自動賣出的只是「超過 25% 就砍倉」的集中度
        # 啟發式，期望報酬未知。因此：實盤模式下，具名策略必須存有通過門檻的
        # 回測紀錄。demo/paper 模式刻意不受限——紙上交易正是策略取得實盤資格的
        # 途徑，限制它等於擋掉關卡所要求的證據。
        # SELL 採降級而非封鎖：拒絕賣出會把使用者困在部位裡（本檔既有立場亦同），
        # 故未驗證的 SELL 只是失去自動執行資格，改走人工核准。
        # 停損（stop_loss）與緊急避險（emergency_exit）屬資本安全控制，豁免於回測閘門。
        is_sell = str(action).upper() == "SELL"
        requires_approval_reason = None
        from src.services.strategy_registry import StrategyRegistry
        is_safety_exit = is_sell and StrategyRegistry.is_safety_control(strategy_name or "")
        if strategy_name and not is_safety_exit:
            try:
                from src.services.broker_factory import effective_trading_mode
                from src.services.strategy_validation_service import StrategyValidationService

                # 2026-08-11: waived while the tradable capital is small
                # enough to be a live test. The $100 run exists to find out
                # whether the loop places sane orders at all — it has never
                # filled one — and requiring a passing backtest first would
                # block the very evidence the run is meant to produce. The
                # waiver keys off effective capital, so raising
                # tradable_capital_usd past small_test_capital_usd re-arms
                # the gate on its own; nobody has to remember to switch it
                # back. $100 is the entire downside of the waiver.
                # 2026-08-11：可交易資本仍屬小額實測時豁免。$100 實測的目的正是
                # 確認此迴圈是否會下出合理委託（它至今從未成交過一筆），若先要求
                # 通過回測，等於擋掉這次實測要產生的證據。豁免以「實際生效資本」
                # 為條件，故調高上限即自動恢復把關，無需記得手動關閉；豁免期間的
                # 全部下檔風險就是 $100。
                waived = False
                try:
                    from src.services.capital_policy import is_small_test_capital

                    broker_nlv = await self._current_nlv(user_id)
                    waived = is_small_test_capital(
                        user_id, broker_nlv, settings_repo=self.settings_repo
                    )
                except Exception as e:
                    # Cannot establish that capital is small -> do not waive.
                    # 無法確認資本規模時不予豁免。
                    logger.warning(f"Small-test waiver check failed ({e}); gate stays armed")
                    waived = False

                if waived:
                    logger.warning(
                        f"Strategy validation WAIVED for '{strategy_name}': tradable capital "
                        f"is within the small-test limit. No backtest is gating this live order."
                    )
                elif effective_trading_mode(user_id) != "demo":
                    validated, detail = StrategyValidationService().is_validated(user_id, strategy_name)
                    if not validated:
                        if str(action).upper() == "BUY":
                            logger.warning(
                                f"Trade Execution Blocked: strategy '{strategy_name}' is not "
                                f"validated for live trading — {detail}"
                            )
                            return {
                                "status": "blocked",
                                "reason": (
                                    f"Strategy '{strategy_name}' is not validated for live "
                                    f"trading: {detail}"
                                ),
                            }
                        requires_approval_reason = (
                            f"strategy '{strategy_name}' is not validated for live trading ({detail})"
                        )
                        logger.warning(
                            f"Auto-execution withheld for {action} {ticker}: {requires_approval_reason}"
                        )
            except Exception as e:
                # Fail closed for BUY, consistent with the protections block.
                # BUY 採 fail-closed，與上方護欄一致。
                if str(action).upper() == "BUY":
                    logger.error(f"Strategy validation unavailable — blocking BUY: {e}")
                    return {
                        "status": "blocked",
                        "reason": f"Strategy validation unavailable ({type(e).__name__}); BUY blocked for safety",
                    }
                requires_approval_reason = f"strategy validation unavailable ({type(e).__name__})"
                logger.warning(f"Strategy validation failed (requiring approval for {action}): {e}")

        # 2. Get the thresholds (upper + lower bound)
        # Normalize thresholds to 0-10 scale: UI saves 0-100 (e.g. 75 -> 7.5, 30 -> 3.0)
        #
        # 2026-08-11: BUY and SELL no longer share the auto-execute bar. The
        # two errors are not symmetric — declining to buy costs upside, while
        # declining to sell can let a loss compound — so a sell clears at a
        # lower score. BUY stays at auto_trade_threshold (7.5);
        # SELL uses auto_trade_threshold_sell (default 6.0).
        # 2026-08-11：買賣不再共用自動執行門檻。兩種錯誤並不對稱——不買只是少賺，
        # 不賣可能讓虧損持續擴大——因此賣出以較低分數即可放行。
        is_sell = str(action).upper() == "SELL"
        threshold_key = "auto_trade_threshold_sell" if is_sell else "auto_trade_threshold"
        default_threshold = 6.0 if is_sell else 7.5

        raw_threshold = self.settings_repo.get(user_id, threshold_key)
        if raw_threshold is not None:
            threshold = float(raw_threshold)
            if threshold > 10:
                threshold = threshold / 10.0
        else:
            threshold = default_threshold

        raw_min_threshold = self.settings_repo.get(user_id, "auto_trade_min_threshold")
        if raw_min_threshold is not None:
            min_threshold = float(raw_min_threshold)
            if min_threshold > 10:
                min_threshold = min_threshold / 10.0
        else:
            min_threshold = 3.0
        
        # ── Normalize confidence to 0-10 scale for consistent comparison ──
        if confidence_score is not None and confidence_score > 10:
            normalized_confidence = confidence_score / 10.0
        else:
            normalized_confidence = float(confidence_score if confidence_score is not None else 0)
        
        # v8.2: Enhanced Excess Cash Detection with multiple trigger patterns
        # 增強現金過高檢測，支援多種觸發模式
        is_excess_cash = (
            "現金比例過高" in rationale or 
            "現金水位過高" in rationale or
            "現金水位明顯過高" in rationale or
            "現金再投資" in rationale or
            "Excess Cash" in rationale or 
            "High Cash" in rationale or
            "cash_ratio >" in rationale  # Quantitative pattern
        )
        # 2026-08-11: scoped to BUY. This lowers the bar so idle cash gets
        # deployed; applying it to a SELL would lower the bar for liquidating
        # a position because there is *too much cash*, which is backwards.
        # Previously the rationale-substring match could hit a sell whose text
        # merely mentioned excess cash.
        # 2026-08-11：限定 BUY。此處是為了讓閒置現金被投入而降低門檻；套用到
        # SELL 等於「因為現金太多所以更容易平倉」，邏輯顛倒。原本的字串比對可能
        # 誤中一筆內文提及現金過高的賣單。
        if is_excess_cash and not is_sell:
            raw_reinvest = self.settings_repo.get(user_id, "auto_reinvest_threshold") or 7
            reinvest_threshold = float(raw_reinvest) / 10.0 if float(raw_reinvest) > 10 else float(raw_reinvest)
            if threshold > reinvest_threshold:
                logger.info(f"Excess Cash Reinvestment: Lowering threshold {threshold} -> {reinvest_threshold} for {ticker}")
                threshold = reinvest_threshold

        logger.info(
            f"evaluating trade for {ticker}. Score: {normalized_confidence:.1f} (raw={confidence_score}), "
            f"Min: {min_threshold:.1f}, Threshold: {threshold:.1f} (ExcessCash={is_excess_cash})"
        )
        
        # 3. Decision Logic (三段式閥值)
        # 3a. Below minimum → skip silently, no notification
        if normalized_confidence < min_threshold:
            logger.info(
                f"Score {normalized_confidence:.1f} < min_threshold {min_threshold:.1f}. "
                f"Skipping silently for {ticker}."
            )
            return {"status": "skipped", "reason": f"Score {normalized_confidence:.1f} below minimum threshold {min_threshold:.1f}"}
        
        # Prepare Order object
        order_action = OrderAction.BUY if action.upper() == "BUY" else OrderAction.SELL
        
        # v6.0: Position Sizing Guard (現金水位與持倉比例守衛)
        # ─────────────────────────────────────────────────
        if order_action == OrderAction.BUY:
            try:
                broker = BrokerFactory.get_broker(user_id)
                if broker:
                    account = await broker.get_account()
                    if account and account.total_equity > 0:
                        # 2026-08-11: size against tradable capital, not the
                        # account's real equity. The account holds ~$1,048 but
                        # this loop has never filled a single order, so it is
                        # capped at $100 until it proves itself. See
                        # src/services/capital_policy.py — the cap only ever
                        # shrinks the figure, never grows it.
                        # 2026-08-11：以「可交易資本」而非帳戶真實權益計算部位。
                        # 帳戶約 $1,048，但此迴圈至今從未成交，故先限縮在 $100。
                        from src.services.capital_policy import tradable_capital

                        nlv = tradable_capital(
                            user_id, account.total_equity, settings_repo=self.settings_repo
                        )
                        # Cash is likewise bounded — deploying $400 of real cash
                        # against a $100 mandate would defeat the cap.
                        # 現金同樣受限，否則以 $100 授權動用 $400 現金即失去意義。
                        cash = min(float(account.available_cash), nlv)

                        # Dynamic settings (Rule #8: no hardcoded thresholds)
                        max_pct = float(self.settings_repo.get(user_id, "max_single_position_pct") or 0.10)
                        min_amount = float(self.settings_repo.get(user_id, "min_trade_amount") or 10.0)

                        max_amount = nlv * max_pct
                        original_qty = quantity

                        # Clamp to available cash
                        if quantity > cash:
                            logger.warning(f"Position Sizing: Clamped ${quantity:.2f} → ${cash:.2f} (available cash)")
                            quantity = cash

                        # Clamp to max position percentage
                        if quantity > max_amount:
                            logger.warning(f"Position Sizing: Clamped ${quantity:.2f} → ${max_amount:.2f} ({max_pct*100:.0f}% of tradable capital ${nlv:.2f})")
                            quantity = max_amount
                        
                        # Check minimum
                        if quantity < min_amount:
                            logger.info(f"Position Sizing: Amount ${quantity:.2f} below minimum ${min_amount:.2f}. Skipping.")
                            return {"status": "skipped", "reason": f"Amount ${quantity:.2f} below minimum (${min_amount:.2f})"}
                        
                        if quantity != original_qty:
                            logger.info(f"Position Sizing: Adjusted {ticker} amount ${original_qty:.2f} → ${quantity:.2f} (NLV: ${nlv:.2f}, Cash: ${cash:.2f})")
                        
                        # Phase 2: Explicit rounding for USD amount
                        quantity = round(quantity, 2)
            except Exception as e:
                # 2026-08-02: fail CLOSED. This block enforces the max-position
                # (% NLV), available-cash and minimum-amount limits. Letting an
                # UNSIZED buy order through to a live broker is the worst
                # outcome in this file, so a sizing failure must block.
                # 2026-08-02：改為 fail-closed。未經 sizing 的買單流到真實 broker 是最糟結果。
                logger.error(f"Position Sizing check failed — blocking BUY: {e}")
                return {
                    "status": "blocked",
                    "reason": f"Position sizing unavailable ({type(e).__name__}); BUY blocked for safety",
                }
        
        # v7.0: SELL Position Sizing Guard (持倉守衛 — 最後防線)
        # ─────────────────────────────────────────────────
        if order_action == OrderAction.SELL:
            try:
                broker = BrokerFactory.get_broker(user_id)
                if broker:
                    positions = await broker.get_positions()  # ← async
                    actual_holding = 0.0
                    for p in positions:
                        p_sym = str(getattr(p, 'symbol', '')).strip().upper()
                        t_sym = ticker.strip().upper()
                        
                        # Handle unresolved ID_xxxx symbols
                        if p_sym.startswith("ID_"):
                            # Check if the broker can resolve it
                            resolved = None
                            if hasattr(broker, '_resolve_id_to_symbol'):
                                resolved = broker._resolve_id_to_symbol(p_sym[3:])
                            
                            if resolved:
                                p_sym = resolved.strip().upper()
                            else:
                                # If it's still ID_xxxx, we can't match it unless we know the ticker's ID
                                # For now, skip and log
                                logger.debug(f"SELL Guard: Skipping unresolved position {p_sym}")
                                continue

                        # Normalize eToro suffixes
                        for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
                            if p_sym.endswith(suffix):
                                p_sym = p_sym[:-len(suffix)]
                        if p_sym == t_sym:
                            actual_holding += getattr(p, 'quantity', 0)
                    
                    original_qty = quantity
                    
                    if actual_holding <= 0:
                        logger.info(f"SELL Guard: No active position for {ticker}. Skipping trade.")
                        return {"status": "skipped", "reason": f"No active position for {ticker}"}
                    
                    if quantity > actual_holding:
                        logger.warning(f"SELL Guard: Clamped {ticker} from {quantity} → {actual_holding} (actual holding)")
                        quantity = actual_holding
                    
                    if quantity != original_qty:
                        logger.info(f"SELL Guard: Adjusted {ticker} qty {original_qty} → {quantity} (holding: {actual_holding})")
                    
                    # Phase 2: Explicit rounding for eToro 0.01 share precision
                    quantity = round(quantity, 2)
            except Exception as e:
                # 2026-08-02: fail CLOSED. This clamp is what keeps a SELL from
                # exceeding the actual holding (i.e. accidentally opening a
                # short). Blocking here does not trap the user — they can retry
                # or sell via the broker directly — whereas an unclamped SELL
                # can create a position that did not exist.
                # 2026-08-02：改為 fail-closed。未鉗制的賣單可能超賣成為做空部位。
                logger.error(f"SELL Position Sizing check failed — blocking SELL: {e}")
                return {
                    "status": "blocked",
                    "reason": f"Sell-quantity clamp unavailable ({type(e).__name__}); SELL blocked for safety",
                }
        
        # Controlled Leverage & Trailing Stop Evaluation (受控槓桿與移動停損評估)
        leverage = 1
        stop_loss_rate = None
        take_profit_rate = None
        is_trailing_stop_loss = False

        if order_action == OrderAction.BUY:
            try:
                from src.services.leverage_policy_service import LeveragePolicyService
                lev_svc = LeveragePolicyService(user_id=user_id, settings_repo=self.settings_repo)
                acc = await broker.get_account() if hasattr(broker, 'get_account') else None
                nlv = getattr(acc, 'total_equity', None) or portfolio_value
                est_price = await self._get_current_price(broker, ticker, user_id=user_id)

                current_vix = None
                try:
                    from src.services.market_data_service import MarketDataService
                    mds = MarketDataService()
                    macro_data = mds.get_macro_shift()
                    indicators = macro_data.get("market_indicators", {})
                    raw_vix = indicators.get("^VIX")
                    if raw_vix is not None:
                        current_vix = float(raw_vix)
                except Exception as vix_e:
                    logger.warning(f"LeveragePolicy: could not fetch real-time VIX ({vix_e}); using None")

                consensus_count = len(confidence_breakdown) if confidence_breakdown else 1
                lev_decision = lev_svc.evaluate_leverage(
                    ticker=ticker,
                    action="BUY",
                    confidence_score=normalized_confidence,
                    current_price=est_price,
                    amount_usd=quantity,
                    portfolio_nlv=nlv,
                    vix=current_vix,
                    confirming_agents_count=consensus_count,
                    strategy_name=strategy_name,
                )
                leverage = lev_decision.eligible_leverage
                stop_loss_rate = lev_decision.stop_loss_rate
                take_profit_rate = lev_decision.take_profit_rate
                is_trailing_stop_loss = lev_decision.is_trailing_stop_loss
                if lev_decision.is_leveraged:
                    logger.info(f"LeveragePolicy: {ticker} approved for X{leverage} leverage ({lev_decision.reason})")
            except Exception as lev_e:
                logger.warning(f"LeveragePolicy check skipped due to error: {lev_e}")

        order = Order(
            symbol=ticker,
            action=order_action,
            quantity=quantity,
            amount_usd=quantity if order_action == OrderAction.BUY else None,
            sizing_mode=OrderSizingMode.AMOUNT if order_action == OrderAction.BUY else OrderSizingMode.SHARES,
            order_type=OrderType.MARKET,
            leverage=leverage,
            stop_loss_rate=stop_loss_rate,
            take_profit_rate=take_profit_rate,
            is_trailing_stop_loss=is_trailing_stop_loss,
            reason=rationale
        )
        
        # 3b. Auto-execute logic (走向全自主通報模式：從要我決策，變成跟我報告)
        auto_exit_enabled = self.settings_repo.get(user_id, "autonomous_exit_enabled")
        if auto_exit_enabled is None:
            auto_exit_enabled = True
        else:
            auto_exit_enabled = str(auto_exit_enabled).lower() in ("true", "1")

        # 2026-09-25: autonomous_reporting_mode (目標從要我決策，變成跟我報告)
        auto_rep_setting = self.settings_repo.get(user_id, "autonomous_reporting_mode")
        autonomous_reporting_mode = str(auto_rep_setting).lower() in ("true", "1")

        # 自主判決置信度優化 (Autonomous Confidence Optimizer)
        optimized_confidence = normalized_confidence
        if normalized_confidence < threshold and (autonomous_reporting_mode or auto_exit_enabled):
            try:
                from src.services.autonomous_reporting_service import AutonomousConfidenceOptimizer
                optimized_confidence, boosts = AutonomousConfidenceOptimizer.optimize_confidence(
                    base_confidence=normalized_confidence,
                    action=action,
                    threshold=threshold,
                    rationale=rationale,
                    confidence_breakdown=confidence_breakdown,
                    strategy_name=strategy_name,
                )
                if optimized_confidence >= threshold:
                    logger.info(
                        f"Autonomous Confidence Optimizer: {ticker} boosted {normalized_confidence:.1f} → "
                        f"{optimized_confidence:.1f} ({', '.join(boosts)}), cleared threshold {threshold:.1f}"
                    )
            except Exception as opt_err:
                logger.warning(f"Confidence optimization check non-blocking failure: {opt_err}")

        effective_confidence = max(normalized_confidence, optimized_confidence)

        should_auto_execute, approval_label = self._determine_auto_execution_policy(
            is_sell=is_sell,
            strategy_name=strategy_name,
            effective_confidence=effective_confidence,
            threshold=threshold,
            auto_exit_enabled=auto_exit_enabled,
            autonomous_reporting_mode=autonomous_reporting_mode,
            requires_approval_reason=requires_approval_reason,
            is_optimized=(optimized_confidence != normalized_confidence),
        )

        if should_auto_execute:
            logger.info(f"Score {effective_confidence} >= {threshold} (or exit/rebalance). Executing automatically ({approval_label}).")
            return await self._execute_trade(
                user_id, order, effective_confidence, rationale, approval_label,
                confidence_breakdown=confidence_breakdown, threshold=threshold,
                strategy_name=strategy_name
            )

        # 3c. Autonomous Reporting Mode: Do not block or harass user with approval requests unless explicitly required by policy
        if autonomous_reporting_mode and not requires_approval_reason:
            skip_reason = f"Score {effective_confidence:.1f} below threshold {threshold:.1f}"
            logger.info(
                f"Autonomous Mode: {order.action.value} {ticker} not auto-executed ({skip_reason}). "
                f"Skipping trade autonomously without interrupting user."
            )
            return {
                "status": "skipped",
                "reason": f"Autonomous evaluation: {skip_reason} (Declined without human interruption)",
            }

        # Legacy 3c: Between min and upper → notify all channels, request approval
        if requires_approval_reason:
            logger.info(
                f"Score {normalized_confidence} would auto-execute, but approval is "
                f"required: {requires_approval_reason}"
            )
        else:
            logger.info(f"Score {normalized_confidence} in [{min_threshold}, {threshold}). Requesting approval.")
        return await self._request_approval_and_execute(
            user_id, order, normalized_confidence, rationale,
            confidence_breakdown=confidence_breakdown,
            threshold=threshold,
            extra_reason=requires_approval_reason,
        )

    @staticmethod
    def _determine_auto_execution_policy(
        is_sell: bool,
        strategy_name: Optional[str],
        effective_confidence: float,
        threshold: float,
        auto_exit_enabled: bool,
        autonomous_reporting_mode: bool,
        requires_approval_reason: Optional[str],
        is_optimized: bool,
    ) -> Tuple[bool, str]:
        """
        Streamlined auto-execution policy gatekeeper.
        統一判定是否符合自動執行標準與對應標籤。
        """
        from src.services.strategy_registry import StrategyRegistry

        if is_sell and strategy_name == "stop_loss":
            return True, "停損自動執行"

        if requires_approval_reason:
            return False, "審批要求阻斷"

        # 安全控制與再平衡出場
        if is_sell and StrategyRegistry.is_safety_control(strategy_name or "") and auto_exit_enabled:
            labels = {
                "take_profit": "停利自動執行",
                "capital_rotation": "換庫自動執行",
                "rebalance_diversification": "再平衡自動執行",
                "concentration_rebalance": "再平衡自動執行",
            }
            return True, labels.get(strategy_name, "安全出場自動執行")

        # 一般賣出且置信度達標
        if is_sell and effective_confidence >= threshold and auto_exit_enabled:
            return True, "出場自動執行" if not is_optimized else "自主執行 (信心優化放行)"

        # 一般買進/賣出且置信度達標
        if effective_confidence >= threshold:
            return True, "自動執行" if not is_optimized else "自主執行 (信心優化放行)"

        # 自主回報模式下的自適應賣出
        if effective_confidence >= threshold and autonomous_reporting_mode and is_sell:
            return True, "自主執行 (策略自適應)"

        return False, "未達自動執行門檻"

    async def _request_approval_and_execute(self, user_id: str, order: Order, confidence_score: int, rationale: str, confidence_breakdown: list = None, threshold: float = None, extra_reason: str = None) -> Dict[str, Any]:
        """Request user approval synchronously via InteractionService."""

        # 2026-08-11: card rewritten. The previous version listed the sub-agent
        # scores but never stated the bar or which input missed it, so the only
        # way to judge a request was to trust the number. render_card computes
        # both — see src/services/decision_card.py.
        # 2026-08-11：改寫卡片。舊版只列各代理人分數，未說明門檻與是哪一項未達標，
        # 使用者只能選擇相信那個數字。render_card 會把兩者算出來。
        from src.services.decision_card import render_card

        is_buy = order.action == OrderAction.BUY
        if is_buy:
            size_line = f"部位：${order.quantity:.2f}"
        else:
            size_line = f"賣出數量：{order.quantity} 股"

        context_lines = []
        if extra_reason:
            context_lines.append("")
            context_lines.append(f"⚠️ {extra_reason}")
        if rationale:
            context_lines.append("")
            context_lines.append(f"依據：{rationale.strip()[:300]}")

        title = f"🛎️ [需要核准] {order.action.value} {order.symbol}"
        content = render_card(
            action=order.action.value,
            ticker=order.symbol,
            score=float(confidence_score),
            threshold=float(threshold) if threshold is not None else 7.5,
            breakdown=confidence_breakdown,
            size_line=size_line,
            context_lines=context_lines,
            auto_executed=False,
            expires_seconds=300,
        )

        # Request approval (Timeout 300 seconds = 5 mins)
        #
        # 2026-08-11: bounded concurrency. `request_approval` polls for up to
        # 300 seconds inside whatever Celery task called it
        # (interaction_service.py). The workers run 2 containers x concurrency
        # 2 = 4 slots, and `sentinel_tick` fires every minute, so four
        # simultaneous approvals stall the entire sentinel for five minutes —
        # including the stop-loss checks it exists to run.
        #
        # A slot budget bounds that: at most `max_pending_approvals` workers
        # can be parked at once, leaving the rest free. Over budget, the trade
        # is recorded rather than silently dropped.
        #
        # Considered and rejected: moving the wait onto a dedicated Celery
        # queue. That requires serializing the Order into a separate task, and
        # if that queue's consumer dies the approvals stop happening with
        # nothing blocked and nothing to notice — a silent black hole. The
        # budget bounds the same damage with no new failure mode.
        #
        # 2026-08-11：限制併發。request_approval 會在呼叫它的 Celery task 內輪詢
        # 最多 300 秒，而 worker 僅 4 個並行槽、sentinel_tick 每分鐘觸發，四筆同時
        # 待核准就會讓整個哨兵停擺五分鐘，連它本來要跑的停損檢查一起停掉。
        # 名額預算把上限鎖住；超額時記錄而非默默丟棄。
        # 已評估並否決「移到專用佇列」：需將 Order 序列化為獨立任務，且該佇列的
        # 消費者一旦停擺，核准會在無人阻塞、無跡象的情況下停止發生——形成無聲黑洞。
        slot = _ApprovalSlot(user_id, self.settings_repo)
        if not await slot.acquire():
            logger.warning(
                f"Approval slots exhausted for user {user_id}; not asking about "
                f"{order.action.value} {order.symbol} (score {confidence_score})"
            )
            self._record_skipped_approval(user_id, order, confidence_score, content)
            return {
                "status": "skipped",
                "reason": (
                    f"Too many approvals already pending; {order.action.value} "
                    f"{order.symbol} was recorded instead of asked"
                ),
            }

        logger.info(f"Requesting approval from user {user_id} for {order.symbol}")

        try:
            # v4.2.3: Handle detailed status results (Approved/Rejected/Expired)
            # 2026-07-14 (B-P2.2): pass ticker via context so a rejection can
            # be attributed to a sector in UserPreferenceService — this was
            # previously only embedded in the free-text `content` string.
            is_approved, status = await self.interaction_service.request_approval(
                user_id=user_id,
                title=title,
                content=content,
                context={"ticker": order.symbol},
                timeout_seconds=300
            )
            
            if is_approved:
                logger.info(f"User {user_id} approved trade for {order.symbol}")
                return await self._execute_trade(user_id, order, confidence_score, rationale, "核准後執行", confidence_breakdown=confidence_breakdown, threshold=threshold)
            else:
                from src.domain.interaction import InteractionStatus
                if status == InteractionStatus.EXPIRED or str(status).upper() in ("EXPIRED", "INTERACTIONSTATUS.EXPIRED"):
                    logger.warning(f"Trade approval for {order.symbol} EXPIRED after timeout. Suppressing notification to avoid spam.")
                    return {"status": "rejected_or_timeout", "reason": f"Trade {status.name if hasattr(status, 'name') else status}"}
                else:
                    logger.info(f"User {user_id} rejected trade for {order.symbol}")
                    notif_title = f"❌ [交易取消] 使用者拒絕 - {order.symbol}"
                    notif_content = f"使用者已拒絕此項交易 (User Rejected)。\n\n**標的:** {order.symbol}\n**方向:** {order.action.value}"

                await self._notify_via_api(
                    user_id=user_id,
                    title=notif_title,
                    content=notif_content,
                    category="approval"
                )
                return {"status": "rejected_or_timeout", "reason": f"Trade {status.name if hasattr(status, 'name') else status}"}
                
        except Exception as e:
            logger.error(f"Approval workflow failed: {e}")
            return {"status": "error", "reason": f"Approval workflow failed: {e}"}
        finally:
            # Must run on every exit path. A leaked slot is permanent (the key
            # has a TTL, but until it expires the budget is smaller), and a
            # budget that only shrinks eventually refuses every approval.
            # 每條退出路徑都必須釋放。洩漏的名額雖有 TTL 但在到期前會縮小預算，
            # 而只減不增的預算最終會拒絕所有核准請求。
            await slot.release()

    def _record_skipped_approval(self, user_id: str, order, confidence_score, card: str) -> None:
        """
        Persist an approval we declined to ask about, so it is not invisible.
        記錄未發出的核准請求，避免它完全不可見。

        Dropping a trade silently because the budget was full is the same
        class of problem as the silent sub-minimum skips: the system decides
        something and the user never learns it happened.
        因名額用盡而默默丟棄交易，與「低於最小單默默略過」屬同一類問題：系統做了
        決定而使用者永遠不會知道。
        """
        try:
            from src.repositories.event_queue_repository import EventQueueRepository

            EventQueueRepository().insert_event(
                user_id=user_id,
                event_type="approval_skipped",
                priority=2,
                content={
                    "ticker": order.symbol,
                    "action": order.action.value,
                    "quantity": order.quantity,
                    "confidence_score": confidence_score,
                    "card": card,
                },
            )
        except Exception as e:
            # Never let bookkeeping break the trading path.
            # 記錄失敗不得影響交易路徑。
            logger.warning(f"Could not record skipped approval for {order.symbol}: {e}")

    async def _current_nlv(self, user_id: str) -> float:
        """
        The account's real net liquidation value, or 0.0 if unavailable.
        帳戶真實淨值；無法取得時回傳 0.0。

        Used only to decide whether the small-test waiver applies. Returning
        0.0 on failure is deliberate: 0 is "small", but the caller wraps this
        in a try/except that refuses to waive when anything goes wrong, so an
        unreachable broker cannot silently disable the gate.
        僅用於判斷是否適用小額實測豁免。失敗時回傳 0.0；呼叫端在例外情況下一律
        不豁免，因此券商不可用時不會默默關閉把關。
        """
        broker = BrokerFactory.get_broker(user_id)
        if not broker:
            return 0.0
        account = await broker.get_account()
        return float(getattr(account, "total_equity", 0.0) or 0.0)

    async def _execute_trade(
        self,
        user_id: str,
        order: Order,
        confidence_score: int,
        rationale: str,
        approval_type: str,
        confidence_breakdown: list = None,
        threshold: float = None,
        strategy_name: str = None,
    ) -> Dict[str, Any]:
        """Execute the trade via the BrokerFactory."""
        
        broker = BrokerFactory.get_broker(user_id)
        if not broker:
            msg = "Broker validation failed: No preferred broker configured."
            logger.error(msg)
            return {"status": "failed", "reason": msg}
            
        logger.info(f"Executing {order.action.value} {order.symbol} via {broker.get_name()}")
        
        try:
            # Order execution is synchronous in current design
            result = await broker.execute_order(order)  # ← async
            
            # v6.0: Post-Trade Sync (交易後紀錄同步)
            if result.get("status") not in ["failed", "error"] and not result.get("error"):
                try:
                    await broker.sync_history(user_id)  # ← async
                    logger.info("Post-trade sync completed.")
                except Exception as sync_e:
                    logger.warning(f"Post-trade sync failed (non-blocking): {sync_e}")

                # v8.0: Record decision outcome for alpha reflection & rule learning
                try:
                    from src.services.outcome_reflection_service import OutcomeReflectionService
                    execution_price = order.price
                    if not execution_price or execution_price <= 0:
                        execution_price = await self._get_current_price(broker, order.symbol, user_id=user_id)
                    
                    if execution_price and execution_price > 0:
                        outcome_svc = OutcomeReflectionService(user_id=user_id)
                        agent_identifier = strategy_name or "AutomatedTrading"
                        dec_id = outcome_svc.record_decision(
                            ticker=order.symbol,
                            agent_name=agent_identifier,
                            signal=order.action.value,
                            price=execution_price,
                            horizon_days=5,
                        )
                        logger.info(f"Recorded decision outcome {dec_id} for {order.symbol} at ${execution_price:.2f}")

                        # Trigger rule citation if active rules exist
                        try:
                            from src.repositories.memory_repository import AgentState
                            from src.services.rule_lifecycle_service import RuleLifecycleService
                            active_rules = AgentState().get_active_rules(agent_identifier, user_id=user_id)
                            if active_rules and dec_id:
                                rule_svc = RuleLifecycleService(user_id=user_id)
                                await rule_svc.judge_and_cite(
                                    agent_identifier, dec_id, rationale or f"Trade executed for {order.symbol}", active_rules
                                )
                        except Exception as cite_err:
                            logger.warning(f"Rule citation for trade {dec_id} skipped: {cite_err}")
                    else:
                        logger.warning(
                            f"Decision outcome for {order.symbol} skipped: price unavailable "
                            f"(order.price={order.price}, fetched={execution_price})"
                        )
                except Exception as outcome_err:
                    logger.warning(f"Failed to record decision outcome for trade (non-blocking): {outcome_err}")
            
            # Send Notification: Three-Pillar Autonomous Post-Action Report
            # (一、行動  二、行動後的狀況影響  三、交易策略改變的行動)
            failed = result.get("status") in ["failed", "error"]
            headline = (
                f"⚠️ 執行失敗：{order.action.value} {order.symbol}" if failed
                else f"✅ {approval_type}：{order.action.value} {order.symbol}"
            )

            title = f"✅ 交易執行成功 (Trade Executed) - {order.symbol}"
            if failed:
                title = f"⚠️ 交易執行失敗 (Trade Failed) - {order.symbol}"

            try:
                from src.services.autonomous_reporting_service import AutonomousReportingService
                reporting_svc = AutonomousReportingService(broker=broker, notification_service=self.notification_service)
                report = await reporting_svc.generate_report(
                    user_id=user_id,
                    order=order,
                    result=result,
                    confidence_score=float(confidence_score),
                    threshold=float(threshold) if threshold is not None else 7.5,
                    rationale=rationale,
                    approval_type=approval_type,
                    confidence_breakdown=confidence_breakdown,
                    strategy_name=strategy_name,
                )
                title = report["title"]
                content = report["content"]
            except Exception as rep_err:
                logger.warning(f"Autonomous report generation failed ({rep_err}), falling back to decision card")
                from src.services.decision_card import render_card

                is_buy = order.action == OrderAction.BUY
                size_line = (
                    f"部位：${order.quantity:.2f}" if is_buy
                    else f"賣出數量：{order.quantity} 股"
                )
                content = render_card(
                    action=order.action.value,
                    ticker=order.symbol,
                    score=float(confidence_score),
                    threshold=float(threshold) if threshold is not None else 7.5,
                    breakdown=confidence_breakdown,
                    size_line=size_line,
                    context_lines=[
                        "",
                        f"券商：{broker.get_name()}　執行方式：{approval_type}",
                        f"依據：{(rationale or '').strip()[:300]}",
                        "",
                        f"結果：{result}",
                    ],
                    auto_executed=True,
                    headline=headline,
                )

            await self._notify_via_api(
                user_id=user_id, 
                title=title, 
                content=content, 
                category="trading"
            )
            
            return result
        except Exception as e:
             logger.error(f"Trade execution failed: {e}")
             return {"status": "error", "reason": str(e)}

    async def _get_current_price(self, broker, ticker: str, user_id: str = None) -> Optional[float]:
        """Get current price for a ticker from broker, positions, or MarketDataService."""
        try:
            # 1. Try broker quote
            if hasattr(broker, 'get_quote'):
                quote = await broker.get_quote(ticker)
                if quote and 'price' in quote and float(quote['price']) > 0:
                    return float(quote['price'])
            
            # 2. Try positions from broker
            if hasattr(broker, 'get_positions'):
                try:
                    positions = await broker.get_positions()
                    for pos in positions:
                        if getattr(pos, 'symbol', None) == ticker and getattr(pos, 'current_price', 0) > 0:
                            return float(pos.current_price)
                except Exception as pos_e:
                    logger.debug(f"Position price lookup skipped: {pos_e}")

            # 3. Fallback: MarketDataService (Polygon -> Tiingo -> FMP -> FinancialData -> YFinance)
            try:
                from src.services.market_data_service import MarketDataService
                effective_uid = user_id or getattr(broker, 'user_id', None)
                mds = MarketDataService(user_id=effective_uid)
                prices = await mds.get_current_prices([ticker])
                if prices.get(ticker) and prices[ticker] > 0:
                    return float(prices[ticker])
            except Exception as mds_e:
                logger.warning(f"MarketDataService failed for price of {ticker}: {mds_e}")

            logger.warning(f"Could not retrieve price for {ticker} from broker or market data")
            return None
        except Exception as e:
            logger.warning(f"Error getting price for {ticker}: {e}")
            return None


    async def _notify_via_api(
        self, user_id: str, title: str, content: str, category: str = "approval"
    ) -> None:
        """
        Dispatch notification via direct NotificationService.
        透過直接 NotificationService 發送通知，繞過已失效的通知微服務。
        """
        try:
            if not self.notification_service:
                from src.services.settings_service import SettingsService
                from src.services.notification_service import NotificationService
                settings_svc = SettingsService(user_id=user_id)
                self.notification_service = NotificationService.create_with_settings(
                    settings_service=settings_svc, user_id=user_id
                )
            
            # [T2] Get user's preferred channels (no hardcoding §5.2)
            from src.services.notification_settings_manager import NotificationSettingsManager
            from src.repositories.settings_repository import AlchemySettingsRepository
            nsm = NotificationSettingsManager(
                settings_repo=AlchemySettingsRepository(), 
                user_id=user_id
            )
            user_channels = nsm.get_active_notification_channels()
            if not user_channels:
                user_channels = ["web", "telegram"] # Fallback

            await self.notification_service.notify_all(
                title=title,
                content=content,
                user_id=user_id,
                channels=user_channels,
                category=category
            )
            logger.info(f"Trade notification dispatched via direct NotificationService for {user_id}")
        except Exception as e:
            logger.error(f"Failed to dispatch trade notification: {e}")

    async def process_council_decision(self, user_id: str, decision_text: str) -> List[Dict[str, Any]]:
        """
        Extract trade recommendations from Council decisions and execute them based on confidence.
        從評議會決策中提取交易建議，並根據信心分數執行。
        """
        from src.agents.skills.skill_loader import SkillLoader
        import json
        
        logger.info(f"AutomatedTradingService: Extracting actions from Council decision for user {user_id}")
        loader = SkillLoader(user_id=user_id)
        
        # Skillified: Use extract_actions skill instead of dedicated agent
        trades_json = await loader.run_skill("extract_actions", user_id=user_id, decision_text=decision_text)
        trades = json.loads(trades_json)

        if not trades:
            logger.info("AutomatedTradingService: No actionable trades found in Council decision.")
            return []
            
        results = []
        for trade in trades:
            ticker = trade.get("ticker")
            action = trade.get("action")
            confidence = int(trade.get("confidence", 5))
            reason = trade.get("reason", "Council Recommendation")
            
            # v7.0: Support both legacy (quantity) and new (weight-based) formats
            quantity = None
            target_weight = None
            current_weight = None
            delta_weight = None
            portfolio_value = None
            
            # Try weight-based format first
            if "target_weight" in trade and "delta_weight" in trade:
                target_weight = float(trade.get("target_weight"))
                current_weight = float(trade.get("current_weight", 0))
                delta_weight = float(trade.get("delta_weight"))
                portfolio_value = float(trade.get("portfolio_value", 0))
                logger.info(f"AutomatedTradingService: Extracted weight-based trade -> {action} {ticker} (target_weight={target_weight}%, delta={delta_weight:+.2%}, Confidence: {confidence})")
            else:
                # Legacy format: use quantity
                quantity = float(trade.get("quantity", 1.0))
                logger.info(f"AutomatedTradingService: Extracted legacy trade -> {action} {quantity} {ticker} (Confidence: {confidence})")
            
            if ticker and action:
                res = await self.evaluate_and_execute_trade(
                    user_id=user_id, 
                    ticker=ticker, 
                    action=action, 
                    quantity=quantity,
                    confidence_score=confidence, 
                    rationale=reason,
                    target_weight=target_weight,
                    current_weight=current_weight,
                    delta_weight=delta_weight,
                    portfolio_value=portfolio_value
                )
                results.append(res)
            else:
                logger.warning(f"AutomatedTradingService: Missing required fields in extracted trade: {trade}")
                
        return results
