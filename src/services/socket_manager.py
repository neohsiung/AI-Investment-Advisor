from fastapi import WebSocket
from typing import List, Dict
import json
import asyncio
from src.utils.logger import setup_logger

logger = setup_logger("SocketManager")

class ConnectionManager:
    """
    Manages active WebSocket connections by user_id.
    管理依據使用者 ID 分類的活躍 WebSocket 連線。
    """
    def __init__(self):
        # user_id -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.interaction_service = None

    def set_interaction_service(self, service):
        """Registers the InteractionService for bidirectional communication."""
        self.interaction_service = service


    async def connect(self, websocket: WebSocket, user_id: str):
        """Accepts a connection and registers it for the user."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"User {user_id} connected. Active connections: {len(self.active_connections[user_id])}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        """Removes a connection from the user's active list."""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"User {user_id} disconnected.")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Sends a JSON message to a specific socket."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def broadcast_to_user(self, user_id: str, message: dict):
        """Broadcasts a JSON message to all active sockets for a specific user."""
        if user_id not in self.active_connections:
            return

        dead_connections = []
        for connection in self.active_connections[user_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Broadcast error for user {user_id}: {e}")
                dead_connections.append(connection)

        # Cleanup dead connections
        for dead in dead_connections:
            self.disconnect(dead, user_id)

    async def handle_command(self, user_id: str, data: dict):
        """Processes incoming commands from the user via WebSocket."""
        cmd_type = data.get("type")
        payload = data.get("payload", {})
        
        logger.info(f"Received command {cmd_type} from user {user_id}")
        
        if cmd_type == "EXECUTE_ORDER":
            # Manual trade execution from UI
            from src.services.automated_trading_service import AutomatedTradingService
            trading_svc = AutomatedTradingService()
            
            ticker = payload.get("ticker", "").upper()
            action = payload.get("action", "").upper()
            quantity = float(payload.get("quantity", 0))
            
            result = await trading_svc.evaluate_and_execute_trade(
                user_id=user_id,
                ticker=ticker,
                action=action,
                quantity=quantity,
                confidence_score=10, # Manual override
                rationale="[MANUAL] Dashboard Terminal Order"
            )
            
            # Send result back via WS
            await self.broadcast_to_user(user_id, {
                "type": "TRADE_RESULT",
                "payload": result
            })
            
        elif cmd_type == "REPLY_APPROVAL":
            # Response to an AI-triggered approval request
            if self.interaction_service:
                request_id = payload.get("request_id")
                action = payload.get("action") # "approve" or "reject"
                
                await self.interaction_service.handle_response(request_id, action)
            else:
                logger.error("InteractionService not registered in SocketManager.")


socket_manager = ConnectionManager()

