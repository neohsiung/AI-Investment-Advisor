
import sys
import os
import json

# Add src to path
sys.path.append(os.getcwd())

from src.agents.factory import AgentFactory
from src.data.database import init_db

def test_mcp_tools():
    print("\n--- Testing MCP Tools Injection ---")
    # 1. Create CIO Agent (Should have tools injected)
    cio = AgentFactory.create_cio_agent(user_id="test_user")
    
    # 2. Check if tools exist
    tools = cio.toold.list_tools()
    print(f"Tools Registered: {len(tools)}")
    for t in tools:
        print(f" - {t['name']}: {t['description']}")
    
    if len(tools) == 0:
        print("FAIL: No tools injected.")
        return False
    
    # 3. Execute a Tool directly
    print("Testing 'get_current_price' tool...")
    try:
        res = cio.toold.call_tool("get_current_price", {"ticker": "AAPL"})
        print(f"Result: {json.dumps(res, indent=2)}")
        if "AAPL" in res:
            print("PASS: Tool execution successful.")
    except Exception as e:
        print(f"FAIL: Tool execution error: {e}")
        return False
        
    return True

def test_hr_protocol():
    print("\n--- Testing HR Protocol (Feedback) ---")
    cio = AgentFactory.create_cio_agent(user_id="test_user")
    
    # 1. Simulate Feedback
    sender_agent = "DataAnalyst"
    score = 5
    comment = "Great request, very clear."
    
    print(f"CIO rating request from {sender_agent}...")
    cio.rate_request(sender_agent, score, comment)
    
    # 2. Verify in DB
    from src.repositories.feedback_repository import SqliteFeedbackRepository
    repo = SqliteFeedbackRepository()
    reviews = repo.get_reviews_by_agent("CIO")
    
    found = False
    for r in reviews:
        if r['reviewee'] == sender_agent and r['score'] == score:
            print(f"Found Review in DB: {r}")
            found = True
            break
            
    if found:
        print("PASS: Feedback stored correctly.")
    else:
        print("FAIL: Feedback not found in DB.")
        return False

    return True

def test_agent_mesh_call():
    print("\n--- Testing Agent Mesh (Call Agent) ---")
    cio = AgentFactory.create_cio_agent(user_id="test_user")
    
    # CALL: CIO -> Fundamental Listener (Mock)
    # We call 'Fundamental' agent
    print("CIO calling Fundamental Agent...")
    try:
        # Note: This might make a real LLM call if not cached or mocked.
        # But BaseAgent usually catches errors or returns mock if no key.
        response = cio.call_agent("Fundamental", "Analyze AAPL for verification.")
        print(f"Response from Fundamental: {str(response)[:100]}...")
        if response:
            print("PASS: Agent Call successful.")
    except Exception as e:
        print(f"FAIL: Agent Call error: {e}")
        return False
        
    return True

if __name__ == "__main__":
    init_db() # Ensure schema
    
    all_pass = True
    if not test_mcp_tools(): all_pass = False
    if not test_hr_protocol(): all_pass = False
    if not test_agent_mesh_call(): all_pass = False
    
    if all_pass:
        print("\n=== ALL TESTS PASSED ===")
        sys.exit(0)
    else:
        print("\n=== SOME TESTS FAILED ===")
        sys.exit(1)
