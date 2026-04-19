import os
import asyncio
import hashlib
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable
from fastapi import APIRouter, Request, HTTPException
from src.utils.logger import setup_logger
from src.utils.async_utils import to_thread
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
        return {
            "type": "SKILL_LEARNING",
            "content": payload.get("content") or payload.get("text", ""),
            "source_url": payload.get("source_url") or payload.get("url", ""),
            "source_type": payload.get("source_type") or "article"
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
        
    async def _resolve_user(self, request: Request) -> str:
        """
        Resolve user_id from API Key in request headers.
        從請求標頭中的 API Key 解析 user_id。
        """
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            logger.warning("Webhook attempt missing X-API-Key")
            raise HTTPException(status_code=401, detail="Missing X-API-Key")
            
        user_id = self.settings_service.find_user_by_webhook_secret(api_key)
        if not user_id:
            logger.warning("Unauthorized API Key attempt")
            raise HTTPException(status_code=403, detail="Invalid API Key")
            
        return user_id

    async def handle_generic_webhook(self, source: str, request: Request) -> Dict[str, str]:
        user_id = await self._resolve_user(request)
        logger.info(f"Webhook {source} for user {user_id}")

        try:
            payload = await request.json()
            logger.info(f"Received webhook from {source}: {payload}")
            
            parser = SOURCE_PARSERS.get(source.lower(), BaseSourceParser)
            normalized_data = parser.parse(payload)
            
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
        user_id = await self._resolve_user(request)
        
        try:
            payload = await request.json()
            logger.info(f"Received Finnhub webhook for user {user_id}: {payload}")
            
            normalized = FinnhubParser.parse(payload)
            
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
            raise HTTPException(status_code=400, detail="Processing failed")

# Global instance for routing
webhook_service_instance = WebhookService()

@webhook_router.post("/finnhub")
async def finnhub_webhook(request: Request):
    return await webhook_service_instance.handle_finnhub_webhook(request)

@webhook_router.get("/rss-sources", tags=["RSS"])
async def get_rss_sources_list():
    """
    Expose RSS configuration for n8n to fetch dynamically.
    """
    logger.info("Serving /rss-sources request")
    try:
        sources = get_rss_sources()
        logger.info(f"Returning {len(sources)} RSS sources")
        return sources
    except Exception as e:
        logger.error(f"Error getting RSS sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    except Exception:
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
            ss = SettingsService(user_id=user_id)
            adapter = TelegramAdapter(
                bot_token=ss.get_setting("channel_telegram_bot_token", ""),
                chat_id=chat_id
            )
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
            "/portfolio — 詳細持倉清單與比例"
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

