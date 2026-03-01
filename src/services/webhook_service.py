import os
import asyncio
import hashlib
from typing import Dict, Any, List
from fastapi import APIRouter, Request, HTTPException
from src.utils.logger import setup_logger
from src.config.rss_config import get_rss_sources

logger = setup_logger("WebhookService")

webhook_router = APIRouter(tags=["Webhook"])

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
            signal_id = f"rss_{hashlib.md5(msg_url.encode()).hexdigest()}"
            
        return {
            "type": data.get("event_type", "N8N_AUTOMATION"),
            "ticker": data.get("ticker", "GLOBAL"),
            "msg": data.get("message") or data.get("msg") or "n8n Triggered Event",
            "value": data.get("value"),
            "url": msg_url,
            "signal_id": signal_id
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
    "pipedream": N8nParser   # Pipedream follows similar logic
}

class WebhookService:
    def __init__(self, sentinel_service=None):
        self.sentinel_service = sentinel_service
        
    def set_sentinel_service(self, sentinel_service):
        self.sentinel_service = sentinel_service

    async def handle_generic_webhook(self, source: str, request: Request) -> Dict[str, str]:
        webhook_secret = os.getenv("WEBHOOK_SECRET")
        if webhook_secret:
            request_secret = request.headers.get("X-Webhook-Secret")
            if request_secret != webhook_secret:
                logger.warning(f"Unauthorized webhook attempt from {source}")
                raise HTTPException(status_code=403, detail="Unauthorized")

        try:
            payload = await request.json()
            logger.info(f"Received webhook from {source}: {payload}")
            
            parser = SOURCE_PARSERS.get(source.lower(), BaseSourceParser)
            normalized_data = parser.parse(payload)
            
            if self.sentinel_service:
                asyncio.create_task(
                    self.sentinel_service.process_event({
                        "source": source,
                        "data": normalized_data
                    })
                )
            
            return {"status": "accepted", "source": source}
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            raise HTTPException(status_code=400, detail="Invalid payload")

    async def handle_finnhub_webhook(self, request: Request) -> Dict[str, str]:
        secret = os.getenv("FINNHUB_WEBHOOK_SECRET")
        if secret:
            req_secret = request.headers.get("X-Finnhub-Secret")
            if req_secret != secret:
                 logger.warning("Unauthorized Finnhub webhook attempt")
                 raise HTTPException(status_code=403, detail="Unauthorized")
        
        try:
            payload = await request.json()
            logger.info(f"Received Finnhub webhook: {payload}")
            
            normalized = FinnhubParser.parse(payload)
            
            if self.sentinel_service:
                 asyncio.create_task(
                    self.sentinel_service.process_event({
                        "source": "finnhub",
                        "data": normalized
                    })
                 )
            
            return {"status": "accepted"}
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
async def heartbeat_webhook():
    """
    系統心跳端口 (Phase 3)
    觸發 Sentinel 常規掃描或做為外部存活檢查 (Heartbeat API)。
    """
    if webhook_service_instance.sentinel_service:
        # Trigger an asynchronous tick
        import asyncio
        asyncio.create_task(webhook_service_instance.sentinel_service.process_tick())
    return {"status": "alive", "message": "Heartbeat received. Sentinel tick triggered in background."}

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
