import unittest
import json
import os
import sys
from unittest.mock import MagicMock, patch
from src.agents.base_agent import BaseAgent
from src.agents.engineer import SystemEngineerAgent
from src.repositories.settings_repository import ISettingsRepository
from src.repositories.agent_state_repository import IAgentStateRepository

# Create Mocks purely for type/interface satisfaction if needed, though MagicMock is enough
class MockAgent(BaseAgent):
    def __init__(self, name="Mock", **kwargs):
        super().__init__(name=name, prompt_path="prompts/cio_agent.txt", use_cache=False, **kwargs) # Reuse existing path
    def run(self, context):
        return "Mock Result"

class TestAdaptiveLogic(unittest.TestCase):

    def setUp(self):
        # Create Mock Repos
        self.mock_settings = MagicMock(spec=ISettingsRepository)
        self.mock_settings.get_all.return_value = []
        
        self.mock_state = MagicMock(spec=IAgentStateRepository)
        self.mock_state.get_state.return_value = None

    def test_freshness_logic(self):
        """Test that identical input triggers skip"""
        agent = MockAgent(name="TestFreshness", user_id="test_user", settings_repo=self.mock_settings, state_repo=self.mock_state)
        data = {"key": "value"}
        
        # 1. First Run: State Repo returns None
        self.mock_state.get_state.return_value = None
        is_fresh, _, _ = agent.check_freshness(data)
        self.assertTrue(is_fresh, "First run should be fresh")

        # 2. Second Run: State Repo returns matching hash
        current_hash = agent._compute_hash(data)
        self.mock_state.get_state.return_value = (current_hash, "Last Output")
        is_fresh, _, last_out = agent.check_freshness(data)
        self.assertFalse(is_fresh, "Identical data should be not fresh")
        self.assertEqual(last_out, "Last Output")

        # 3. Data Change
        data_new = {"key": "value_new"}
        # Hash changes, so even if repo returns old hash for same ID, it mismatches
        # But wait, check_freshness re-computes current_hash and compares with what repo returned?
        # If repo is mocked to return constant (hash1, out), and we pass data2 (hash2), hash1 != hash2 -> fresh.
        # But state repo get_state depends on agent ID.
        # If we use same agent ID, repo returns (hash1, out).
        is_fresh, _, _ = agent.check_freshness(data_new)
        self.assertTrue(is_fresh, "Changed data should be fresh")

    def test_hr_protocol_parsing(self):
        """Test Engineer Agent parsing of [HR_REQUEST]"""
        # Pass Mocks
        engineer = SystemEngineerAgent(user_id="test_user", settings_repo=self.mock_settings, state_repo=self.mock_state)
        
        cio_report = """
        Analysis...
        [HR_REQUEST] Replace Agent: Momentum (Reason: Inactivity > 7 days)
        Conclusion...
        """
        
        needs = engineer.analyze_optimization_needs(cio_report)
        self.assertEqual(len(needs), 1)
        self.assertEqual(needs[0]['target_agent'], "Momentum")
        self.assertIn("Inactivity", needs[0]['raw_feedback'])

    @patch('src.services.workflow_service.AlchemyTransactionRepository')
    @patch('src.services.workflow_service.TransactionService')
    @patch('src.services.workflow_service.MarketDataService')
    @patch('src.services.workflow_service.AlchemyMemoryRepository')
    @patch('src.services.workflow_service.AlchemySettingsRepository')
    def test_json_actionable_orders_parsing(self, mock_settings_repo, mock_memory_repo, mock_market_svc, mock_tx_svc, mock_tx_repo):
        """Test parsing of [CONVINCING_ACTION] JSON blocks in workflow report."""
        from src.services.workflow_service import DailyWorkflow
        
        workflow = DailyWorkflow(user_id="test_user")
        
        report_with_json = """
        # Investment Strategy Report
        Some preamble...
        
        [CONVINCING_ACTION]
        {
            "actions": [
                {
                    "ticker": "AAPL",
                    "action": "BUY",
                    "target_weight": 0.08,
                    "current_weight": 0.05,
                    "delta_weight": 0.03,
                    "confidence": 9,
                    "rationale": "Buy AAPL"
                },
                {
                    "ticker": "TSLA",
                    "action": "SELL",
                    "target_weight": 0.02,
                    "current_weight": 0.05,
                    "delta_weight": -0.03,
                    "confidence": 8,
                    "rationale": "Sell TSLA"
                }
            ]
        }
        """
        
        workflow._parse_actionable_orders(report_with_json)
        
        orders = workflow.context.get('actionable_orders', [])
        self.assertEqual(len(orders), 2)
        
        self.assertEqual(orders[0]['ticker'], "AAPL")
        self.assertEqual(orders[0]['action'], "BUY")
        self.assertEqual(orders[0]['score'], 9)
        self.assertEqual(orders[0]['target_weight'], 0.08)
        self.assertEqual(orders[0]['delta_weight'], 0.03)
        self.assertEqual(orders[0]['reason'], "Buy AAPL")
        
        self.assertEqual(orders[1]['ticker'], "TSLA")
        self.assertEqual(orders[1]['action'], "SELL")
        self.assertEqual(orders[1]['score'], 8)
        self.assertEqual(orders[1]['target_weight'], 0.02)
        self.assertEqual(orders[1]['delta_weight'], -0.03)
        self.assertEqual(orders[1]['reason'], "Sell TSLA")

if __name__ == '__main__':
    unittest.main()
