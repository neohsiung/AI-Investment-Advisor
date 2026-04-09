import sys
import os
import shutil
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

from src.agents.skills.registry import get_default_registry
from src.agents.skills.skill_loader import SkillLoader

def test_modular_skills():
    print("--- Verifying Skill Modularization ---")
    reg = get_default_registry()
    
    # Ensure registry is initialized
    reg._ensure_builtins()
    
    expected_skills = [
        "search_web", "get_market_data", "get_portfolio", "investment_skill",
        "position_sizing", "auto_discover_learning", "get_historical_report",
        "strategic_envisioning", "attacker_lens_validation", "alpha_judgment_synthesis"
    ]
    
    found = reg.list_registered()
    print(f"Registered skills: {found}")
    
    for skill in expected_skills:
        assert skill in found, f"Skill '{skill}' not discovered!"
    
    print("✅ All 10 core skills auto-discovered.")

    # Test invocation (mocking services)
    with patch('src.services.search_service.InternetSearchService') as mock_svc:
        mock_instance = mock_svc.return_value
        mock_instance.search_financial_context.return_value = [{"title": "Test", "snippet": "Test", "link": "test"}]
        
        result = reg.get("search_web")("test_user", query="AI News")
        assert "Test" in result
        print("✅ Invocation of 'search_web' successful through registry.")

def test_hot_reload():
    print("\n--- Verifying Hot-reload ---")
    reg = get_default_registry()
    
    temp_skill_dir = "src/agents/skills/temp_hot_test"
    os.makedirs(temp_skill_dir, exist_ok=True)
    
    with open(f"{temp_skill_dir}/metadata.json", "w") as f:
        f.write('{"name": "temp_hot_test", "description": "Test", "input_schema": {}, "output_schema": {}}')
    
    with open(f"{temp_skill_dir}/impl.py", "w") as f:
        f.write('def temp_hot_test(user_id, **kwargs): return "Hot reload success"')
        
    try:
        new_skills = reg.hot_reload()
        assert "temp_hot_test" in new_skills
        assert reg.has("temp_hot_test")
        print(f"✅ Hot-reload discovered new skill: {new_skills}")
        
        result = reg.get("temp_hot_test")("test_user")
        assert result == "Hot reload success"
        print("✅ New skill invoked successfully.")
    finally:
        shutil.rmtree(temp_skill_dir)
        reg.unregister("temp_hot_test")

if __name__ == "__main__":
    try:
        test_modular_skills()
        test_hot_reload()
        print("\n🎉 Skill Architecture Verification Passed!")
    except Exception as e:
        print(f"\n❌ Verification Failed: {e}")
        sys.exit(1)
