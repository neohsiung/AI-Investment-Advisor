import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from src.workflow.optimizer import OptimizerPipeline
from src.domain.entities import FeedbackExample, SecurityContext, SignalType

@pytest.fixture
def mock_repo():
    return MagicMock()

def test_load_training_data_no_dspy(mock_repo):
    # Simulate DSPy missing
    with patch("src.workflow.optimizer.dspy", None):
        pipeline = OptimizerPipeline()
        pipeline.repo = mock_repo
        
        data = pipeline.load_training_data()
        assert data == []

def test_load_training_data_success(mock_repo):
    # Simulate DSPy available
    with patch("src.workflow.optimizer.dspy") as mock_dspy:
        # Define mock Example class
        mock_dspy.Example = MagicMock()
        
        pipeline = OptimizerPipeline()
        pipeline.repo = mock_repo
        
        # Mock Repo Response
        mock_ctx = SecurityContext(ticker="AAPL", date=datetime.now(), price=100, indicators={})
        mock_ex = FeedbackExample(
            id="1", 
            agent_name="Momentum", 
            context=mock_ctx, 
            response_text="Analysis... BUY", 
            signal=SignalType.BUY, 
            outcome_score=0.8
        )
        mock_repo.get_training_examples.return_value = [mock_ex]
        
        data = pipeline.load_training_data()
        
        assert len(data) == 1
        mock_repo.get_training_examples.assert_called_with("Momentum", min_score=0.1, limit=20)
        assert mock_dspy.Example.called

def test_optimize_flow_success(mock_repo):
    with patch("src.workflow.optimizer.dspy") as mock_dspy, \
         patch("src.workflow.optimizer.BootstrapFewShot") as MockTeleprompter:
        
        pipeline = OptimizerPipeline()
        trainset = [MagicMock()]
        
        # Mock Optimizer Compilation
        mock_compiler = MockTeleprompter.return_value
        mock_compiled_program = MagicMock()
        mock_compiler.compile.return_value = mock_compiled_program
        
        res = pipeline.optimize_momentum_agent(trainset)
        
        assert res == mock_compiled_program
        mock_compiler.compile.assert_called()
        mock_compiled_program.save.assert_called()
