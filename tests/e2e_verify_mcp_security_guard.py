import asyncio
import os
import sys
import shutil
from unittest.mock import MagicMock, patch, AsyncMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.conversation_agent import ConversationAgent
from src.agents.skills.gap_detector import GapReport

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "agents", "skills")
SKILLS_DIR = os.path.abspath(SKILLS_DIR)
MALICIOUS_SKILL_NAME = "malicious_eval_tool"

async def test_e2e_mcp_security_interception():
    """
    E2E Verification for Phase 3/4 Security Guard:
    1. Simulate user confirming a gap scaffold.
    2. Auto-generate code containing 'eval' (security violation).
    3. Verify ConversationAgent interceptor blocks activation.
    4. Verify the malicious directory is deleted.
    """
    print(f"🚀 Starting E2E Security Interception Test...")

    # 1. Setup Mock Agent and Settings
    user_id = "test_user_e2e"
    # Ensure no leftover
    malicious_path = os.path.join(SKILLS_DIR, MALICIOUS_SKILL_NAME)
    if os.path.exists(malicious_path):
        shutil.rmtree(malicious_path)

    agent = ConversationAgent(user_id=user_id)
    
    # 2. Mock dependencies
    # Mock SettingsService to avoid DB dependency in E2E
    with patch("src.services.settings_service.SettingsService.get_all_settings") as mock_settings, \
         patch("src.infrastructure.llm.llm_gateway.LLMGatewayFactory.create") as mock_gateway_factory:
        
        mock_settings.return_value = {"API_KEY": "fake_key"}
        
        # Mock LLM and Gateway
        mock_llm = MagicMock()
        mock_gateway_factory.return_value = mock_llm
        
        # 2a. Mock Purpose Alignment (Approve it first to reach code generation)
        # 2b. Mock Code Generation (Contain 'eval')
        # 2c. Mock Review (Doesn't matter if security clear fails first)
        
        mock_llm.chat.side_effect = [
            "Decision: APPROVE\nReason: Valid intent.", # Purpose check
            "def malicious_eval_tool(user_id, **kwargs):\n    eval('1+1')\n    return 'hacked'", # Code generation
            "PASS" # Review (should not even be reached if security check fails)
        ]

        # 3. Prepare the gap record
        pending_gap = {
            "is_gap": True,
            "suggested_skill_name": MALICIOUS_SKILL_NAME,
            "suggested_category": "system",
            "reasoning": "Need a tool to evaluate expressions",
            "can_auto_scaffold": True
        }

        # 4. Execute scaffold confirmation
        print(f"🛠️ Executing gap confirmation for '{MALICIOUS_SKILL_NAME}'...")
        result = await agent._execute_gap_confirmation(pending_gap)

        # 5. Assert Interception
        print(f"📝 Result: {result}")
        assert "資安攔截" in result
        assert "背景調查" in result
        
        # 6. Assert Cleanup
        assert not os.path.exists(malicious_path), "❌ Malicious directory should have been deleted!"
        print(f"✅ Security Interception and Cleanup verified correctly.")

    print("\n🎉 Phase 5 E2E: Security Guard Verification PASSED 🎉")

if __name__ == "__main__":
    asyncio.run(test_e2e_mcp_security_interception())
