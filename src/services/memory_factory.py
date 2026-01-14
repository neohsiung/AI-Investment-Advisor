import os
import logging
from src.services.memory_service import MemoryService
from src.data.memory_repository import SqliteMemoryRepository
from src.data.redis_memory_repository import RedisMemoryRepository
from src.infrastructure.agent_llm_provider import AgentLLMProvider

logger = logging.getLogger(__name__)

class MemoryFactory:
    """
    Factory to create MemoryService instances.
    Selects backend based on 'MEMORY_BACKEND' env var ('redis' or 'sqlite').
    """
    
    @staticmethod
    def create_memory_service(user_id: str = None) -> MemoryService:
        backend = os.getenv("MEMORY_BACKEND", "sqlite").lower()
        
        # 1. Select Repository
        if backend == "redis":
            redis_url = os.getenv("REDIS_URL")
            logger.info(f"Initializing MemoryService with REDIS backend at {redis_url}")
            repo = RedisMemoryRepository(redis_url)
        else:
            logger.info("Initializing MemoryService with SQLITE backend.")
            repo = SqliteMemoryRepository()
            
        # 2. Select LLM Provider (Shared)
        # In production, this might also be an interface to a specialized Microservice
        # For now, we use the AgentLLMProvider which uses our Agents for summarization.
        llm_provider = AgentLLMProvider(user_id=user_id)
        
        return MemoryService(repository=repo, llm_provider=llm_provider)
