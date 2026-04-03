import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.append(os.getcwd())

from src.infrastructure.memory.wisdom_vault import WisdomVault
from src.services.experience_replay_service import ExperienceReplayService
from src.domain.interfaces import Message

async def test_feedback_distillation():
    print("\n--- Testing Phase 3: Cognitive Evolution ---")
    
    # Mock LLM Gateway to simulate different confidence scenarios
    mock_llm = MagicMock()
    user_id = "test_user_789"
    
    service = ExperienceReplayService(llm_gateway=mock_llm, user_id=user_id)
    
    # Scenario 1: HIGH Confidence (Direct Store)
    mock_llm.chat.return_value = json.dumps({
        "action": "store",
        "category": "reporting_style",
        "principle": "偏好表格格式回報",
        "confidence": 0.9,
        "reasoning": "使用者明確要求以後用表格",
        "question": None,
        "conflicts_with": None
    })
    
    # [Fix 3X-Verify] Ensure mock handles messages and config arguments
    # The actual service calls: chat(messages, config)
    
    print("\n[Scenario 1] High Confidence Feedback...")
    res = await service.distill_feedback("以後都用表格", "好的。", user_id)
    print(f"Result Action: {res['action']}, Confidence: {res['confidence']}")
    assert res['action'] == "store"
    
    # Scenario 2: MEDIUM Confidence (Clarification)
    mock_llm.chat.return_value = json.dumps({
        "action": "clarify",
        "category": "tone_preference",
        "principle": "偏好熱情活潑的語氣",
        "confidence": 0.5,
        "reasoning": "使用者說你太死板了，暗示可能喜歡活潑一點",
        "question": "您希望我之後的說話語氣更活潑一些嗎？",
        "conflicts_with": None
    })
    
    print("\n[Scenario 2] Medium Confidence Feedback...")
    res = await service.distill_feedback("你說話好死板", "了解您的反饋。", user_id)
    print(f"Result Action: {res['action']}, Question: {res.get('question')}")
    assert res['action'] == "clarify"

    # Scenario 3: Conflict Detection
    # First, store "Conservative"
    vault = WisdomVault()
    vault.store_wisdom(user_id, "risk_profile", "偏好保守投資", confidence=0.8)
    
    mock_llm.chat.return_value = json.dumps({
        "action": "store",
        "category": "risk_profile",
        "principle": "偏好激進投資",
        "confidence": 0.85,
        "reasoning": "使用者現在要求激進，與之前保守矛盾",
        "question": None,
        "conflicts_with": "偏好保守投資"
    })
    
    print("\n[Scenario 3] Conflict Detection...")
    res = await service.distill_feedback("我要改走激進路線", "已收到。", user_id)
    print(f"Conflicts With: {res.get('conflicts_with')}")
    
    if res.get('conflicts_with'):
        service.record_feedback(
            user_id=user_id,
            category=res['category'],
            principle=res['principle'],
            confidence=res['confidence'],
            conflicts_with=res['conflicts_with']
        )
        
    # Verify in Vault
    all_wisdom = vault.load_wisdom(user_id, categories=["risk_profile"])
    print(f"Vault Entries for risk_profile: {len(all_wisdom)}")
    for w in all_wisdom:
        print(f" - {w.principle} (Conf: {w.confidence}, Tags: {w.tags})")
        if w.principle == "偏好保守投資":
            assert w.confidence == 0.1
            assert "superseded" in w.tags

    print("\n--- Phase 3 Verification Successful ---")

if __name__ == "__main__":
    asyncio.run(test_feedback_distillation())
