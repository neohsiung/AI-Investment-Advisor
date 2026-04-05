"""
Pulse Repository — Agent Real-Time State Tracking.
Stores the last heartbeat and 'current_task' of every active agent.
"""
from typing import Dict, Any, Optional
import time
import json

class AsyncPulseRepository:
    """
    Tracks the active state and heartbeats of agents.
    Uses Redis directly if available for real-time ephemeral tracking, 
    otherwise falls back to in-memory dictionary.
    """
    
    def __init__(self):
        self._fallback_dict: Dict[str, Dict[str, Any]] = {}
        self._use_redis = False
        
        import os
        redis_url = os.getenv("CELERY_BROKER_URL") 
        if redis_url and "redis" in redis_url:
            try:
                import redis.asyncio as aioredis
                self.redis = aioredis.from_url(redis_url, decode_responses=True)
                self._use_redis = True
            except ImportError:
                pass

    async def update_pulse(self, agent_name: str, task: str = "Idle", metadata: Optional[Dict[str, Any]] = None) -> None:
        """Updates the heartbeat and current state of an agent."""
        timestamp = time.time()
        payload = {
            "agent": agent_name,
            "task": task,
            "last_heartbeat": timestamp,
            "metadata": metadata or {}
        }
        
        if self._use_redis:
            await self.redis.hset("agent_pulses", agent_name, json.dumps(payload))
        else:
            self._fallback_dict[agent_name] = payload

    def update_pulse_sync(self, agent_name: str, task: str = "Idle", metadata: Optional[Dict[str, Any]] = None) -> None:
        """Updates the heartbeat and current state of an agent (Synchronous version)."""
        timestamp = time.time()
        payload = {
            "agent": agent_name,
            "task": task,
            "last_heartbeat": timestamp,
            "metadata": metadata or {}
        }
        
        if self._use_redis:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.redis.hset("agent_pulses", agent_name, json.dumps(payload)))
            except RuntimeError:
                asyncio.run(self.redis.hset("agent_pulses", agent_name, json.dumps(payload)))
        else:
            self._fallback_dict[agent_name] = payload

    async def get_all_pulses(self) -> Dict[str, Dict[str, Any]]:
        """Retrieves the state of all agents."""
        if self._use_redis:
            raw_data = await self.redis.hgetall("agent_pulses")
            return {k: json.loads(v) for k, v in raw_data.items()}
        return self._fallback_dict

    async def get_pulse(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves the state for a specific agent."""
        if self._use_redis:
            raw = await self.redis.hget("agent_pulses", agent_name)
            return json.loads(raw) if raw else None
        return self._fallback_dict.get(agent_name)
