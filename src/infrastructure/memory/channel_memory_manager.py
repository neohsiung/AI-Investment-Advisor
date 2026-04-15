"""
Channel Memory Manager — Redis Short-Term + pgvector Long-Term.
頻道記憶管理器 — Redis 短期記憶 + pgvector 長期記憶。

Implements per-channel conversational memory:
  - Short-Term Memory (STM): Redis-backed rolling window of recent messages.
  - Long-Term Memory (LTM): pgvector-backed semantic storage via HybridMemory.
  - Compaction: LLM-summarized short-term context → long-term storage.

Design decisions:
  - Redis STM survives process restarts (user decision)
  - STM stored as Redis List per channel_id with TTL
  - LTM uses existing HybridMemory/memory_embeddings table with source_type metadata
  - Compaction trigger: every N messages (configurable)

遵循規範:
  - 規範一 (Clean Architecture): 依賴注入，不直接實例化 infra
  - 規範四 (模組化設計): STM/LTM 可獨立替換
  - 規範十五 (AI-Support First): 標準化介面
"""

import os
import json
import time
import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
STM_MAX_MESSAGES = int(os.getenv("CHANNEL_STM_MAX_MESSAGES", "20"))
STM_TTL_SECONDS = int(os.getenv("CHANNEL_STM_TTL_SECONDS", str(60 * 60 * 4)))  # 4 hours
COMPACTION_THRESHOLD = int(os.getenv("CHANNEL_COMPACTION_THRESHOLD", "20"))


@dataclass
class ChannelMessage:
    """Single message in channel conversation."""
    role: str          # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    channel_type: str = ""   # "telegram" | "line"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ChannelMessage":
        return ChannelMessage(**data)

    def to_openai_message(self) -> Dict[str, str]:
        """Convert to OpenAI-compatible message format."""
        return {"role": self.role, "content": self.content}


class RedisSTMStore:
    """
    Redis-backed Short-Term Memory store.
    Redis 支援的短期記憶存儲。

    Uses Redis List per channel_id with automatic TTL and LTRIM.
    """

    def __init__(self, redis_url: str = None, max_messages: int = None, ttl: int = None):
        self._redis_url = redis_url or REDIS_URL
        self._max_messages = max_messages or STM_MAX_MESSAGES
        self._ttl = ttl or STM_TTL_SECONDS
        self._redis = None

    def _get_redis(self):
        """Lazy-init Redis connection."""
        if self._redis is None:
            try:
                import redis as redis_lib
                self._redis = redis_lib.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=3,
                )
                self._redis.ping()
                logger.info(f"RedisSTMStore: Connected to {self._redis_url}")
            except Exception as e:
                logger.warning(
                    f"RedisSTMStore: Redis unavailable ({e}). "
                    f"Falling back to in-process dict."
                )
                self._redis = None
        return self._redis

    def _key(self, channel_id: str) -> str:
        return f"stm:{channel_id}"

    def _meta_key(self, channel_id: str) -> str:
        return f"stm_meta:{channel_id}"

    def set_metadata(self, channel_id: str, key: str, value: Any) -> None:
        """Set a metadata value for a channel."""
        mkey = self._meta_key(channel_id)
        r = self._get_redis()
        if r:
            try:
                # Use HSET to store key-value pairs
                r.hset(mkey, key, json.dumps(value, ensure_ascii=False))
                r.expire(mkey, self._ttl)
                return
            except Exception as e:
                logger.error(f"RedisSTMStore: set_metadata failed: {e}")

        # Fallback
        if mkey not in self._fallback_meta:
            self._fallback_meta[mkey] = {}
        self._fallback_meta[mkey][key] = json.dumps(value, ensure_ascii=False)

    def get_metadata(self, channel_id: str, key: str) -> Optional[Any]:
        """Get a metadata value for a channel."""
        mkey = self._meta_key(channel_id)
        r = self._get_redis()
        if r:
            try:
                val = r.hget(mkey, key)
                return json.loads(val) if val else None
            except Exception as e:
                logger.error(f"RedisSTMStore: get_metadata failed: {e}")

        # Fallback
        raw = self._fallback_meta.get(mkey, {}).get(key)
        return json.loads(raw) if raw else None

    def delete_metadata(self, channel_id: str, key: str) -> None:
        """Delete a metadata value for a channel."""
        mkey = self._meta_key(channel_id)
        r = self._get_redis()
        if r:
            try:
                r.hdel(mkey, key)
                return
            except Exception as e:
                logger.error(f"RedisSTMStore: delete_metadata failed: {e}")

        # Fallback
        if mkey in self._fallback_meta:
            self._fallback_meta[mkey].pop(key, None)

    # ── Fallback in-process store ────────────────────────────
    _fallback: Dict[str, List[str]] = {}
    _fallback_meta: Dict[str, Dict[str, str]] = {}

    def append(self, channel_id: str, message: ChannelMessage) -> None:
        """Append a message to the channel's STM."""
        key = self._key(channel_id)
        msg_json = json.dumps(message.to_dict(), ensure_ascii=False)

        r = self._get_redis()
        if r:
            try:
                r.rpush(key, msg_json)
                r.ltrim(key, -self._max_messages, -1)  # Keep last N
                r.expire(key, self._ttl)
                return
            except Exception as e:
                logger.error(f"RedisSTMStore: append failed: {e}")

        # Fallback
        if key not in self._fallback:
            self._fallback[key] = []
        self._fallback[key].append(msg_json)
        # Trim
        if len(self._fallback[key]) > self._max_messages:
            self._fallback[key] = self._fallback[key][-self._max_messages:]

    def get_recent(self, channel_id: str, limit: int = 10) -> List[ChannelMessage]:
        """Get the most recent messages for a channel."""
        key = self._key(channel_id)

        r = self._get_redis()
        if r:
            try:
                raw_list = r.lrange(key, -limit, -1)
                return [
                    ChannelMessage.from_dict(json.loads(item))
                    for item in raw_list
                ]
            except Exception as e:
                logger.error(f"RedisSTMStore: get_recent failed: {e}")

        # Fallback
        raw = self._fallback.get(key, [])
        return [
            ChannelMessage.from_dict(json.loads(item))
            for item in raw[-limit:]
        ]

    def count(self, channel_id: str) -> int:
        """Get number of messages in STM for a channel."""
        key = self._key(channel_id)

        r = self._get_redis()
        if r:
            try:
                return r.llen(key)
            except Exception:
                pass  # nosec B110

        return len(self._fallback.get(key, []))

    def clear(self, channel_id: str) -> None:
        """Clear all STM for a channel (after compaction)."""
        key = self._key(channel_id)

        r = self._get_redis()
        if r:
            try:
                r.delete(key)
                return
            except Exception:
                pass  # nosec B110

        self._fallback.pop(key, None)

    def get_all_and_clear(self, channel_id: str) -> List[ChannelMessage]:
        """Atomically get all messages and clear (for compaction)."""
        key = self._key(channel_id)

        r = self._get_redis()
        if r:
            try:
                pipe = r.pipeline()
                pipe.lrange(key, 0, -1)
                pipe.delete(key)
                results = pipe.execute()
                raw_list = results[0]
                return [
                    ChannelMessage.from_dict(json.loads(item))
                    for item in raw_list
                ]
            except Exception as e:
                logger.error(f"RedisSTMStore: get_all_and_clear failed: {e}")

        # Fallback
        raw = self._fallback.pop(key, [])
        return [
            ChannelMessage.from_dict(json.loads(item))
            for item in raw
        ]


