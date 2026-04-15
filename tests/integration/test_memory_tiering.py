import os
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta
from pathlib import Path

from src.data.database import init_db, get_db_engine
from src.services.memory_distillation_service import MemoryDistillationService
from src.services.cognitive_memory_manager import CognitiveMemoryManager
from src.agents.base_agent import BaseAgent
from sqlalchemy import text

class MockAgent(BaseAgent):
    def run(self, context):
        system_prompt = self.render_system_prompt(context)
        return self.call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "test"}
        ])

@pytest.fixture
def db_setup():
    # Force SQLite in-memory for testing
    os.environ["DB_URL"] = "sqlite:///:memory:"
    engine = get_db_engine()
    init_db()
    return engine

@pytest.mark.asyncio
async def test_full_cognitive_memory_pipeline(db_setup):
    user_id = "test_user_123"
    engine = db_setup
    
    # 1. Seed some event logs
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO event_logs (user_id, event_type, title, content, created_at)
            VALUES (:user_id, 'alert', 'VIX Spike', 'VIX jumped to 30.0', :ts)
        """), {
            "user_id": user_id, 
            "ts": datetime.now() - timedelta(hours=2),
            "content": "VIX jumped to 30.0"
        })
        conn.execute(text("""
            INSERT INTO event_logs (user_id, event_type, title, content, created_at)
            VALUES (:user_id, 'signal', 'TSLA Long', 'Momentum turning bullish', :ts)
        """), {
            "user_id": user_id, 
            "ts": datetime.now() - timedelta(hours=1),
            "content": "Momentum turning bullish"
        })

    # 2. Mock the LLM Distillation call
    mock_distilled_json = {
        "summary": "Market volatility is rising with VIX at 30, but TSLA shows bullish momentum.",
        "key_events": ["VIX Spike to 30", "TSLA Bullish Pivot"],
        "convictions": [{"subject": "TSLA", "sentiment": "bullish", "reasoning": "Momentum pivot"}],
        "importance": 0.9
    }
    
    with patch("src.infrastructure.llm.llm_gateway.LLMGatewayFactory.create") as mock_factory:
        mock_gateway = MagicMock()
        mock_gateway.chat = AsyncMock(return_value=json.dumps(mock_distilled_json))
        mock_factory.return_value = mock_gateway
        
        # 3. Run Distillation Service
        service = MemoryDistillationService(user_id=user_id)
        await service.distill_daily_memory()
        
    # 4. Verify memory storage
    manager = CognitiveMemoryManager(user_id=user_id)
    memories = manager.get_recent_memories()
    
    assert len(memories) >= 1
    assert memories[0]["memory_type"] == "daily_summary"
    assert memories[0]["content"]["summary"] == mock_distilled_json["summary"]
    
    # 5. Verify Agent Integration (Context Assembly)
    # We need a dummy prompt file
    prompt_path = "/tmp/test_prompt.txt"
    with open(prompt_path, "w") as f:
        f.write("System: {{cognitive_context}}\nUser: {{input}}")
        
    agent = MockAgent(
        name="TestAgent",
        prompt_path=prompt_path,
        user_id=user_id,
        tier="fast"
    )
    
    # Mocking call_llm to capture the system prompt
    with patch.object(BaseAgent, "call_llm", new_callable=AsyncMock) as mock_call:
        await agent.run({"input": "What happened?"})
        
        # Check system prompt contents
        args, _ = mock_call.call_args
        messages = args[0]
        system_msg = messages[0]["content"] if isinstance(messages[0], dict) else messages[0].content
        
        assert "cognitive_memory_highlights" in system_msg
        assert mock_distilled_json["summary"] in system_msg
        
    print("Full cognitive memory pipeline test passed!")
