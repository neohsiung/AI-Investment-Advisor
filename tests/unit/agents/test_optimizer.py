import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock dspy before importing optimizer
orig_dspy = sys.modules.get("dspy")
orig_dspy_teleprompt = sys.modules.get("dspy.teleprompt")

sys.modules["dspy"] = MagicMock()
sys.modules["dspy.teleprompt"] = MagicMock()

from src.workflow.optimizer import OptimizerPipeline
from src.domain.entities import FeedbackExample, SignalType

@pytest.fixture(scope="module", autouse=True)
def cleanup_dspy():
    yield
    # Restore original sys.modules states after all tests in this module run
    if orig_dspy is None:
        sys.modules.pop("dspy", None)
    else:
        sys.modules["dspy"] = orig_dspy

    if orig_dspy_teleprompt is None:
        sys.modules.pop("dspy.teleprompt", None)
    else:
        sys.modules["dspy.teleprompt"] = orig_dspy_teleprompt



class MockFeedbackRepo:
    def __init__(self, db_path):
        pass
    def get_training_examples(self, agent_name, min_score, limit):
        # Return a list of fake FeedbackExamples
        return [
            FeedbackExample(
                id="1", agent_name="Momentum", 
                context=MagicMock(to_json=lambda: '{"data": "ctx"}'),
                response_text="Analysis", 
                signal=SignalType.BUY,
                outcome_score=1.0,
                # feedback_text="Good", # Not in dataclass definition in entities.py
                timestamp="2023-01-01"
            )
        ]

@patch('src.workflow.optimizer.AlchemyFeedbackRepository', new=MockFeedbackRepo)
def test_optimizer_initialization():
    optimizer = OptimizerPipeline(db_path=":memory:")
    assert optimizer is not None

@patch('src.workflow.optimizer.AlchemyFeedbackRepository', new=MockFeedbackRepo)
def test_load_training_data():
    optimizer = OptimizerPipeline()
    # Mock dspy availability check? 
    # The module checks `if dspy is None`. Since we mocked it in sys.modules, it should be truthy.
    
    examples = optimizer.load_training_data()
    assert len(examples) == 1
    # Check if dspy.Example was called
    sys.modules["dspy"].Example.assert_called()

@patch('src.workflow.optimizer.AlchemyFeedbackRepository', new=MockFeedbackRepo)
def test_optimize_momentum_agent():
    optimizer = OptimizerPipeline()
    trainset = optimizer.load_training_data()
    
    # Mock BootstrapFewShot
    with patch('src.workflow.optimizer.BootstrapFewShot') as mock_boot:
        mock_compiler = MagicMock()
        mock_boot.return_value = mock_compiler
        mock_compiler.compile.return_value = MagicMock()
        
        module = optimizer.optimize_momentum_agent(trainset)
        
        mock_boot.assert_called()
        mock_compiler.compile.assert_called()
        # Save is called
        module.save.assert_called()

def test_optimizer_no_dspy():
    # Simulate dspy missing
    with patch('src.workflow.optimizer.dspy', None):
        optimizer = OptimizerPipeline()
        examples = optimizer.load_training_data()
        assert examples == []
        res = optimizer.optimize_momentum_agent([])
        assert res is None
