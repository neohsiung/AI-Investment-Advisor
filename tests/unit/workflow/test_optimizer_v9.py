import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_dspy():
    # We patch the dspy module in optimizer if it's there
    with patch("src.workflow.optimizer.dspy") as mock_dspy, \
         patch("src.workflow.optimizer.BootstrapFewShot") as mock_bfs:
        yield mock_dspy, mock_bfs

def test_optimizer_init():
    with patch("src.workflow.optimizer.AlchemyFeedbackRepository") as mock_repo:
        from src.workflow.optimizer import OptimizerPipeline
        pipeline = OptimizerPipeline()
        assert pipeline.repo is not None

def test_load_training_data_no_dspy():
    with patch("src.workflow.optimizer.AlchemyFeedbackRepository"):
        from src.workflow.optimizer import OptimizerPipeline
        pipeline = OptimizerPipeline()
        
        # Force dspy to None
        with patch("src.workflow.optimizer.dspy", None):
            res = pipeline.load_training_data()
            assert res == []

def test_load_training_data_with_examples(mock_dspy):
    with patch("src.workflow.optimizer.AlchemyFeedbackRepository") as mock_repo:
        from src.workflow.optimizer import OptimizerPipeline
        from src.domain.entities import FeedbackExample, SignalType, SecurityContext
        
        # Create a mock example
        ex1 = MagicMock(spec=FeedbackExample)
        ex1.context = MagicMock()
        ex1.context.to_json.return_value = '{"ticker": "AAPL"}'
        ex1.response_text = "Good"
        ex1.signal = SignalType.BUY
        
        mock_repo.return_value.get_training_examples.return_value = [ex1]
        
        pipeline = OptimizerPipeline()
        res = pipeline.load_training_data()
        
        assert len(res) == 1
        # It should have called dspy.Example
        mock_dspy[0].Example.assert_called()

def test_optimize_momentum_agent_no_dspy():
    with patch("src.workflow.optimizer.AlchemyFeedbackRepository"):
        from src.workflow.optimizer import OptimizerPipeline
        pipeline = OptimizerPipeline()
        
        with patch("src.workflow.optimizer.dspy", None):
            res = pipeline.optimize_momentum_agent([MagicMock()])
            assert res is None

def test_optimize_momentum_agent(mock_dspy):
    with patch("src.workflow.optimizer.AlchemyFeedbackRepository"):
        from src.workflow.optimizer import OptimizerPipeline
        pipeline = OptimizerPipeline()
        
        mock_compiled = MagicMock()
        mock_bfs = mock_dspy[1]
        mock_bfs.return_value.compile.return_value = mock_compiled
        
        trainset = [MagicMock()]
        res = pipeline.optimize_momentum_agent(trainset)
        
        # Verify compiled and saved
        assert res == mock_compiled
        mock_compiled.save.assert_called_once()
