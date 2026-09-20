"""
Discord notification channel.

Added in M7 as the proof that a channel can now be introduced without touching
ChannelFactory: this file plus one entry in config/channels.yaml, no factory edit,
no new module-level import. Under the previous design it would also have required
a seventh near-identical if-block inside `create_adapters`.

Uses an incoming webhook, the same approach as GoogleChatAdapter — no bot token,
no gateway connection, so there is nothing to authenticate inbound.

M7 新增，用以證明新增通知管道無須改動 ChannelFactory：一個檔案加一個 manifest 條目。
在舊設計下還得在 create_adapters 裡再寫第七段幾乎相同的 if 區塊。
採用 incoming webhook（與 GoogleChatAdapter 相同），無 bot token、無需驗證入向請求。
"""
from __future__ import annotations

import os
import typing
from typing import Any, Dict, List

from src.infrastructure.channels.base_adapter import BaseChannelAdapter
from src.utils.logger import setup_logger

logger = setup_logger("DiscordAdapter")

# Discord rejects messages over 2000 characters outright rather than truncating,
# so a long report must be cut here or the whole notification is lost.
# Discord 對超過 2000 字元的訊息直接拒收而非截斷，過長的報告必須在此裁切，
# 否則整則通知會消失。
_MAX_CONTENT = 1900


class DiscordAdapter(BaseChannelAdapter):
    """Outbound-only Discord channel via an incoming webhook."""

    def __init__(self, webhook_url: str = None):
        super().__init__()
        self.webhook_url = (webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")).strip()
        self.is_active = bool(self.webhook_url)

    async def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        if isinstance(message, str):
            return await self.send_alert(user_id, "Message", message)
        return False

    async def receive_command(self, payload: Any, **kwargs) -> Any:
        """Webhooks are one-way; there is no inbound command path."""
        return None

    async def authenticate(self, request: Any, **kwargs) -> bool:
        return True

    def verify_signature(self, payload: Any, headers: Dict[str, Any] = None) -> bool:
        """
        No inbound requests exist for this adapter, so there is no signature to
        verify. Returning False rather than True: if an inbound path is ever added,
        it must fail closed until someone implements verification.
        本適配器沒有入向請求，故無簽章可驗。刻意回傳 False——若未來新增入向路徑，
        必須先實作驗證，在那之前一律拒絕。
        """
        return False

    async def send_alert(self, user_id: str, title: str, content: str,
                         actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        import httpx

        if not self.webhook_url:
            logger.warning("DiscordAdapter: no webhook URL configured; skipping send")
            return False

        body = content or ""
        if len(body) > _MAX_CONTENT:
            body = body[:_MAX_CONTENT] + "\n… (truncated)"

        payload: Dict[str, Any] = {
            "embeds": [{
                "title": (title or "Notification")[:256],
                "description": body,
                "color": 0x5865F2,
            }]
        }

        # Actions cannot be interactive buttons without a registered application,
        # so they are appended as text rather than silently dropped.
        # 沒有註冊應用程式就無法做互動按鈕，故將動作以文字附加而非靜默丟棄。
        if actions:
            labels = ", ".join(a.get("label", a.get("action", "")) for a in actions)
            if labels:
                payload["embeds"][0]["footer"] = {"text": f"Actions: {labels}"[:2048]}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self.webhook_url, json=payload)
            if response.status_code >= 400:
                logger.error(
                    "DiscordAdapter: webhook returned %s: %s",
                    response.status_code, response.text[:200],
                )
                return False
            return True
        except Exception as exc:
            logger.error("DiscordAdapter: send failed: %s", exc)
            return False

    async def handle_webhook(self, payload: Any, headers: Dict[str, Any] = None) -> Any:
        return None