class ChannelMemoryManager:
    """
    Per-channel conversational memory with Redis STM + pgvector LTM.
    每頻道對話記憶管理器，Redis 短期記憶 + pgvector 長期記憶。

    Usage:
        cm = ChannelMemoryManager(long_term_memory=hybrid_memory)
        cm.append_short_term("tg_123", "user", "NVDA 怎麼看？")
        recent = cm.get_short_term("tg_123", limit=5)
        relevant = cm.search_long_term("NVDA analysis", user_id="u1")
    """

    def __init__(
        self,
        stm_store: RedisSTMStore = None,
        long_term_memory=None,
        compaction_threshold: int = None,
        cognitive_engine=None,
    ):
        self._stm = stm_store or RedisSTMStore()
        self._ltm = long_term_memory  # HybridMemory instance
        self._compaction_threshold = compaction_threshold or COMPACTION_THRESHOLD
        # [Cognitive Architecture] DIKW distillation engine
        # 認知架構: DIKW 蒸餾引擎
        self._cognitive = cognitive_engine  # CognitiveMemoryManager or None

    def set_metadata(self, channel_id: str, key: str, value: Any) -> None:
        """Set arbitrary metadata for a channel."""
        self._stm.set_metadata(channel_id, key, value)

    def get_metadata(self, channel_id: str, key: str) -> Optional[Any]:
        """Get arbitrary metadata for a channel."""
        return self._stm.get_metadata(channel_id, key)

    def delete_metadata(self, channel_id: str, key: str) -> None:
        """Delete arbitrary metadata for a channel."""
        self._stm.delete_metadata(channel_id, key)

    # ── Short-Term Memory API ────────────────────────────────

    def get_short_term(
        self, channel_id: str, limit: int = 10
    ) -> List[ChannelMessage]:
        """
        Get recent conversation messages for this channel.
        取得此頻道的最近對話訊息。
        """
        return self._stm.get_recent(channel_id, limit=limit)

    def get_short_term_as_messages(
        self, channel_id: str, limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        Get recent messages in OpenAI-compatible format.
        取得最近訊息（OpenAI 相容格式）。
        """
        msgs = self._stm.get_recent(channel_id, limit=limit)
        return [m.to_openai_message() for m in msgs]

    def append_short_term(
        self,
        channel_id: str,
        role: str,
        content: str,
        channel_type: str = "",
    ) -> None:
        """
        Append a message, auto-evict oldest if over limit.
        新增訊息，超過上限時自動淘汰最舊的。
        """
        msg = ChannelMessage(
            role=role,
            content=content,
            channel_type=channel_type,
        )
        self._stm.append(channel_id, msg)

    # ── Long-Term Memory API ─────────────────────────────────

    def search_long_term(
        self,
        query: str,
        user_id: str,
        limit: int = 5,
    ) -> List[Dict]:
        """
        Semantic search across all stored conversations.
        在所有已存對話中進行語意搜尋。
        """
        if not self._ltm:
            return []

        try:
            results = self._ltm.search(
                query_text=query,
                user_id=user_id,
                limit=limit,
            )
            return results
        except Exception as e:
            logger.error(f"ChannelMemoryManager: LTM search error: {e}")
            return []

    # ── Compaction (STM → LTM) ───────────────────────────────

    def should_compact(self, channel_id: str) -> bool:
        """Check if short-term buffer should be compacted to long-term."""
        return self._stm.count(channel_id) >= self._compaction_threshold

    async def compact_to_long_term(
        self,
        channel_id: str,
        user_id: str,
    ) -> Optional[str]:
        """
        Summarize and store short-term context into long-term memory.
        摘要短期上下文並存入長期記憶。

        Uses LLM to generate a summary, then stores in pgvector.
        Returns the memory_id if successful.
        """
        if not self._ltm:
            logger.warning(
                "ChannelMemoryManager: No LTM configured, skipping compaction"
            )
            return None

        # [Cognitive Architecture] Use DIKW engine if available
        # 認知架構: 優先使用 DIKW 引擎
        if self._cognitive:
            try:
                return await self._cognitive.compact_stm_to_episodic(
                    channel_id, user_id
                )
            except Exception as e:
                logger.error(
                    f"ChannelMemoryManager: Cognitive compaction failed, "
                    f"falling back to simple: {e}"
                )

        # Fallback: simple summarization (original behavior)
        messages = self._stm.get_all_and_clear(channel_id)
        if not messages:
            return None

        # Build conversation transcript
        transcript = "\n".join(
            [f"[{m.role}] {m.content}" for m in messages]
        )

        # Summarize using LLM (lazy import to avoid circular deps)
        summary = await self._summarize_conversation(transcript, user_id=user_id)

        # Store in LTM
        memory_id = str(uuid.uuid4())
        try:
            self._ltm.add_memory(
                memory_id=memory_id,
                user_id=user_id,
                content=summary,
                metadata={
                    "source_type": "channel_conversation",
                    "memory_tier": "episodic",
                    "channel_id": channel_id,
                    "message_count": len(messages),
                    "compacted_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(
                f"ChannelMemoryManager: Compacted {len(messages)} messages "
                f"from {channel_id} → memory {memory_id}"
            )
            return memory_id
        except Exception as e:
            logger.error(
                f"ChannelMemoryManager: Compaction storage failed: {e}"
            )
            return None

    async def _summarize_conversation(self, transcript: str, user_id: str = None) -> str:
        """
        Use a fast-tier LLM to summarize conversation transcript.
        使用快速 LLM 摘要對話記錄。
        """
        try:
            from src.agents.factory import AgentFactory

            summarizer = AgentFactory.create_agent(
                "Sentiment",
                tier="nano",
                user_id=user_id,
                use_cache=True,
            )

            prompt = (
                "請將以下對話精華摘要成 2-3 句話，保留關鍵投資決策、"
                "提到的標的和市場觀點。只回傳摘要文字：\n\n"
                f"{transcript[:2000]}"  # Truncate to avoid token limits
            )

            result = summarizer.run({"user_request": prompt})
            if isinstance(result, dict):
                return str(result.get("content") or result.get("output") or result)
            return str(result)
        except Exception as e:
            logger.error(f"Conversation summarization failed: {e}")
            # Fallback: store truncated raw transcript
            return f"[Raw Transcript] {transcript[:500]}"

    # ── Cognitive Architecture Extensions ─────────────────

    def get_wisdom_context(self, user_id: str) -> str:
        """
        Get wisdom summary for system prompt injection.
        取得智慧摘要供 system prompt 注入。

        Delegates to CognitiveMemoryManager.prime_with_wisdom().
        """
        if self._cognitive:
            return self._cognitive.prime_with_wisdom(user_id)
        return ""

    async def trigger_distillation(self, user_id: str) -> Dict:
        """
        Trigger I→K and K→W distillation (if thresholds met).
        觸發 I→K 和 K→W 蒸餾（如達門檻）。

        Typically called by a scheduled job or after multiple compactions.
        """
        if not self._cognitive:
            return {"knowledge_ids": [], "wisdom_count": 0}

        knowledge_ids = await self._cognitive.distill_episodic_to_knowledge(
            user_id
        )
        wisdom_count = await self._cognitive.crystallize_knowledge_to_wisdom(
            user_id
        )
        return {
            "knowledge_ids": knowledge_ids,
            "wisdom_count": wisdom_count,
        }

