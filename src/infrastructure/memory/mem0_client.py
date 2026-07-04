"""
Mem0 Memory Service — 統一 Agent 記憶介面
所有 Agent 共享記憶空間，以 user_id / agent_id 區分來源

Usage:
    svc = Mem0MemoryService()
    await svc.remember("CIO reduced TSLA weight", user_id="advisor", agent_id="CIO")
    memories = await svc.recall("TSLA strategy", user_id="advisor")
"""
import os
import logging
from mem0 import Memory

logger = logging.getLogger(__name__)


class Mem0MemoryService:
    """Embedded mem0 memory service — no external API server needed.

    Uses Ollama for embeddings (nomic-embed-text) and LLM (gemma3:4b),
    and Qdrant local for vector storage. All data persists in a Docker volume.
    """

    def __init__(self, ollama_base_url: str | None = None):
        ollama_host = ollama_base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
        )
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "pad_memories",
                    "path": "/workspace/data/mem0_qdrant",
                    "embedding_model_dims": 768,  # nomic-embed-text
                },
            },
            "llm": {
                "provider": "ollama",
                "config": {
                    "model": "gemma3:4b",
                    "ollama_base_url": ollama_host,
                    "temperature": 0.1,
                },
            },
            "embedder": {
                "provider": "ollama",
                "config": {
                    "model": "nomic-embed-text",
                    "ollama_base_url": ollama_host,
                    "embedding_dims": 768,
                },
            },
            "version": "v1.1",
        }
        self.memory = Memory.from_config(config)

    async def remember(
        self,
        content: str,
        user_id: str,
        agent_id: str | None = None,
        metadata: dict | None = None,
        infer: bool = False,
    ) -> dict:
        """寫入記憶 — Agent 執行後調用
        infer=False: 跳過 LLM 處理，只做 embedding 儲存（更快）
        """
        messages = [
            {"role": "user", "content": content}
        ]
        return self.memory.add(
            messages,
            user_id=user_id,
            agent_id=agent_id,
            metadata=metadata or {},
            infer=infer,
        )

    async def recall(
        self,
        query: str,
        user_id: str,
        agent_id: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """搜尋相關記憶 — Agent 執行前調用
        
        兼容 mem0 v2.0.6 回傳格式：
        - v2.0.0-2.0.5: list[dict] with "memory" key
        - v2.0.6+: list[str] (純記憶體字串)
        - 檢索失敗：空列表 []
        """
        filters = {"user_id": user_id}
        if agent_id:
            filters["agent_id"] = agent_id
        results = self.memory.search(
            query,
            filters=filters,
            top_k=limit,
        )
        # 處理空結果
        if not results:
            return []
        
        # 兼容不同版本的 mem0 API
        first_item = results[0] if isinstance(results, list) else results
        if isinstance(first_item, str):
            # v2.0.6+ returns list of strings
            return [{"memory": r, "type": "text"} for r in results]
        # v2.0.0-2.0.5 returns list of dicts
        return results

    async def get_all(
        self, user_id: str, agent_id: str | None = None
    ) -> list[dict]:
        """取得所有記憶"""
        filters = {"user_id": user_id}
        if agent_id:
            filters["agent_id"] = agent_id
        return self.memory.get_all(filters=filters)

    async def delete(self, memory_id: str) -> bool:
        """刪除指定記憶"""
        return self.memory.delete(memory_id)

    async def update(
        self, memory_id: str, data: str, metadata: dict | None = None
    ) -> dict:
        """更新指定記憶"""
        return self.memory.update(memory_id, data, metadata=metadata)