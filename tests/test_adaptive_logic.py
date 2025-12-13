import unittest
import json
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from src.agents.base_agent import BaseAgent
from src.agents.dispatcher import DispatcherAgent
from src.agents.engineer import SystemEngineerAgent

class MockAgent(BaseAgent):
    def __init__(self, name="Mock"):
        super().__init__(name=name, prompt_path="prompts/cio_agent.txt", use_cache=False) # Reuse existing path
    def run(self, context):
        return "Mock Result"

class TestAdaptiveLogic(unittest.TestCase):

    def setUp(self):
        # Mock DB connection
        self.mock_conn = MagicMock()
        self.patcher = patch('src.agents.base_agent.get_db_connection', return_value=self.mock_conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_freshness_logic(self):
        """Test that identical input triggers skip"""
        agent = MockAgent(name="TestFreshness")
        data = {"key": "value"}
        
        # 1. First Run: DB returns None
        self.mock_conn.execute.return_value.fetchone.return_value = None
        is_fresh, _, _ = agent.check_freshness(data)
        self.assertTrue(is_fresh, "First run should be fresh")

        # 2. Second Run: DB returns matching hash
        current_hash = agent._compute_hash(data)
        self.mock_conn.execute.return_value.fetchone.return_value = (current_hash, "2025-01-01", "Last Output")
        is_fresh, _, last_out = agent.check_freshness(data)
        self.assertFalse(is_fresh, "Identical data should be not fresh")
        self.assertEqual(last_out, "Last Output")

        # 3. Data Change
        data_new = {"key": "value_new"}
        is_fresh, _, _ = agent.check_freshness(data_new)
        self.assertTrue(is_fresh, "Changed data should be fresh")

    def test_hr_protocol_parsing(self):
        """Test Engineer Agent parsing of [HR_REQUEST]"""
        engineer = SystemEngineerAgent()
        
        cio_report = """
        Analysis...
        [HR_REQUEST] Replace Agent: Momentum (Reason: Inactivity > 7 days)
        Conclusion...
        """
        
        needs = engineer.analyze_optimization_needs(cio_report)
        self.assertEqual(len(needs), 1)
        self.assertEqual(needs[0]['target_agent'], "Momentum")
        self.assertIn("Inactivity", needs[0]['raw_feedback'])

    @patch('src.agents.dispatcher.DispatcherAgent._call_real_llm')
    def test_dispatcher_logic(self, mock_llm):
        """Test Dispatcher JSON parsing"""
        agent = DispatcherAgent()
        
        # Mock LLM Response
        mock_response = """
        ```json
        {
            "agents": ["Momentum", "Fundamental"],
            "tickers": ["AAPL"],
            "intent": "analysis"
        }
        ```
        """
        mock_llm.return_value = mock_response
        
        result = agent.run({"user_input": "Test Input"})
        self.assertEqual(result['agents'], ["Momentum", "Fundamental"])
        self.assertEqual(result['tickers'], ["AAPL"])

if __name__ == '__main__':
    unittest.main()
