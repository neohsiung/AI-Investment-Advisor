import os
import asyncio
import hashlib
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable
from fastapi import APIRouter, Request, HTTPException
from src.utils.logger import setup_logger
from src.utils.async_utils import to_thread
from src.utils.security import redact_secrets
from src.config.rss_config import get_rss_sources
from src.services.settings_service import SettingsService

logger = setup_logger("WebhookService")

webhook_router = APIRouter(tags=["Webhook"])
from src.services.sentinel_service import SentinelService

# Services instance from mcp_service to be injected or accessed
# We will use a dependency or global reference. To avoid circular imports,
# we'll look it up from the app state or a global registry.
# For simplicity, we can pass the sentinel service directly to the router instance,
# or we can keep the parsing logic here and use the router.

class BaseSourceParser:
    """各來源解析器基底"""
    @staticmethod
    def parse(payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload

class MktRecapParser(BaseSourceParser):
    @staticmethod
    def parse(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "MARKET_SPIKE",
            "ticker": payload.get("ticker", "UNKNOWN"),
            "value": payload.get("price") or payload.get("volume"),
            "msg": payload.get("alert_name", "MktRecap Trigger")
        }

class TradingViewParser(BaseSourceParser):
    @staticmethod
    def parse(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "TECHNICAL_SIGNAL",
            "ticker": payload.get("ticker"),
            "signal": payload.get("signal"), # e.g., "BUY", "SELL"
            "msg": payload.get("comment", "TV Alert")
        }

class RssBridgeParser(BaseSourceParser):
    @staticmethod
    def parse(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "NEWS_ALERT",
            "msg": payload.get("title") or payload.get("description", "New RSS Item"),
            "url": payload.get("link")
        }

class FinnhubParser(BaseSourceParser):
    @staticmethod
    def parse(payload: Dict[str, Any]) -> Dict[str, Any]:
        event_type = payload.get("event", "news")
        raw_data = payload.get("data", {})
        
        data = {}
        if isinstance(raw_data, list):
            if raw_data:
                data = raw_data[0]
        elif isinstance(raw_data, dict):
            data = raw_data
            
        ticker = payload.get("ticker")
        if not ticker:
            ticker = data.get("symbol", "UNKNOWN")
        
        msg = f"Finnhub Alert: {event_type}"
        
        if event_type == "earnings":
             msg = f"Earnings Alert for {ticker}: Q{data.get('quarter')} EPS={data.get('eps')}"
        elif event_type == "news":
             msg = data.get("headline", f"News Alert for {ticker}")
             
        return {
            "type": "FINANCIAL_EVENT",
            "ticker": ticker,
            "msg": msg,
            "url": data.get("url")
        }

class N8nParser(BaseSourceParser):
    @staticmethod
    def parse(payload: Dict[str, Any]) -> Dict[str, Any]:
        # n8n typically passes the object directly or via 'body' depending on setup
        data = payload.get("body", payload) if isinstance(payload.get("body"), dict) else payload
        
        # Link-based Deduplication ID
        msg_url = data.get("link") or data.get("url")
        signal_id = data.get("event_id")
        if not signal_id and msg_url:
            signal_id = f"rss_{hashlib.sha256(msg_url.encode()).hexdigest()}"
            
        return {
            "type": data.get("event_type", "N8N_AUTOMATION"),
            "ticker": data.get("ticker", "GLOBAL"),
            "msg": data.get("message") or data.get("msg") or "n8n Triggered Event",
            "value": data.get("value"),
            "url": msg_url,
            "signal_id": signal_id
        }

class PolygonParser(BaseSourceParser):
    @staticmethod
    def parse(payload: Any) -> Dict[str, Any]:
        # Polygon can send a list of events or a single event
        data = payload[0] if isinstance(payload, list) and payload else payload
        
        ev_type = data.get("ev", "unknown")
        ticker = data.get("sym", "UNKNOWN")
        
        msg = f"Polygon.io Alert: {ev_type} for {ticker}"
        if ev_type == "T":
            msg = f"Trade Event for {ticker}: Price={data.get('p')} Size={data.get('s')}"
        elif ev_type == "A":
            msg = f"Aggregate Alert for {ticker}: Close={data.get('c')} Vol={data.get('v')}"
            
        return {
            "type": "POLYGON_EVENT",
            "ticker": ticker,
            "msg": msg,
            "ev": ev_type
        }

class SkillLearningParser(BaseSourceParser):
    @staticmethod
    def parse(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pillar 5: Skill Learning Webhook Parser.
        技能學習 Webhook 解析器：動態處理多種來源（RSS, Podcast, Article）。
        """
        return {
            "type": payload.get("event_type", "SKILL_LEARNING"),
            "content": payload.get("content") or payload.get("article_text") or payload.get("transcript") or payload.get("text", ""),
            "source_url": payload.get("source_url") or payload.get("article_url") or payload.get("audioUrl") or payload.get("url", ""),
            "source_type": payload.get("source_type") or "article",
            "source_name": payload.get("source_name") or payload.get("podcastName", "")
        }

SOURCE_PARSERS = {
    "mktrecap": MktRecapParser,
    "tradingview": TradingViewParser,
    "tradingview_alerts": TradingViewParser,
    "rss": RssBridgeParser,
    "rss_bridge": RssBridgeParser,
    "ifttt": RssBridgeParser,
    "finnhub": FinnhubParser,
    "n8n": N8nParser,
    "make": N8nParser,       # Make.com follows similar logic
    "pipedream": N8nParser,  # Pipedream follows similar logic
    "skill_learning": SkillLearningParser,
    "skill-learning": SkillLearningParser,
    "polygon": PolygonParser,
}

class WebhookService:
    def __init__(self, settings_service: Optional[SettingsService] = None):
        self.settings_service = settings_service or SettingsService()
        import redis
        try:
            self._redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True, socket_connect_timeout=3)
        except Exception as e:
            logger.warning(f'Exception in webhook_service.py: {e}', exc_info=True)
            self._redis = None
        
    async def _resolve_user(self, request: Request) -> str:
        """
        Resolve user_id from API Key in request headers.
        從請求標頭中的 API Key 解析 user_id。
        """
        # Route context: the catch-all POST /webhook/{source} means any stray
        # request lands here, so log which path/source failed — otherwise n8n
        # cannot be told apart from a scanner.
        # 補上來源路徑，否則無法分辨是 n8n 還是掃描器。
        route = getattr(request, "url", None)
        route = route.path if route is not None else "?"
        client = getattr(getattr(request, "client", None), "host", "?")

        api_key = request.headers.get("X-API-Key")
        if not api_key:
            logger.warning(f"Webhook attempt missing X-API-Key (route={route}, client={client})")
            raise HTTPException(status_code=401, detail="Missing X-API-Key")

        user_id = self.settings_service.find_user_by_webhook_secret(api_key)
        if not user_id:
            # settings_repository.find_user_by_webhook_secret already logged a
            # non-secret fingerprint diagnostic explaining WHY it did not match.
            logger.warning(f"Unauthorized API Key attempt (route={route}, client={client})")
            raise HTTPException(status_code=403, detail="Invalid API Key")
            
        return user_id

    def _is_duplicate(self, user_id: str, url: str = None, signal_id: str = None) -> bool:
        """Checks if a URL or signal_id has already been processed in the event queue."""
        if not url and not signal_id:
            return False
            
        try:
            from sqlalchemy import text
            from src.data.database import get_db_engine
            engine = get_db_engine()
            with engine.connect() as conn:
                query_str = """
                    SELECT 1 FROM event_queue 
                    WHERE user_id = :uid 
                    AND (
                        1 = 0
                """
                params = {"uid": user_id}
                if url:
                    query_str += " OR content->>'url' = :url OR content->>'link' = :url OR content->>'summary' LIKE :url_pattern"
                    params["url"] = url
                    params["url_pattern"] = f"%{url}%"
                if signal_id:
                    query_str += " OR content->>'signal_id' = :signal_id"
                    params["signal_id"] = signal_id
                query_str += "\n) LIMIT 1"
                
                exists = conn.execute(text(query_str), params).first()
                return bool(exists)
        except Exception as e:
            logger.error(f"Duplicate check failed: {e}")
            return False

    def _acquire_concurrency_lock(self, user_id: str, url: str = None, signal_id: str = None) -> bool:
        """
        Acquire a Redis lock for this specific webhook event to prevent concurrent processing.
        獲取特定 Webhook 事件的 Redis 鎖，以防止併發處理。
        """
        if not self._redis or (not url and not signal_id):
            return True # If Redis is unavailable, skip the lock check (graceful degradation)
            
        try:
            key_source = url or signal_id
            hashed = hashlib.sha256(key_source.encode("utf-8")).hexdigest()
            lock_key = f"lock:webhook:{user_id}:{hashed}"
            
            # SETNX with a 15-second expiration
            acquired = self._redis.set(lock_key, "locked", ex=15, nx=True)
            return bool(acquired)
        except Exception as e:
            logger.error(f"Failed to acquire concurrency lock: {e}")
            return True # Fallback: proceed on Redis failure

    async def handle_generic_webhook(self, source: str, request: Request) -> Dict[str, str]:
        user_id = await self._resolve_user(request)
        logger.info(f"Webhook {source} for user {user_id}")

        try:
            payload = await request.json()
            logger.info(f"Received webhook from {source}: {payload}")
            
            parser = SOURCE_PARSERS.get(source.lower(), BaseSourceParser)
            normalized_data = parser.parse(payload)
            
            # Deduplication Check
            url = normalized_data.get("url")
            signal_id = normalized_data.get("signal_id")
            if self._is_duplicate(user_id, url=url, signal_id=signal_id):
                logger.info(f"Webhook: Duplicate event skipped. url={url}, signal_id={signal_id}")
                return {"status": "skipped", "reason": "duplicate", "url": url}
            
            # Concurrency Lock Check (SETNX)
            if not self._acquire_concurrency_lock(user_id, url=url, signal_id=signal_id):
                logger.info(f"Webhook: Concurrent duplicate event locked. url={url}, signal_id={signal_id}")
                return {"status": "skipped", "reason": "concurrent_lock", "url": url}
            
            # Route skill-learning events to InvestmentSkillLearningService
            if source.lower() in ("skill-learning", "skill_learning"):
                from src.services.investment_skill_learning_service import (
                    InvestmentSkillLearningService,
                )
                svc = InvestmentSkillLearningService(user_id=user_id)
                asyncio.create_task(
                    svc.run_daily_learning(
                        content=normalized_data.get("content", ""),
                        source_url=normalized_data.get("source_url", ""),
                        source_type=normalized_data.get("source_type", "article"),
                    )
                )
                return {"status": "accepted", "user_id": user_id, "source": source, "workflow": "skill_learning"}
            
            # [Refactor] Independent Event Analysis Workflow (v6.0)
            # Instead of just Sentinel, we trigger a full Agent-driven Workflow.
            from src.services.workflow_service import EventAnalysisWorkflow
            event_workflow = EventAnalysisWorkflow(
                user_id=user_id,
                event_source=source,
                event_data=normalized_data
            )
            asyncio.create_task(event_workflow.run())
            
            # Keep Sentinel for background/secondary monitoring if needed
            # For now, we prefer the deterministic EventAnalysisWorkflow for external signals.
            # (Optional: sentinel = SentinelService(user_id=user_id); asyncio.create_task(sentinel.process_event(...)))
            
            return {"status": "accepted", "user_id": user_id, "source": source}
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            raise HTTPException(status_code=400, detail="Invalid payload")

    async def handle_finnhub_webhook(self, request: Request) -> Dict[str, str]:
        """
        Finnhub Webhook Handler with Secret Verification.
        Finnhub uses X-Finnhub-Secret header (not X-API-Key).
        """
        # Step 1: Verify Finnhub secret FIRST (acknowledge before heavy processing!)
        received_secret = request.headers.get("X-Finnhub-Secret")
        
        # Look up secret from DB settings (admin user), fallback to env var
        expected_secret = ""
        try:
            admin_user_id = os.getenv("DEFAULT_FINNHUB_USER_ID")
            if not admin_user_id:
                from src.repositories.user_repository import AlchemyUserRepository
                admin_user_id = AlchemyUserRepository().get_first_user_id()
            from src.services.settings_service import SettingsService
            svc = SettingsService(user_id=admin_user_id)
            expected_secret = svc.get_setting("source_finnhub_webhook_secret", "")
        except Exception as e:
            logger.warning(f'Exception in webhook_service.py: {e}', exc_info=True)
        
        if not expected_secret:
            expected_secret = os.getenv("FINNHUB_WEBHOOK_SECRET", "")
        
        if not received_secret or not expected_secret or received_secret != expected_secret:
            client_ip = request.headers.get("X-Forwarded-For", "unknown")
            logger.warning(f"Invalid Finnhub secret from {client_ip}")
            # CRITICAL: Return 200 OK even on failure (prevent Finnhub from disabling endpoint)
            return {"status": "acknowledged", "detail": "invalid_secret"}
        
        try:
            payload = await request.json()
            logger.info(f"Received verified Finnhub webhook: {payload}")
            
            normalized = FinnhubParser.parse(payload)
            
            # Resolve user (Finnhub doesn't provide user context in payload)
            user_id = os.getenv("DEFAULT_FINNHUB_USER_ID")
            if not user_id:
                from src.repositories.user_repository import AlchemyUserRepository
                user_id = AlchemyUserRepository().get_first_user_id()
            
            # Deduplication Check
            url = normalized.get("url")
            signal_id = normalized.get("signal_id")
            if self._is_duplicate(user_id, url=url, signal_id=signal_id):
                logger.info(f"Finnhub webhook: Duplicate event skipped. url={url}, signal_id={signal_id}")
                return {"status": "skipped", "reason": "duplicate", "url": url}
            
            # Concurrency Lock Check (SETNX)
            if not self._acquire_concurrency_lock(user_id, url=url, signal_id=signal_id):
                logger.info(f"Finnhub webhook: Concurrent duplicate event locked. url={url}, signal_id={signal_id}")
                return {"status": "skipped", "reason": "concurrent_lock", "url": url}
            
            # [Refactor] Independent Event Analysis Workflow (v6.0)
            from src.services.workflow_service import EventAnalysisWorkflow
            event_workflow = EventAnalysisWorkflow(
                user_id=user_id,
                event_source="finnhub",
                event_data=normalized
            )
            asyncio.create_task(event_workflow.run())
            
            return {"status": "accepted", "user_id": user_id}
        except Exception as e:
            logger.error(f"Finnhub webhook error: {e}")
            # Still return 200 to acknowledge
            return {"status": "acknowledged", "detail": "processing_error"}

    async def handle_stripe_webhook(self, request: Request) -> Dict[str, Any]:
        """
        Stripe Webhook Handler (2026-07-12) — implements the product spec's
        "checkout.session.completed 觸發 account_id 初始化流程" (Webhook-觸發
        源整合指南 §14): on successful checkout, create/resolve the user
        account, seed default settings (webhook_api_key, sentinel thresholds,
        risk keywords), and send a welcome notification.

        Verifies the `Stripe-Signature` header via the official SDK
        (stripe.Webhook.construct_event) — signature verification failures
        return 400 (Stripe's own recommended practice), distinct from the
        always-200 pattern used by best-effort sources like Finnhub.

        `stripe_webhook_secret` is read from Settings (admin user) first,
        falling back to the STRIPE_WEBHOOK_SECRET env var — same pattern as
        Finnhub's source_finnhub_webhook_secret. Neither is hardcoded here;
        until configured, this endpoint safely rejects all events (503).
        """
        try:
            import stripe
        except ImportError:
            logger.error("Stripe webhook received but 'stripe' package is not installed")
            raise HTTPException(status_code=503, detail="Stripe integration not available")

        admin_user_id = os.getenv("DEFAULT_STRIPE_ADMIN_USER_ID")
        if not admin_user_id:
            from src.repositories.user_repository import AlchemyUserRepository
            admin_user_id = AlchemyUserRepository().get_first_user_id()
        endpoint_secret = ""
        try:
            svc = SettingsService(user_id=admin_user_id)
            endpoint_secret = svc.get_setting("stripe_webhook_secret", "")
        except Exception as e:
            logger.warning(f'Exception in webhook_service.py: {e}', exc_info=True)
        if not endpoint_secret:
            endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        if not endpoint_secret:
            logger.warning("Stripe webhook rejected: stripe_webhook_secret not configured")
            raise HTTPException(status_code=503, detail="Stripe webhook not configured")

        raw_payload = await request.body()
        sig_header = request.headers.get("Stripe-Signature", "")
        try:
            event = stripe.Webhook.construct_event(raw_payload, sig_header, endpoint_secret)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            logger.warning(f"Stripe webhook signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")

        if event.get("type") != "checkout.session.completed":
            # Acknowledge other event types without processing — we only act on completed checkouts.
            return {"status": "ignored", "event_type": event.get("type")}

        try:
            session = event["data"]["object"]
            email = (
                session.get("customer_details", {}).get("email")
                or session.get("customer_email")
            )
            if not email:
                logger.warning("Stripe checkout.session.completed missing customer email")
                return {"status": "acknowledged", "detail": "no_email"}

            from src.repositories.user_repository import AlchemyUserRepository
            user_repo = AlchemyUserRepository()

            existing = user_repo.get_by_identity("email", email)
            if existing:
                user_id = existing["id"]
                logger.info(f"Stripe checkout: existing user resolved for {redact_secrets(email)}")
            else:
                user_id = user_repo.create_user(email=email, name=session.get("customer_details", {}).get("name"))
                logger.info(f"Stripe checkout: created new user {user_id[:8]}... for {redact_secrets(email)}")

            settings_svc = SettingsService(user_id=user_id)
            settings_svc.initialize_user_settings(user_id)

            try:
                from src.services.notification_service import NotificationService
                notif_svc = NotificationService.create_with_settings(settings_service=settings_svc, user_id=user_id)
                asyncio.create_task(notif_svc.send_report(
                    subject="🎉 歡迎加入 AI Investment Advisor",
                    content="您的訂閱已啟用，帳戶已完成初始化。前往 Settings 設定您的投資偏好與券商連結即可開始使用。",
                    user_id=user_id,
                ))
            except Exception as notif_err:
                logger.warning(f"Stripe welcome notification failed (non-blocking): {notif_err}")

            return {"status": "accepted", "user_id": user_id}
        except Exception as e:
            logger.error(f"Stripe webhook processing error: {e}")
            # Acknowledge to prevent Stripe retry storms once signature is verified —
            # a processing bug shouldn't cause repeated retries of the same event.
            return {"status": "acknowledged", "detail": "processing_error"}

# Global instance for routing
webhook_service_instance = WebhookService()

@webhook_router.post("/finnhub")
async def finnhub_webhook(request: Request):
    return await webhook_service_instance.handle_finnhub_webhook(request)

@webhook_router.post("/stripe")
async def stripe_webhook(request: Request):
    return await webhook_service_instance.handle_stripe_webhook(request)

@webhook_router.get("/rss-sources", tags=["RSS"])
async def get_rss_sources_list(request: Request):
    """
    Expose RSS configuration for n8n to fetch dynamically.
    """
    user_id = await webhook_service_instance._resolve_user(request)
    logger.info(f"Serving /rss-sources request for user {user_id}")
    try:
        sources = get_rss_sources(user_id=user_id)
        logger.info(f"Returning {len(sources)} RSS sources for user {user_id}")
        return sources
    except Exception as e:
        logger.error(f"Error getting RSS sources: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve RSS sources")


@webhook_router.get("/heartbeat")
@webhook_router.post("/heartbeat")
async def heartbeat_webhook(request: Request):
    """
    系統心跳端口 (Phase 3)
    v5.0: Requires X-API-Key to trigger user-specific sentinel tick.
    """
    svc = WebhookService()
    user_id = await svc._resolve_user(request)
    
    sentinel = SentinelService(user_id=user_id)
    asyncio.create_task(sentinel.process_tick())
    
    return {"status": "alive", "user_id": user_id, "message": "Sentinel tick triggered."}

@webhook_router.post("/podcast-extract")
async def podcast_extract_webhook(request: Request):
    """
    音檔轉錄與技能學習 Webhook (解決 n8n 413 錯誤)。
    """
    svc = WebhookService()
    user_id = await svc._resolve_user(request)
    payload = await request.json()
    
    audio_url = payload.get("audioUrl")
    podcast_name = payload.get("podcastName", "Podcast")
    
    from src.services.transcription_service import TranscriptionService
    from src.services.investment_skill_learning_service import InvestmentSkillLearningService
    
    transcriber = TranscriptionService(user_id=user_id)
    skill_svc = InvestmentSkillLearningService(user_id=user_id)
    
    async def process_task():
        try:
            transcript = await transcriber.transcribe_url(audio_url)
            if transcript and not transcript.startswith("Error:"):
                # Run learning in a thread as it might be synchronous or heavy
                await skill_svc.run_daily_learning(
                    content=transcript,
                    source_url=audio_url,
                    source_type="podcast",
                    source_name=podcast_name
                )
                logger.info(f"Successfully processed podcast: {podcast_name}")
        except Exception as e:
            logger.error(f"Error processing podcast extract: {e}")

    asyncio.create_task(process_task())
    return {"status": "accepted", "message": "Podcast transcription process initiated."}

@webhook_router.post("/market-alert")
async def market_alert_webhook(request: Request):
    """
    市場異常波動警報端口 (Phase 3)
    當接收到如 TradingView, News API 傳來的異常波動訊號時，系統直接喚醒 Sentinel 進行即時分析。
    """
    return await webhook_service_instance.handle_generic_webhook("market-alert", request)


@webhook_router.post("/telegram")
async def telegram_bot_webhook(request: Request):
    """
    Telegram Bot Webhook Receiver.
    Handles inbound messages (commands) and callback_query (inline buttons) from Telegram.

    Telegram Bot setWebhook 接收端點：
      - /report   → 立即觸發每日報告
      - /status   → 回傳帳戶持倉摘要
      - /sentinel → 手動觸發一次 Sentinel check
      - /portfolio → 回傳現金比例和持倉列表

    Setup: 到 https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://YOUR_DOMAIN/webhook/telegram
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.warning(f'Exception in webhook_service.py: {e}', exc_info=True)
        return {"ok": True}  # Telegram expects 200 always

    # Identify sender chat_id from either message or callback_query
    chat_id: str | None = None
    text: str = ""
    callback_data: str | None = None

    msg = payload.get("message") or payload.get("edited_message")
    cb = payload.get("callback_query")

    if msg:
        chat = msg.get("chat", {})
        chat_id = str(chat.get("id", ""))
        text = (msg.get("text") or "").strip()
    elif cb:
        chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
        callback_data = cb.get("data", "")

    if not chat_id:
        return {"ok": True}

    # Resolve internal user_id from chat_id
    try:
        from src.services.settings_service import SettingsService
        ss = SettingsService()
        user_id = ss.find_user_by_channel_id(chat_id)
    except Exception as e:
        logger.error(f"Telegram webhook: failed to resolve user for chat {chat_id}: {e}")
        user_id = None

    if not user_id:
        logger.warning(f"Telegram webhook: unknown chat_id {chat_id}, ignoring.")
        return {"ok": True}

    # Helper: send reply back to chat
    async def _reply(reply_text: str):
        try:
            from src.services.settings_service import SettingsService
            ss = SettingsService(user_id=user_id)
            bot_token = ss.get_setting("channel_telegram_bot_token", "")
            if not bot_token:
                return
            import httpx
            import html
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": reply_text[:4000], "parse_mode": "HTML"}
                )
        except Exception as e:
            logger.error(f"Telegram reply failed: {e}")

    # Callback query (inline button press)
    if callback_data:
        logger.info(f"Telegram callback: {callback_data} from chat {chat_id} (user {user_id[:8]}...)")
        # Delegate to TelegramAdapter handle_webhook for callback handling
        try:
            from src.infrastructure.channels.telegram_adapter import TelegramAdapter
            from src.services.settings_service import SettingsService
            from src.services.interaction_service import InteractionService
            ss = SettingsService(user_id=user_id)
            adapter = TelegramAdapter(
                bot_token=ss.get_setting("channel_telegram_bot_token", ""),
                chat_id=chat_id
            )
            # Register interaction callback to handle Approve/Reject clicks
            interaction_svc = InteractionService(settings_service=ss)
            adapter.register_callback(interaction_svc.handle_response)
            
            asyncio.create_task(adapter.handle_webhook(payload))
        except Exception as e:
            logger.error(f"Telegram callback handling failed: {e}")
        return {"ok": True}

    # Text commands
    cmd = text.split()[0].lower() if text else ""
    logger.info(f"Telegram command: '{cmd}' from chat {chat_id} (user {user_id[:8]}...)")

    if cmd in ("/start", "/help"):
        help_text = (
            "🤖 <b>Investment Advisor Bot</b>\n\n"
            "可用指令 (Available commands):\n"
            "/report   — 立即生成每日投資報告\n"
            "/status   — 查看帳戶現金與持倉摘要\n"
            "/sentinel — 手動觸發 Sentinel 市場掃描\n"
            "/portfolio — 詳細持倉清單與比例\n"
            "/backtest <TICKER> — 執行快速策略回測\n"
            "/health   — 系統健康與保護機制狀態\n"
            "/pause    — 暫停 AI 自動交易\n"
            "/resume   — 恢復 AI 自動交易"
        )
        asyncio.create_task(_reply(help_text))

    elif cmd == "/status":
        async def _status():
            try:
                from src.services.etoro_service import EtoroService
                etoro = EtoroService(user_id=user_id)
                port = await to_thread(etoro.get_portfolio)
                positions = port.get("positions", [])
                cash = port.get("cash_available", 0)
                nlv = port.get("net_liquidation_value", 0)
                cash_pct = (cash / nlv * 100) if nlv else 0
                lines = [f"💼 <b>帳戶快照 ({len(positions)} 持倉)</b>", f"💵 現金: ${cash:,.0f} ({cash_pct:.1f}%)", f"📊 NLV: ${nlv:,.0f}", ""]
                for p in sorted(positions, key=lambda x: -(x.get("value", 0)))[:10]:
                    lines.append(f"• {p.get('ticker','?')}: ${p.get('value',0):,.0f} ({p.get('pnl_pct',0):.1f}%)")
                await _reply("\n".join(lines))
            except Exception as e:
                await _reply(f"❌ 無法取得帳戶狀態: {e}")
        asyncio.create_task(_status())

    elif cmd == "/portfolio":
        async def _portfolio():
            try:
                from src.services.etoro_service import EtoroService
                etoro = EtoroService(user_id=user_id)
                port = await to_thread(etoro.get_portfolio)
                positions = port.get("positions", [])
                lines = [f"📊 <b>完整持倉清單 ({len(positions)} 筆)</b>", ""]
                for p in sorted(positions, key=lambda x: -(x.get("value", 0))):
                    ticker = p.get("ticker", "?")
                    val = p.get("value", 0)
                    pnl = p.get("pnl_pct", 0)
                    pnl_str = f"+{pnl:.1f}%" if pnl >= 0 else f"{pnl:.1f}%"
                    lines.append(f"• {ticker}: ${val:,.0f} ({pnl_str})")
                await _reply("\n".join(lines))
            except Exception as e:
                await _reply(f"❌ 無法取得持倉: {e}")
        asyncio.create_task(_portfolio())

    elif cmd == "/sentinel":
        async def _sentinel():
            await _reply("⚙️ 正在執行 Sentinel 市場掃描，請稍候...")
            try:
                sentinel = SentinelService(user_id=user_id)
                await sentinel.process_tick()
                await _reply("✅ Sentinel 掃描完成，若有警報將另行通知。")
            except Exception as e:
                await _reply(f"❌ Sentinel 執行失敗: {e}")
        asyncio.create_task(_sentinel())

    elif cmd == "/report":
        async def _report():
            await _reply("📊 正在生成每日投資報告，請稍候...")
            try:
                from src.services.workflow_service import DailyWorkflow
                wf = DailyWorkflow(user_id=user_id)
                asyncio.create_task(wf.run())
                await _reply("✅ 每日報告已開始生成，完成後將自動送達。")
            except Exception as e:
                await _reply(f"❌ 報告生成失敗: {e}")
        asyncio.create_task(_report())

    elif cmd == "/backtest":
        # P5.4 (2026-07-11): quick MA-crossover backtest for a ticker, reported inline.
        async def _backtest():
            parts = text.split()
            ticker = parts[1].upper() if len(parts) > 1 else None
            if not ticker:
                await _reply("用法: /backtest <TICKER>，例如 /backtest AAPL")
                return
            await _reply(f"📈 正在對 {ticker} 執行回測，請稍候...")
            try:
                from src.services.market_data_service import MarketDataService
                from src.services.portfolio_backtest_engine import PortfolioBacktestEngine, simple_ma_crossover_signal
                from src.repositories.backtest_repository import AlchemyBacktestRepository

                market_service = MarketDataService(user_id=user_id)
                ohlcv = await to_thread(market_service.get_ohlcv, ticker, 180)
                if not ohlcv or not ohlcv.get("close") or len(ohlcv["close"]) < 35:
                    await _reply(f"❌ {ticker} 歷史數據不足，無法回測")
                    return
                engine = PortfolioBacktestEngine()
                result = engine.run(ticker, ohlcv, simple_ma_crossover_signal(10, 30))
                m = result.metrics
                AlchemyBacktestRepository().save_run(
                    user_id=user_id, ticker=ticker, strategy_name="ma_crossover_10_30",
                    initial_cash=100_000.0, final_cash=result.final_cash, metrics=m,
                    trades=result.trades, equity_curve=result.equity_curve, dates=result.dates,
                    params={"fast_ma": 10, "slow_ma": 30},
                )

                def fmt(v, suffix=""):
                    return f"{v:.2f}{suffix}" if v is not None else "—"

                lines = [
                    f"📈 <b>{ticker} 回測結果</b> (MA 10/30, 180日)",
                    f"最終資金: ${result.final_cash:,.0f} (初始 $100,000)",
                    f"Sharpe: {fmt(m.get('sharpe'))} · Sortino: {fmt(m.get('sortino'))}",
                    f"CAGR: {fmt(m.get('cagr_pct'), '%')} · 最大回撤: {fmt(m.get('max_drawdown_pct'), '%')}",
                    f"勝率: {fmt(m.get('win_rate_pct'), '%')} · 交易次數: {m.get('total_trades', 0)}",
                ]
                await _reply("\n".join(lines))
            except Exception as e:
                await _reply(f"❌ 回測失敗: {e}")
        asyncio.create_task(_backtest())

    elif cmd == "/health":
        # P5.4 (2026-07-11): trading status + active protection halts at a glance.
        async def _health():
            try:
                from src.services.settings_service import SettingsService
                ss = SettingsService(user_id=user_id)
                trading_enabled = ss.get_setting("ai_trading_enabled", "true")
                from src.services.trading_protections_service import TradingProtectionsService
                protection_note = TradingProtectionsService(user_id=user_id).check("HEALTHCHECK", "BUY")
                lines = [
                    "🩺 <b>系統健康檢查</b>",
                    f"AI 交易: {'✅ 啟用' if str(trading_enabled).lower() != 'false' else '⏸️ 已暫停'}",
                    f"保護機制: {'⚠️ ' + protection_note if protection_note else '✅ 正常，無停機觸發'}",
                ]
                await _reply("\n".join(lines))
            except Exception as e:
                await _reply(f"❌ 健康檢查失敗: {e}")
        asyncio.create_task(_health())

    elif cmd == "/pause":
        async def _pause():
            try:
                from src.services.settings_service import SettingsService
                SettingsService(user_id=user_id).save_setting("ai_trading_enabled", "false")
                await _reply("⏸️ AI 自動交易已暫停。使用 /resume 恢復。")
            except Exception as e:
                await _reply(f"❌ 暫停失敗: {e}")
        asyncio.create_task(_pause())

    elif cmd == "/resume":
        async def _resume():
            try:
                from src.services.settings_service import SettingsService
                SettingsService(user_id=user_id).save_setting("ai_trading_enabled", "true")
                await _reply("▶️ AI 自動交易已恢復。")
            except Exception as e:
                await _reply(f"❌ 恢復失敗: {e}")
        asyncio.create_task(_resume())

    else:
        if text and not text.startswith("/"):
            # Treat freeform text as a chat query (delegate to ConversationAgent)
            async def _chat():
                try:
                    from src.agents.conversation_agent import ConversationAgent
                    agent = ConversationAgent(user_id=user_id)
                    result = await agent.chat(text)
                    reply = result.get("response", "抱歉，我暫時無法回答這個問題。")
                    await _reply(f"🤖 {reply}")
                except Exception as e:
                    await _reply(f"❌ 無法處理查詢: {e}")
            asyncio.create_task(_chat())

    return {"ok": True}


@webhook_router.post("/{source}")
async def generic_webhook(source: str, request: Request):
    return await webhook_service_instance.handle_generic_webhook(source, request)

