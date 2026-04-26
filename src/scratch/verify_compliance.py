import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.infrastructure.llm.budget_aware_model_router import BudgetAwareModelRouter
from src.services.settings_service import SettingsService
from src.services.token_logger_service import TokenLoggerService
from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline

async def test_compliance():
    user_id = "test_user_no_settings"
    
    # Ensure NO environment variables are set that could interfere
    if "API_KEY" in os.environ: del os.environ["API_KEY"]
    if "LLM_API_KEY" in os.environ: del os.environ["LLM_API_KEY"]
    if "AI_PROVIDER" in os.environ: del os.environ["AI_PROVIDER"]
    
    print(f"Testing compliance for user: {user_id}")
    
    settings_svc = SettingsService(user_id=user_id)
    token_logger = TokenLoggerService()
    router = BudgetAwareModelRouter(settings_svc, token_logger)
    
    try:
        print("Attempting to get config chain for 'fast' tier...")
        chain = router.get_config_chain("fast", user_id)
        
        if not chain:
            print("SUCCESS: Chain is empty as expected (Rule #13).")
        else:
            print(f"FAILURE: Chain contains candidates even though DB is empty! {chain}")
            return
            
        # Test pipeline execution with empty chain
        pipeline = ResilientLLMPipeline(config_chain=chain)
        print("Attempting to execute pipeline...")
        from src.domain.interfaces import Message
        await pipeline.execute([Message(role="user", content="Hello")], temperature=0.0)
        print("FAILURE: Pipeline executed successfully with empty chain!")
        
    except Exception as e:
        print(f"SUCCESS: Pipeline failed as expected: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_compliance())
