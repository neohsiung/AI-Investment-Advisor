import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta

from src.data.database import BaseRepository, get_db_engine
from sqlalchemy import text

logger = logging.getLogger("CognitiveMemoryManager")

class CognitiveMemoryManager:
    """
    Rule #8: Cognitive Memory Tiering.
    認知記憶管理器：實作三階層記憶架構。
    
    Tiers:
    1. Short (Fast): Redis / In-memory (Ticks/Events)
    2. Medium (Structured): PostgreSQL (Insights/Convictions)
    3. Long (Cold): File-based / Compressed (Archives)
    """

    def __init__(self, user_id: str):
        # 1. Base Directory Setup (Rule #8 Security - Path Hardening)
        # 確保路徑為絕對路徑且位於 data/memory 內，防止 Path Traversal。
        try:
            project_root = Path(__file__).parent.parent.parent.resolve()
            base_dir = (project_root / "data" / "memory").resolve()
        except Exception:
            # Fallback to relative if resolving fails in specific environments
            base_dir = Path("data/memory").resolve()

        # 2. Sanitize user_id
        safe_user_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(user_id or "default"))
        if not safe_user_id: safe_user_id = "default"
        
        self.user_id = user_id
        self.engine = get_db_engine()

        # 3. Path Construction with Boundary Shield
        lt_path = (base_dir / "long_term" / safe_user_id).resolve()
        if not str(lt_path).startswith(str(base_dir)):
            logger.error(f"Security Alert: Attempted path traversal for user_id={user_id}")
            raise PermissionError("Access denied: Invalid path construction.")
        
        self.long_term_path = lt_path
        self.long_term_path.mkdir(parents=True, exist_ok=True)
        
        # [Task 8.3] Runtime DB Resilience
        self._db_available = self._check_db_health()
        if not self._db_available:
            logger.warning(f"CognitiveMemoryManager ({user_id}): PostgreSQL unavailable. Falling back to local storage.")
            fb_path = (base_dir / "medium_term_fallback" / safe_user_id).resolve()
            if not str(fb_path).startswith(str(base_dir)):
                raise PermissionError("Access denied: Invalid path construction.")
            self.fallback_path = fb_path
            self.fallback_path.mkdir(parents=True, exist_ok=True)

    def _check_db_health(self) -> bool:
        """Checks if the database is reachable."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                return True
        except Exception:
            return False

    # ──────────────────────────────────────────
    # Storage API (with SQL -> File Fallback)
    # ──────────────────────────────────────────

    def store_insight(self, agent_name: str, memory_type: str, content: Dict[str, Any], importance: float = 0.5, source_id: str = None):
        """
        Stores a distilled insight. Falls back to local JSON if DB is offline.
        """
        if self._db_available:
            sql = """
            INSERT INTO cognitive_memories (user_id, agent_name, memory_type, content, importance, source_id)
            VALUES (:user_id, :agent_name, :memory_type, :content, :importance, :source_id)
            """
            try:
                with self.engine.begin() as conn:
                    conn.execute(text(sql), {
                        "user_id": self.user_id,
                        "agent_name": agent_name,
                        "memory_type": memory_type,
                        "content": json.dumps(content, ensure_ascii=False),
                        "importance": importance,
                        "source_id": source_id
                    })
                logger.info(f"Stored {memory_type} memory for agent {agent_name} to DB.")
                return
            except Exception as e:
                logger.error(f"Failed to store memory to DB, trying fallback: {e}")
                self._db_available = False # Mark as unavailable for this session

        # Fallback to Local File
        try:
            filename = f"{memory_type}_{datetime.now().timestamp()}.json"
            filepath = self.fallback_path / filename
            memory_data = {
                "user_id": self.user_id,
                "agent_name": agent_name,
                "memory_type": memory_type,
                "content": content,
                "importance": importance,
                "source_id": source_id,
                "created_at": datetime.now().isoformat()
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Stored {memory_type} memory to local fallback: {filepath}")
        except Exception as e:
            logger.error(f"CRITICAL: Resource exhausted - Fallback storage also failed: {e}")

    def get_recent_memories(self, limit: int = 10, memory_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves recent distilled memories. Falls back to local storage if DB is offline.
        """
        if self._db_available:
            sql = """
            SELECT agent_name, memory_type, content, importance, created_at 
            FROM cognitive_memories 
            WHERE user_id = :user_id
            """
            params = {"user_id": self.user_id, "limit": limit}
            if memory_type:
                sql += " AND memory_type = :memory_type"
                params["memory_type"] = memory_type
            
            sql += " ORDER BY created_at DESC LIMIT :limit"
            
            try:
                with self.engine.connect() as conn:
                    result = conn.execute(text(sql), params).fetchall()
                    return [
                        {
                            "agent_name": row[0],
                            "memory_type": row[1],
                            "content": json.loads(row[2]) if isinstance(row[2], str) else row[2],
                            "importance": float(row[3]),
                            "created_at": row[4].isoformat() if hasattr(row[4], 'isoformat') else str(row[4])
                        }
                        for row in result
                    ]
            except Exception as e:
                logger.error(f"Failed to retrieve from DB, trying fallback: {e}")
                self._db_available = False

        # Fallback: Scrape local files
        try:
            memories = []
            if not self.fallback_path.exists():
                return []
                
            for file in sorted(self.fallback_path.glob("*.json"), key=os.path.getmtime, reverse=True):
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if memory_type and data.get("memory_type") != memory_type:
                        continue
                    memories.append(data)
                if len(memories) >= limit:
                    break
            return memories
        except Exception as e:
            logger.error(f"Fallback retrieval failed: {e}")
            return []

    # ──────────────────────────────────────────
    # Long-Term Storage (Files)
    # ──────────────────────────────────────────

    def archive_to_long_term(self, days_old: int = 30) -> int:
        """
        Archives old medium-term memories to long-term storage (Vector DB).
        將舊的中階記憶歸檔至長階向量儲存 (pgvector)。
        """
        if not self._db_available:
            logger.warning("CognitiveMemoryManager: DB unavailable, skipping archival.")
            return 0
            
        from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
        from src.services.settings_service import SettingsService
        from src.domain.interfaces import LLMConfig
        from src.repositories.vector_repository import AlchemyVectorRepository
        
        try:
            cutoff = datetime.now() - timedelta(days=days_old)
            with self.engine.begin() as conn:
                # 1. Query old records
                query = text("""
                    SELECT id, agent_name, memory_type, content, importance, source_id, created_at
                    FROM cognitive_memories
                    WHERE user_id = :uid AND created_at < :cutoff
                """)
                rows = conn.execute(query, {"uid": self.user_id, "cutoff": cutoff}).fetchall()
                
            if not rows:
                logger.info(f"CognitiveMemoryManager: No memories older than {days_old} days to archive.")
                return 0

            # 2. Get LLM Settings for Embeddings
            settings = SettingsService(user_id=self.user_id).get_all_settings()
            provider = settings.get("AI_PROVIDER", "Google Gemini")
            model = settings.get("AI_MODEL_SMART", "gemini-1.5-pro")
            api_key = settings.get("API_KEY", "")
            
            if provider.lower() == "openai":
                model = "text-embedding-3-small"
                
            llm_config = LLMConfig(provider=provider, model=model, api_key=api_key)
            gateway = LLMGatewayFactory.create(provider)
            vector_repo = AlchemyVectorRepository(engine=self.engine)
            
            archived_count = 0
            to_delete_ids = []
            
            for row in rows:
                try:
                    content_dict = json.loads(row.content) if isinstance(row.content, str) else row.content
                    text_to_embed = f"[{row.memory_type}] {row.agent_name}: {json.dumps(content_dict, ensure_ascii=False)}"
                    
                    # 3. Generate Embedding (Use fallback zero vector if API fails)
                    try:
                        embedding = gateway.embed(text_to_embed, llm_config)
                    except Exception as e:
                        logger.warning(f"Embedding failed, using zero vector: {e}")
                        embedding = [0.0] * 1536
                    
                    # 4. Store in Vector DB
                    metadata = {"agent_name": row.agent_name, "memory_type": row.memory_type, "importance": row.importance, "source_id": row.source_id, "archived_from": str(row.created_at)}
                    vector_repo.add_memory(self.user_id, "archive", text_to_embed, embedding, metadata)
                    
                    to_delete_ids.append(row.id)
                    archived_count += 1
                except Exception as e:
                    logger.error(f"Error archiving memory ID {row.id}: {e}")
                    
            # 5. Purge archived records
            if to_delete_ids:
                with self.engine.begin() as conn:
                    delete_query = text("DELETE FROM cognitive_memories WHERE id IN :ids")
                    conn.execute(delete_query, {"ids": tuple(to_delete_ids)})
                    
            logger.info(f"CognitiveMemoryManager: Successfully archived {archived_count} old memories to Vector DB.")
            return archived_count
            
        except Exception as e:
            logger.error(f"archive_to_long_term failed: {e}")
            return 0

    async def distill_conversation(self, channel_id: str) -> str:
        """
        Distills short-term conversation into structured knowledge (DIKW Phase 2).
        將短期對話蒸餾為結構化知識。
        """
        from src.infrastructure.memory.channel_memory_manager import ChannelMemoryManager
        from src.services.settings_service import SettingsService
        from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
        from src.domain.interfaces import Message, LLMConfig
        from src.utils.async_utils import to_thread

        # 1. Fetch STM
        memory = ChannelMemoryManager()
        history = memory.get_short_term_as_messages(channel_id, limit=50)
        if len(history) < 5:
            return "Too short for significant distillation."

        # 2. Prepare Distillation Prompt
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history])
        prompt = f"""Summarize the following investment conversation into a concise knowledge entry.
         Focus on:
         - User preferences / risk tolerance
         - Symbols of interest
         - Key decisions or conclusions
         
         Conversation:
         {history_text}
         
         Output format: Brief, bulleted summary only."""

        # 3. Call Smart Model
        settings = SettingsService(user_id=self.user_id)
        config_data = settings.get_all_settings()
        
        provider = config_data.get("AI_PROVIDER", "Google Gemini")
        model = config_data.get("AI_MODEL_SMART", "gemini-1.5-pro")
        api_key = config_data.get("API_KEY", "")

        gateway = LLMGatewayFactory.create(provider)
        llm_config = LLMConfig(
            provider=provider, model=model, api_key=api_key, 
            temperature=0.3, max_tokens=1000
        )
        messages = [
            Message(role="system", content="You are a context distillation specialist."),
            Message(role="user", content=prompt)
        ]

        try:
            summary = await gateway.chat(messages, llm_config)
            
            # 4. Store as Knowledge (Medium-Term)
            self.store_insight(
                agent_name="CognitiveMemoryManager",
                memory_type="distilled_conversation",
                content={"summary": summary, "channel_id": channel_id},
                importance=0.7,
                source_id=channel_id
            )
            
            # 5. Clear STM (Keep last 3 messages for immediate continuity)
            # memory.prune_short_term(channel_id, keep_last=3)
            # For now, we'll just log it. PRUNING logic needs to be safe.
            logger.info(f"Distilled conversation for {channel_id} into knowledge.")
            
            return summary
        except Exception as e:
            logger.error(f"Distillation error: {e}")
            return f"Error during distillation: {e}"

    def search_historical_context(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Pillar 3: Active RAG Retrieval
        主動檢索長階記憶庫中的相關脈絡。
        """
        if not self._db_available:
            return []
            
        from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
        from src.services.settings_service import SettingsService
        from src.domain.interfaces import LLMConfig
        from src.repositories.vector_repository import AlchemyVectorRepository
        
        settings = SettingsService(user_id=self.user_id).get_all_settings()
        provider = settings.get("AI_PROVIDER", "Google Gemini")
        model = settings.get("AI_MODEL_SMART", "gemini-1.5-pro")
        api_key = settings.get("API_KEY", "")
        if provider.lower() == "openai":
            model = "text-embedding-3-small"
            
        llm_config = LLMConfig(provider=provider, model=model, api_key=api_key)
        gateway = LLMGatewayFactory.create(provider)
        vector_repo = AlchemyVectorRepository(engine=self.engine)
        
        try:
            # Generate query embedding — gateway.embed is async, run it safely from sync context
            import asyncio
            async def _do_embed():
                return await gateway.embed(query, llm_config)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            embedding = loop.run_until_complete(_do_embed())
            
            # Search PGVector
            results = vector_repo.search_memory(self.user_id, embedding=embedding, query_text=query, top_k=limit)
            return results
        except Exception as e:
            logger.error(f"search_historical_context failed: {e}")
            return []

    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Semantic search across tiers. Combines Medium and Long-term search.
        跨層級語義搜索。整合中短期與長期語義檢索。
        """
        recent = self.get_recent_memories(limit=3)
        historical = self.search_historical_context(query, limit=2)
        
        combined = []
        for r in recent:
            combined.append({"source": "Medium-Term", "content": r["content"], "date": r["created_at"], "agent": r.get("agent_name")})
            
        for h in historical:
            combined.append({"source": "Long-Term", "content": h["content"], "score": h.get("final_score")})
            
        return combined
