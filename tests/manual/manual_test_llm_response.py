import sys
import os
import time
from unittest.mock import MagicMock

# Add project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.interaction_service import InteractionService
from src.domain.interaction import InteractionRequest, InteractionType, InteractionStatus
from src.infrastructure.nlp.intent_classifier import IntentClassifier

def test_llm_flow():
    print("--- Starting LLM Response Test ---")
    
    # 1. Mock Adapter (We don't need real channels for this test)
    mock_adapter = MagicMock()
    mock_adapter.register_callback = MagicMock()
    mock_adapter.register_text_callback = MagicMock()
    
    # 2. Real Intent Classifier (or Mock Agent if no keys)
    # Check if keys exist, otherwise mock the internal agent
    try:
        classifier = IntentClassifier()
        if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
            print("⚠️ No LLM API Keys found. Mocking internal agent.")
            classifier.agent = MagicMock()
            
            def mock_run(prompt_str):
                # Robustly extract user response
                # Prompt format: ... USER RESPONSE: "{text}" ...
                try:
                    prompt_str = str(prompt_str)
                    if 'USER RESPONSE: "' in prompt_str:
                        user_part = prompt_str.split('USER RESPONSE: "')[1].split('"')[0].lower()
                    else:
                        user_part = prompt_str.lower()
                        
                    if any(w in user_part for w in ["ok", "sure", "yes", "execute", "執行"]):
                        return "APPROVE"
                    if any(w in user_part for w in ["no", "cancel", "reject", "不執行"]):
                        return "REJECT"
                    return "UNKNOWN"
                except:
                    return "UNKNOWN"
            
            classifier.agent.run.side_effect = mock_run
        else:
            print("✅ Using Real IntentClassifier with Real LLM")
            
    except Exception as e:
        print(f"Failed to init classifier: {e}")
        return

    # 3. Init Service
    service = InteractionService(adapters=[mock_adapter], intent_classifier=classifier)
    
    # 4. Create a Pending Request
    user_id = "U_TEST_USER"
    req_id = "REQ_123"
    
    # Manually inject request
    req = InteractionRequest(
        request_id=req_id,
        user_id=user_id,
        type=InteractionType.APPROVAL,
        title="Test Trade",
        content="Buy AAPL?"
    )
    service._pending_requests[req_id] = req
    print(f"Created Pending Request: {req_id} for {user_id}")
    
    # 5. Simulate User Text Response "Sure, go ahead"
    user_text = "Sure, go ahead"
    print(f"User replies: '{user_text}'")
    service.handle_text_response(user_id, user_text)
    
    # 6. Verify Status
    if req.status == InteractionStatus.APPROVED:
        print("✅ SUCCESS: Request was APPROVED based on text.")
    else:
        print(f"❌ FAILED: Request status is {req.status}")

    # 7. Test Rejection
    # Reset
    req.status = InteractionStatus.PENDING
    user_text = "No, I don't want this."
    print(f"User replies: '{user_text}'")
    service.handle_text_response(user_id, user_text)
    
    if req.status.value == "REJECTED":
        print("✅ SUCCESS: Request was REJECTED based on text.")
    else:
        print(f"❌ FAILED: Request status is {req.status}")

if __name__ == "__main__":
    test_llm_flow()
