import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from src.infrastructure.llm.llm_gateway import LLMGatewayFactory, LoggingLLMGateway
from src.domain.interfaces import LLMConfig, Message
from src.services.cognitive_memory_manager import CognitiveMemoryManager
from src.data.database import get_db_engine
from sqlalchemy import text

logger = logging.getLogger("MemoryDistillationService")

class MemoryDistillationService:
    """
    Rule #8: Cognitive Memory Distillation.
    記憶提煉服務：定期掃描原始日誌並提煉出結構化見解。
    
    Workflow:
    1. Fetch raw event logs and LLM usage logs (Last 24h).
    2. Feed to Nano LLM (Gemini Flash) with distillation prompt.
    3. Store structured memory in CognitiveMemoryManager (Medium-Term).
    """

    def __init__(self, user_id: str, tier: str = "nano"):
        self.user_id = user_id
        self.tier = tier
        self.memory_manager = CognitiveMemoryManager(user_id=user_id)
        self.engine = get_db_engine()
        
        # Initialize Gateway
        provider = os.getenv("AI_PROVIDER", "Google Gemini")
        inner = LLMGatewayFactory.create(provider)
        self._llm_gateway = LoggingLLMGateway(
            inner=inner,
            agent_name="MemoryDistillationService",
            tier=self.tier,
            user_id=self.user_id
        )

    async def distill_daily_memory(self):
        """
        Main job to distill the last 24 hours of activity into a single memory entry.
        """
        logger.info(f"Starting daily distillation for user: {self.user_id}")
        
        # 1. Fetch raw logs
        raw_logs_text = self._fetch_recent_activity_text(hours=24)
        if not raw_logs_text:
            logger.info("No activity found in the last 24h. Skipping distillation.")
            return
            
        # 2. Distill via LLM
        distilled_data = await self._call_distillation_llm(raw_logs_text)
        if not distilled_data:
            logger.error("Distillation failed to return valid data.")
            return
            
        # 3. Store structured memory
        importance = distilled_data.get("importance", 0.5)
        self.memory_manager.store_insight(
            agent_name="MemoryDistillationService",
            memory_type="daily_summary",
            content=distilled_data,
            importance=importance,
            source_id=f"distill_{datetime.now().strftime('%Y%m%d')}"
        )
        logger.info(f"Daily distillation complete. Narrative: {distilled_data.get('summary')[:100]}...")

    def _fetch_recent_activity_text(self, hours: int = 24) -> str:
        """
        Aggregate event logs and LLM usage metadata into a textual stream.
        """
        since = datetime.now() - timedelta(hours=hours)
        
        # Fetch event logs
        event_sql = """
        SELECT event_type, title, content, metadata 
        FROM event_logs 
        WHERE user_id = :user_id AND created_at >= :since
        ORDER BY created_at ASC
        """
        
        # Fetch LLM usage highlights (where agent performed reasoning)
        usage_sql = """
        SELECT agent_name, model, metadata 
        FROM llm_usage_logs 
        WHERE user_id = :user_id AND timestamp >= :since
        ORDER BY timestamp ASC
        """
        
        output = []
        try:
            with self.engine.connect() as conn:
                events = conn.execute(text(event_sql), {"user_id": self.user_id, "since": since}).fetchall()
                for e in events:
                    output.append(f"[{e[0]}] {e[1]}: {e[2]}")
                    
                usages = conn.execute(text(usage_sql), {"user_id": self.user_id, "since": since}).fetchall()
                for u in usages:
                    meta = json.loads(u[2]) if isinstance(u[2], str) else u[2]
                    # Only include reasoning if it's there
                    if meta and "reasoning" in meta:
                        output.append(f"[Agent: {u[0]}] Reasoning: {meta['reasoning']}")
                        
            return "\n".join(output)
        except Exception as e:
            logger.error(f"Failed to fetch recent activity: {e}")
            return ""

    async def _call_distillation_llm(self, raw_logs: str) -> Optional[Dict[str, Any]]:
        """
        Calls the LLM to perform structural distillation.
        """
        # Load prompt
        prompt_path = "prompts/memory_distillation.txt"
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
            
            full_prompt = template.replace("{{raw_logs}}", raw_logs[:8000]) # Cap input
            
            from src.infrastructure.llm.tier_config import SettingsAwareModelRouter
            try:
                from src.repositories.settings_repository import AlchemySettingsRepository
                settings_repo = AlchemySettingsRepository()
                model_router = SettingsAwareModelRouter(settings_repo)
                model = model_router.get_model(self.user_id, "nano")
            except Exception as e:
                logger.warning(f"MemoryDistillation: Model router failed, using tier default: {e}")
                from src.infrastructure.llm.tier_config import TierConfig
                tier_config = TierConfig()
                model = tier_config.resolve("nano")
            
            config = LLMConfig(
                provider=os.getenv("AI_PROVIDER", "OpenRouter"),
                model=model,
                api_key=os.getenv("API_KEY", ""),
                temperature=0.2,
                max_tokens=1000
            )
            
            messages = [Message(role="user", content=full_prompt)]
            content = await self._llm_gateway.chat(messages, config)
            
            # Parse JSON
            cleaned = content.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned)
        except Exception as e:
            logger.error(f"Distillation LLM call failed: {e}")
            return None
