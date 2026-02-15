import sys
import os
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.infrastructure.nlp.intent_classifier import IntentClassifier

def test_chinese_intent():
    print("--- Testing Chinese Intent Classification ---")
    
    # Mock LLM provider to avoid API costs/errors, focusing on keyword fallback logic first
    # Or strict real test if keys exist.
    # The fallback logic I added is BEFORE LLM call? No, it's AFTER or INDEPENDENT.
    # In my code:
    # response = agent.run(prompt) ...
    # if "執行" in text ... return APPROVE
    # Wait, I put the fallback validation *after* the agent run?
    # Actually I should put it *before* to save costs/time, but the current code has it after/parallel.
    # Let's check the file content again.
    
    # If I want to test the keyword logic, I need to make sure agent.run doesn't crash.
    # If keys are missing, agent.run might crash. 
    # Let's mock the internal provider if needed.
    
    classifier = IntentClassifier()
    # Mock the internal agent if no keys
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️ No API Keys, mocking internal agent to return dummy")
        # Update for new structure: classifier.agent instead of llm_provider
        classifier.agent = MagicMock()
        classifier.agent.run.return_value = "UNKNOWN" # Force it to use keyword fallback
    
    test_cases = [
        ("執行", "APPROVE"),
        ("我確認執行", "APPROVE"),
        ("不執行", "REJECT"),
        ("取消交易", "REJECT"),
        ("Sure, go ahead", "APPROVE"), # English still works? (Depends on mock/llm)
        ("No", "REJECT")
    ]
    
    for text, expected in test_cases:
        result = classifier.classify(text)
        status = "✅" if result == expected else f"❌ (Got {result})"
        print(f"Input: '{text}' -> Expected: {expected} {status}")

if __name__ == "__main__":
    test_chinese_intent()
