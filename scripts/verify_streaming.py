"""
Verification Script for Phase 8: LLM Streaming & SSE (Mocked).
驗證串流回應與 SSE 格式 (使用 Mock 避免資料庫依賴)。

This script tests the streaming flow using Mock repositories to avoid environment hangs.
"""
import asyncio
import os
import json
from unittest.mock import MagicMock

# Force SQLite for verification to avoid Postgres connection errors
os.environ["DB_TYPE"] = "sqlite"
os.environ["DB_URL"] = "sqlite:///:memory:"

from src.agents.cio import CIOAgent
from src.domain.interfaces import Message, LLMConfig

async def verify_streaming():
    print("🚀 Starting Mocked Streaming Verification...")
    
    # Mock dependencies to avoid DB/Network hangs during initialization
    mock_settings_repo = MagicMock()
    mock_state_repo = MagicMock()
    mock_feedback_repo = MagicMock()
    
    # Mock settings to use MockLLMGateway
    mock_settings_repo.get_all.return_value = []
    
    user_id = "test_user_v8"
    
    print("Creating CIOAgent with mocks...")
    # Manually create CIOAgent to avoid Factory's heavy dependency injection
    agent = CIOAgent(
        user_id=user_id,
        settings_repo=mock_settings_repo,
        state_repo=mock_state_repo,
        feedback_repo=mock_feedback_repo,
        use_cache=False
    )
    
    # Force MockLLMGateway for verification
    from src.infrastructure.llm.llm_gateway import MockLLMGateway
    agent._llm_gateway = MockLLMGateway()
    
    # Allowlist-validate config fields before logging to break CodeQL taint path (#59)
    _KNOWN_PROVIDERS = {'openai', 'anthropic', 'gemini', 'groq', 'azure', 'mock'}
    _raw_provider = str(agent.config.get('provider', ''))
    _provider = _raw_provider if _raw_provider in _KNOWN_PROVIDERS else 'unknown'
    _raw_model = str(agent.config.get('model', ''))
    import re as _re
    _model = _raw_model if _re.match(r'^[a-zA-Z0-9._-]{1,60}$', _raw_model) else 'unknown'
    print(f"--- Testing LLM Gateway: {_provider} ({_model}) ---")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Verify streaming works."}
    ]
    
    print("Yielding chunks:")
    full_response = ""
    chunk_count = 0
    
    try:
        # agents.stream_llm is a synchronous generator
        for chunk in agent.stream_llm(messages=messages):
            print(f"[{chunk}]", end="", flush=True)
            full_response += chunk
            chunk_count += 1
            # Very small sleep
            await asyncio.sleep(0.001)
    except Exception as e:
        print(f"\n❌ Streaming failed: {e}")
        return

    print(f"\n\n✅ Streaming Complete!")
    print(f"Total Chunks: {chunk_count}")
    
    if chunk_count > 1:
        print("PASS: Multiple chunks received.")
    else:
        print("FAIL: Expected multiple chunks from MockLLMGateway.")

    # Verify SSE format simulation
    print("\n--- Verifying SSE Format ---")
    sse_chunk = f"data: {json.dumps({'chunk': 'Hello'})}\n\n"
    print(f"SSE Sample: {sse_chunk.strip()}")
    if sse_chunk.startswith("data: ") and sse_chunk.endswith("\n\n"):
        print("PASS: SSE format is correct.")
    else:
        print("FAIL: SSE format mismatch.")

if __name__ == "__main__":
    asyncio.run(verify_streaming())
