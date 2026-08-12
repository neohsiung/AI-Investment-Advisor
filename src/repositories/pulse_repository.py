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
        self.redis: Optional[Any] = None

        # 2026-08-10: the constructor used to build an unclosed async Redis
        # client whenever CELERY_BROKER_URL was set. docker-compose.prod.yml
        # has never set that variable (only REDIS_URL), so the branch was dead
        # and this class has always run on the in-memory fallback. That was a
        # landmine rather than a live bug: AsyncPulseRepository is constructed
        # per agent tool call (agent_loop.py) and per chat request (chat.py),
        # so setting the variable would have leaked one client per invocation
        # — worse than the /health leak that caused the 2026-08-10 outage.
        #
        # The leaky construction is removed. Redis-backed pulses stay OFF:
        # switching a never-exercised path on mid-incident is a separate,
        # deliberate change. To enable it later, wire self.redis to
        # src.infrastructure.cache.redis_client.get_redis() (async, shared
        # pool) and set _use_redis — every use below is awaited.
        #
        # 2026-08-10：原建構子在 CELERY_BROKER_URL 有值時會建立從不關閉的 async
        # client，但該變數在 prod 從未設定，此分支等同死碼，一直走記憶體 fallback。
        # 這是地雷而非現行 bug：一旦設了該變數，每次 agent tool 呼叫就洩漏一條。
        # 現移除洩漏來源，並「維持」Redis 路徑關閉——在事故處理中打開從未驗證過的
        # 路徑是另一個獨立決定。日後要啟用，請接上共用連線池的 get_redis()。

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
