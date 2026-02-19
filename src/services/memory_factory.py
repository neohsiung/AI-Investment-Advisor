import os
import logging
from src.services.memory_service import MemoryService
from src.repositories.memory_repository import AlchemyMemoryRepository
from src.repositories.redis_memory_repository import RedisMemoryRepository
from src.infrastructure.agent_llm_provider import AgentLLMProvider

logger = logging.getLogger(__name__)

class MemoryFactory:
    """
    Factory to create MemoryService instances.
    用於建立 MemoryService 實例的工廠。
    
    Selects backend based on 'MEMORY_BACKEND' env var ('redis' or 'alchemy').
    根據 'MEMORY_BACKEND' 環境變數選擇後端（'redis' 或 'alchemy'）。
    """
    
    @staticmethod
    def create_memory_service(user_id: str = None) -> MemoryService:
        """
        Create a MemoryService instance with the configured repository and LLM provider.
        使用配置的儲存庫與 LLM 提供者建立 MemoryService 實例。
        """
        backend = os.getenv("MEMORY_BACKEND", "alchemy").lower()
        
        # 1. Select Repository
        if backend == "redis":
            redis_url = os.getenv("REDIS_URL")
            logger.info(f"Initializing MemoryService with REDIS backend at {redis_url}")
            repo = RedisMemoryRepository(redis_url)
        else:
            logger.info("Initializing MemoryService with PostgreSQL (Alchemy) backend.")
            repo = AlchemyMemoryRepository()
            
        # 2. Select LLM Provider (Shared)
        # In production, this might also be an interface to a specialized Microservice
        # For now, we use the AgentLLMProvider which uses our Agents for summarization.
        llm_provider = AgentLLMProvider(user_id=user_id)
        
        return MemoryService(repository=repo, llm_provider=llm_provider)
