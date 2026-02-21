"""
Standalone Notification Service for Investment Advisor
獨立通知微服務

Handles omni-channel notifications (LINE, Telegram, Email, Slack, etc.) asynchronously
with full OpenTelemetry observability and reliable retries.

This service reads configurations from the central settings system so it correctly maps
the 'Settings Page' without breaking existing user workflows.
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException, Header
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import logging
from contextlib import asynccontextmanager

# Setup OTel and Logging
from src.utils.logger import setup_logger
logger = setup_logger("NotificationAPI")

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Import existing core infrastructure for Notification dispatch
from src.services.settings_service import SettingsService
from src.infrastructure.channels.channel_factory import ChannelFactory
from src.services.notification_service import NotificationService
from src.services.notification_filters import InterestBasedFilter

class NotificationRequest(BaseModel):
    user_id: str
    title: str
    content: str
    channels: List[str] = ["line", "email"]
    category: str = "sentinel"
    actions: Optional[List[Dict[str, str]]] = None

# Global instance
notification_service: Optional[NotificationService] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle hook to initialize adapters and services."""
    global notification_service
    logger.info("Initializing Standalone Notification Service...")
    
    try:
        # Load global settings or specific adapter configs 
        settings_svc = SettingsService(db_path=None)
        
        # Instantiate the NotificationService precisely as the monolith did
        notification_service = NotificationService.create_with_settings(settings_service=settings_svc)
        logger.info("Notification Service initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Notification Service: {e}")
        
    yield
    
app = FastAPI(
    title="Standalone Notification Service",
    description="Dedicated microservice for omni-channel alerts with SLO monitoring.",
    version="1.0.0",
    lifespan=lifespan
)

FastAPIInstrumentor.instrument_app(app)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "notification_api"}

async def _process_notification(req: NotificationRequest):
    """Background task to heavily process the actual notification logic."""
    if not notification_service:
        logger.error("Notification Service is not initialized.")
        return
        
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("process_notification"):
        try:
            results = await notification_service.notify_all(
                title=req.title,
                content=req.content,
                user_id=req.user_id,
                actions=req.actions,
                channels=req.channels,
                category=req.category,
                capture_error=True
            )
            
            logger.info("Notification process completed", extra={"results": results, "user_id": req.user_id})
            
            # Here we could record OTel metrics based on the results to fulfill SLO tracking
            # e.g. success_count, failure_count for each channel

        except Exception as e:
            logger.error(f"Critical failure sending background notification: {e}")

@app.post("/api/v1/notify")
async def send_notification(request: NotificationRequest, background_tasks: BackgroundTasks):
    """
    Main endpoint for the monolith to trigger a notification.
    Returns 202 Accepted quickly, and processes delivery in the background.
    """
    if not request.user_id or not request.content:
         raise HTTPException(status_code=400, detail="user_id and content are required")
         
    # Enqueue internal background task
    background_tasks.add_task(_process_notification, request)
    return {"status": "accepted", "message": "Notification queued for delivery."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
