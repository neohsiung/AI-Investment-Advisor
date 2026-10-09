"""
Slippage Guard Service
======================
防滑點與買賣價差熔斷守衛 (Anti-Slippage & Bid-Ask Spread Circuit Breaker)

職責：
1. 開盤極端波動率防線 (Market Open Volatility Guard)：
   檢測美股常規開盤前 N 分鐘（預設 5 分鐘，09:30-09:35 EST）。開盤競價階段券商撮合價差擴大、
   流動性不穩，暫緩市價下單以避免撮合在極端高點。
2. 即時買賣價差熔斷 (Bid-Ask Spread Circuit Breaker)：
   即時度量標的 Bid-Ask Spread。若價差超過閾值（預設 0.15% = 15 bps），觸發熔斷暫緩下單或
   改為自適應限價單。
3. 自適應限價保護 (Adaptive Limit Price Protection)：
   針對碎股與金額型委託，依據即時 Bid/Ask/Mid 動態精算安全成交價上限，封頂滑點吃損。
4. 成交滑點事後稽核 (Post-Trade Realized Slippage Audit)：
   比對成交回報價與預期市價，若不利滑點超過閾值（>0.2%），寫入審計隊列並示警。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
import pytz

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("SlippageGuardService")


@dataclass
class SlippageGuardDecision:
    """防滑點守衛決策結果"""
    passed: bool
    reason: str
    circuit_breaker_triggered: bool = False
    is_opening_window: bool = False
    spread_pct: Optional[float] = None
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    mid_price: Optional[float] = None
    last_price: Optional[float] = None
    adaptive_limit_price: Optional[float] = None
    recommended_action: str = "PROCEED"  # "PROCEED", "DEFER", "REJECT", "LIMIT_ORDER"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "circuit_breaker_triggered": self.circuit_breaker_triggered,
            "is_opening_window": self.is_opening_window,
            "spread_pct": round(self.spread_pct, 5) if self.spread_pct is not None else None,
            "bid_price": round(self.bid_price, 4) if self.bid_price is not None else None,
            "ask_price": round(self.ask_price, 4) if self.ask_price is not None else None,
            "mid_price": round(self.mid_price, 4) if self.mid_price is not None else None,
            "last_price": round(self.last_price, 4) if self.last_price is not None else None,
            "adaptive_limit_price": round(self.adaptive_limit_price, 4) if self.adaptive_limit_price is not None else None,
            "recommended_action": self.recommended_action,
        }


class SlippageGuardService:
    """防滑點與價差熔斷服務"""

    DEFAULT_MAX_SPREAD_PCT = 0.0015       # 0.15% (15 bps) 價差上限門檻
    DEFAULT_OPEN_DELAY_MINUTES = 5         # 開盤後緩衝 5 分鐘 (09:30 - 09:35 EST)
    DEFAULT_SLIPPAGE_WARNING_PCT = 0.0020  # 成交滑點預警門檻 0.20% (20 bps)

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        market_data_service: Optional[Any] = None,
        market_clock: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        from src.services.settings_service import SettingsService
        self.settings_service = settings_service or SettingsService(user_id=self.user_id)
        self.market_data_service = market_data_service
        if market_clock is not None:
            self.market_clock = market_clock
        else:
            try:
                from src.utils.market_clock import MarketClock
                self.market_clock = MarketClock()
            except Exception:
                self.market_clock = None
        self._nyse_tz = pytz.timezone("US/Eastern")

    def _get_setting_bool(self, key: str, default: bool = True) -> bool:
        val = self.settings_service.get_setting(key, default)
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1")

    def _get_setting_float(self, key: str, default: float) -> float:
        val = self.settings_service.get_setting(key, default)
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def _get_setting_int(self, key: str, default: int) -> int:
        val = self.settings_service.get_setting(key, default)
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def is_opening_auction_window(
        self,
        ny_now: Optional[datetime] = None,
        delay_minutes: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        檢測當前時間是否處於開盤極端波動與撮合價差擴大窗口 (09:30 - 09:35 EST)。
        """
        delay = delay_minutes if delay_minutes is not None else self._get_setting_int(
            "market_open_delay_minutes", self.DEFAULT_OPEN_DELAY_MINUTES
        )
        if delay <= 0:
            return False, "開盤緩衝防線已停用"

        now = ny_now or datetime.now(self._nyse_tz)
        if now.tzinfo is None:
            now = self._nyse_tz.localize(now)
        else:
            now = now.astimezone(self._nyse_tz)

        # 僅平日週一至週五 (0=Mon, 4=Fri)
        if now.weekday() > 4:
            return False, "非美股常規交易日 (週末)"

        open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
        delay_cutoff = open_time + timedelta(minutes=delay)

        if open_time <= now < delay_cutoff:
            elapsed_sec = int((now - open_time).total_seconds())
            remaining_sec = int((delay_cutoff - now).total_seconds())
            msg = (
                f"美股開盤前 {delay} 分鐘極端波動保護窗口（當前 09:{now.minute:02d}:{now.second:02d} EST，"
                f"開盤已過 {elapsed_sec}s，尚餘 {remaining_sec}s 解除）。"
                f"撮合價差極寬，暫緩市價下單以避免極端滑點吃損。"
            )
            return True, msg

        return False, "常規市場時段或開盤緩衝期已過"

    async def get_ticker_quote(self, ticker: str) -> Dict[str, Any]:
        """
        獲取標的即時報價，包括 Bid、Ask、Last 與 Mid。
        """
        clean_ticker = ticker.strip().upper()
        for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
            if clean_ticker.endswith(suffix):
                clean_ticker = clean_ticker[:-len(suffix)]

        # 1. 嘗試透過 MarketDataService
        if self.market_data_service is not None:
            if hasattr(self.market_data_service, "get_quote"):
                try:
                    q = await self.market_data_service.get_quote(clean_ticker)
                    if q and (q.get("bid") or q.get("last") or q.get("price")):
                        return q
                except Exception as e:
                    logger.debug(f"MarketDataService.get_quote failed for {clean_ticker}: {e}")

        # 2. 嘗試透過 Polygon 快照提取即時買賣價差
        quote_data = await self._fetch_polygon_quote(clean_ticker)
        if quote_data:
            return quote_data

        # 3. 嘗試透過 Finnhub
        finnhub_quote = await self._fetch_finnhub_quote(clean_ticker)
        if finnhub_quote:
            return finnhub_quote

        # 4. Fallback 透過 MarketDataService.get_current_prices 取得最新市價
        last_price = None
        if self.market_data_service is not None and hasattr(self.market_data_service, "get_current_prices"):
            try:
                prices = await self.market_data_service.get_current_prices([clean_ticker])
                last_price = prices.get(clean_ticker)
            except Exception as e:
                logger.debug(f"Fallback get_current_prices failed for {clean_ticker}: {e}")

        return {
            "ticker": clean_ticker,
            "bid": None,
            "ask": None,
            "last": last_price,
            "mid": last_price,
            "spread": None,
            "spread_pct": None,
            "source": "fallback_last_price",
        }

    async def _fetch_polygon_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        """從 Polygon v2 snapshot 抓取 bid, ask, lastTrade"""
        try:
            poly_key = self.settings_service.get_setting("source_polygon_api_key")
            if not poly_key:
                return None

            import httpx
            url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
            params = {"apiKey": poly_key}
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    t_data = data.get("ticker", {})
                    last_quote = t_data.get("lastQuote", {}) or {}
                    last_trade = t_data.get("lastTrade", {}) or {}
                    day = t_data.get("day", {}) or {}
                    min_bar = t_data.get("min", {}) or {}

                    bid = float(last_quote.get("p", 0.0) or 0.0)
                    ask = float(last_quote.get("P", 0.0) or 0.0)
                    last = float(
                        last_trade.get("p", 0.0)
                        or day.get("c", 0.0)
                        or min_bar.get("c", 0.0)
                        or 0.0
                    )

                    if bid > 0 and ask > 0 and ask >= bid:
                        mid = (bid + ask) / 2.0
                        spread = ask - bid
                        spread_pct = spread / mid if mid > 0 else 0.0
                        return {
                            "ticker": ticker,
                            "bid": bid,
                            "ask": ask,
                            "last": last if last > 0 else mid,
                            "mid": mid,
                            "spread": spread,
                            "spread_pct": spread_pct,
                            "source": "polygon_snapshot",
                        }
                    elif last > 0:
                        return {
                            "ticker": ticker,
                            "bid": None,
                            "ask": None,
                            "last": last,
                            "mid": last,
                            "spread": None,
                            "spread_pct": None,
                            "source": "polygon_last",
                        }
        except Exception as e:
            logger.debug(f"Polygon quote fetch non-blocking error for {ticker}: {e}")
        return None

    async def _fetch_finnhub_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        """從 Finnhub 抓取即時行情"""
        try:
            finnhub_key = self.settings_service.get_setting("source_finnhub_api_key")
            if not finnhub_key:
                return None

            import httpx
            url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={finnhub_key}"
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    q = resp.json()
                    c = float(q.get("c", 0.0) or 0.0)
                    if c > 0:
                        return {
                            "ticker": ticker,
                            "bid": None,
                            "ask": None,
                            "last": c,
                            "mid": c,
                            "spread": None,
                            "spread_pct": None,
                            "source": "finnhub",
                        }
        except Exception as e:
            logger.debug(f"Finnhub quote fetch error for {ticker}: {e}")
        return None

    async def evaluate_trade(
        self,
        ticker: str,
        action: str,
        amount_usd: Optional[float] = None,
        current_price: Optional[float] = None,
        check_opening_window: bool = True,
        override_max_spread_pct: Optional[float] = None,
    ) -> SlippageGuardDecision:
        """
        全流程防滑點與價差熔斷評估：
        1. 檢查開關是否開啟
        2. 檢測美股開盤前 5 分鐘極端波動率窗口 (09:30-09:35 EST)
        3. 查詢標的即時 Bid-Ask 價差，若超過門檻 (預設 0.15%) 觸發熔斷
        4. 精算自適應限價單上限 (Adaptive Limit Price)
        """
        enabled = self._get_setting_bool("enable_slippage_guard", True)
        if not enabled:
            return SlippageGuardDecision(
                passed=True,
                reason="防滑點守衛已由使用者設定關閉 (enable_slippage_guard=false)",
                recommended_action="PROCEED",
            )

        max_spread = (
            override_max_spread_pct
            if override_max_spread_pct is not None
            else self._get_setting_float("max_allowed_spread_pct", self.DEFAULT_MAX_SPREAD_PCT)
        )

        # 1. 開盤極端波動率視窗檢查 (09:30-09:35 EST)
        if check_opening_window:
            is_opening, open_reason = self.is_opening_auction_window()
            if is_opening:
                logger.warning(f"SlippageGuard: {action.upper()} {ticker} BLOCKED - {open_reason}")
                return SlippageGuardDecision(
                    passed=False,
                    reason=open_reason,
                    circuit_breaker_triggered=True,
                    is_opening_window=True,
                    recommended_action="DEFER",
                )

        # 2. 獲取標的即時報價
        quote = await self.get_ticker_quote(ticker)
        bid = quote.get("bid")
        ask = quote.get("ask")
        mid = quote.get("mid")
        last = quote.get("last") or current_price
        spread_pct = quote.get("spread_pct")

        # 3. 即時買賣價差熔斷檢測
        if spread_pct is not None and spread_pct > max_spread:
            reason = (
                f"即時買賣價差 {spread_pct:.3%} 高於防滑點門檻 {max_spread:.3%} "
                f"(Bid: ${bid:.2f}, Ask: ${ask:.2f})，觸發價差熔斷保護以防止券商滑點吃損。"
            )
            logger.warning(f"SlippageGuard Circuit Breaker TRIGGERED for {action.upper()} {ticker}: {reason}")
            self._record_circuit_breaker_event(
                ticker=ticker,
                action=action,
                spread_pct=spread_pct,
                threshold=max_spread,
                bid=bid,
                ask=ask,
            )
            return SlippageGuardDecision(
                passed=False,
                reason=reason,
                circuit_breaker_triggered=True,
                spread_pct=spread_pct,
                bid_price=bid,
                ask_price=ask,
                mid_price=mid,
                last_price=last,
                recommended_action="DEFER",
            )

        # 4. 價差合格或無即時 Bid/Ask 報價（離線/非交易時段備援）
        ref_price = mid or last or current_price or 1.0
        adaptive_limit = None
        is_buy = str(action).upper() == "BUY"

        if is_buy:
            # 買進自適應限價：保護上限至多為 ask (或 ref_price) 溢價 0.05%
            base_p = ask if (ask and ask > 0) else ref_price
            adaptive_limit = round(base_p * (1.0 + min(max_spread * 0.5, 0.0010)), 2)
        else:
            # 賣出自適應限價：保護下限至多為 bid (或 ref_price) 折價 0.05%
            base_p = bid if (bid and bid > 0) else ref_price
            adaptive_limit = round(base_p * (1.0 - min(max_spread * 0.5, 0.0010)), 2)

        if spread_pct is not None:
            reason = f"即時買賣價差 {spread_pct:.3%} 符合風控門檻 (<= {max_spread:.3%})，流動性充裕放行"
        else:
            reason = "即時買賣報價未提供細部買賣價差，處於常規交易時段且非開盤波動期，予以放行"

        return SlippageGuardDecision(
            passed=True,
            reason=reason,
            circuit_breaker_triggered=False,
            spread_pct=spread_pct,
            bid_price=bid,
            ask_price=ask,
            mid_price=mid,
            last_price=last,
            adaptive_limit_price=adaptive_limit,
            recommended_action="PROCEED",
        )

    def record_realized_slippage(
        self,
        ticker: str,
        action: str,
        expected_price: float,
        fill_price: float,
        order_id: Optional[str] = None,
    ) -> float:
        """
        記錄並稽核訂單成交的實際滑點 (Realized Slippage)。
        若不利滑點超過門檻 (預設 0.20%)，寫入事件記錄並日誌警報。
        """
        if not expected_price or expected_price <= 0 or not fill_price or fill_price <= 0:
            return 0.0

        is_buy = str(action).upper() == "BUY"
        if is_buy:
            # 買入成交價高於預期為不利滑點 (Positive = adverse)
            slippage_pct = (fill_price - expected_price) / expected_price
        else:
            # 賣出成交價低於預期為不利滑點
            slippage_pct = (expected_price - fill_price) / expected_price

        warning_threshold = self._get_setting_float(
            "slippage_warning_pct", self.DEFAULT_SLIPPAGE_WARNING_PCT
        )

        if slippage_pct > warning_threshold:
            logger.warning(
                f"🚨 Execution Slippage Warning: {action.upper()} {ticker} slipped {slippage_pct:+.3%} "
                f"(Expected: ${expected_price:.2f}, Filled: ${fill_price:.2f}, Order: {order_id})"
            )
            try:
                from src.repositories.event_queue_repository import EventQueueRepository
                EventQueueRepository().insert_event(
                    user_id=self.user_id,
                    event_type="slippage_warning",
                    priority=2,
                    content={
                        "ticker": ticker,
                        "action": action.upper(),
                        "expected_price": round(expected_price, 4),
                        "fill_price": round(fill_price, 4),
                        "slippage_pct": round(slippage_pct, 5),
                        "threshold_pct": round(warning_threshold, 5),
                        "order_id": order_id,
                    },
                )
            except Exception as e:
                logger.debug(f"Failed to record slippage warning event: {e}")
        else:
            logger.info(
                f"SlippageGuard: {action.upper()} {ticker} executed with {slippage_pct:+.3%} slippage "
                f"(Expected: ${expected_price:.2f}, Filled: ${fill_price:.2f})"
            )

        return slippage_pct

    def _record_circuit_breaker_event(
        self,
        ticker: str,
        action: str,
        spread_pct: float,
        threshold: float,
        bid: Optional[float],
        ask: Optional[float],
    ) -> None:
        """記錄熔斷事件至事件隊列供審計與通報"""
        try:
            from src.repositories.event_queue_repository import EventQueueRepository
            EventQueueRepository().insert_event(
                user_id=self.user_id,
                event_type="spread_circuit_breaker",
                priority=2,
                content={
                    "ticker": ticker,
                    "action": action.upper(),
                    "spread_pct": round(spread_pct, 5),
                    "threshold_pct": round(threshold, 5),
                    "bid": round(bid, 4) if bid is not None else None,
                    "ask": round(ask, 4) if ask is not None else None,
                    "timestamp": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            logger.debug(f"Failed to record circuit breaker event: {e}")
