import pytest
import gc
import weakref
from unittest.mock import MagicMock, patch
from src.agents.skills.registry import SkillRegistry

class MockAgent:
    def __init__(self, name="TestAgent"):
        self.name = name
        self.toold = MagicMock()
        self.skill_loader = MagicMock()
        self.user_id = "test_user"
        self.register_tool = MagicMock()

def test_registry_active_agents_weakref():
    """驗證 SkillRegistry 使用弱引用，當 Agent 被銷毀時會自動移除。"""
    registry = SkillRegistry()
    agent = MockAgent()
    
    registry.register_agent(agent)
    assert agent in registry._active_agents
    assert len(registry._active_agents) == 1
    
    # 銷毀 Agent 實例
    name_ref = agent.name
    del agent
    gc.collect() # 強致執行垃圾回收
    
    assert len(registry._active_agents) == 0

@patch("src.agents.skills.registry.SkillRegistry.auto_discover_from_impl")
def test_hot_reload_propagation(mock_discover):
    """驗證 hot_reload 會將新技能推播給所有活躍的 Agent。"""
    registry = SkillRegistry()
    agent1 = MockAgent("Agent1")
    agent2 = MockAgent("Agent2")
    
    registry.register_agent(agent1)
    registry.register_agent(agent2)
    
    # 模擬發現了新技能 'new_super_tool'
    registry._implementations['new_super_tool'] = lambda u: "done"
    
    # 模擬 hot_reload 邏輯中發現新技能
    # 我們直接手動模擬 _propagate_to_agent 的呼叫環境
    with patch.object(registry, '_propagate_to_agent') as mock_propagate:
        # 假設本次 hot_reload 發現了 'new_super_tool'
        # 我們直接操作內部 set 來模擬 before/after 差異
        # 由於 hot_reload 代碼中：before = set(self._implementations.keys())
        # 所以我們要在呼叫前先清空或調整
        registry._implementations = {} 
        
        # 執行 hot_reload (會呼叫 discover)
        # 我們模擬 discover 後 implementations 多了一個
        def side_effect(*args):
            registry._implementations['new_super_tool'] = lambda u: "done"
        mock_discover.side_effect = side_effect
        
        new_skills = registry.hot_reload()
        
        assert 'new_super_tool' in new_skills
        # 驗證推播被呼叫了兩次 (兩個 Agent)
        assert mock_propagate.call_count == 2
        mock_propagate.assert_any_call(agent1, ['new_super_tool'])
        mock_propagate.assert_any_call(agent2, ['new_super_tool'])

def test_propagate_to_agent_binding():
    """驗證 _propagate_to_agent 是否真的執行了 Agent 的工具註冊。"""
    registry = SkillRegistry()
    agent = MockAgent()
    registry.register_agent(agent)
    
    # 準備技能實作
    registry.register("test_skill", lambda uid: f"uid:{uid}")
    
    # 模擬技能中繼資料
    mock_skill_def = MagicMock()
    mock_skill_def.description = "Test Description"
    agent.skill_loader.skills = {"test_skill": mock_skill_def}
    
    # 執行推播
    registry._propagate_to_agent(agent, ["test_skill"])
    
    # 驗證 Agent.register_tool 被呼叫
    assert agent.register_tool.called
    tool = agent.register_tool.call_args[0][0]
    assert tool.name == "test_skill"
    assert tool.description == "Test Description"
    # 驗證 func 是否已 bind user_id
    assert tool.func() == "uid:test_user"
