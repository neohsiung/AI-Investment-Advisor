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

class SkillLearningParser(BaseSourceParser):
    """Parser for investment skill learning events (articles, podcast transcripts)."""
    @staticmethod
    def parse(payload: Dict[str, Any]) -> Dict[str, Any]:
        data = payload.get("body", payload) if isinstance(payload.get("body"), dict) else payload
        return {
            "type": data.get("event_type", "SKILL_LEARNING"),
            "content": data.get("transcript") or data.get("article_text") or data.get("content") or "",
            "source_url": data.get("article_url") or data.get("source_url") or data.get("url") or "",
            "source_type": data.get("source_type", "article"),
            "source_name": data.get("source_name", ""),
            "msg": data.get("message") or f"Skill learning: {data.get('source_type', 'article')}",
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

@webhook_router.post("/{source}")
async def generic_webhook(source: str, request: Request):
    return await webhook_service_instance.handle_generic_webhook(source, request)
