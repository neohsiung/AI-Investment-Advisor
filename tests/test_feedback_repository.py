import pytest
import os
import json
from datetime import datetime
from src.repositories.feedback_repository import AlchemyFeedbackRepository
from src.data.database import init_db, get_db_engine
from src.domain.entities import FeedbackExample, SecurityContext, SignalType

@pytest.fixture
def temp_db_path(tmp_path):
    # Use a temp directory for DB
    db_file = tmp_path / "test_portfolio.db"
    init_db(str(db_file)) # Init schema
    return str(db_file)

def test_repository_save_and_retrieve(temp_db_path):
    # Initialize repository with the test database
    repo = AlchemyFeedbackRepository(db_path=temp_db_path)
    
    # Create Domain Entity
    ctx = SecurityContext(
        ticker="TSLA",
        date=datetime.now(),
        price=200.0,
        indicators={"RSI": 70}
    )
    example = FeedbackExample(
        id=None,
        agent_name="Momentum",
        context=ctx,
        response_text="Overbought. SELL.",
        signal=SignalType.SELL,
        outcome_score=0.5
    )
    
    # Save using the restored method
    repo.save(example)
    
    # Retrieve using the restored method
    # Note: min_score=0.1 should include 0.5
    results = repo.get_training_examples(agent_name="Momentum", min_score=0.1, limit=10)
    
    assert len(results) == 1
    retrieved = results[0]
    
    assert retrieved.agent_name == "Momentum"
    assert retrieved.signal == SignalType.SELL
    assert retrieved.context.ticker == "TSLA"
    assert retrieved.outcome_score == 0.5

def test_repository_hr_feedback(temp_db_path):
    """Test the Peer Review (HR 360) functionality."""
    repo = AlchemyFeedbackRepository(db_path=temp_db_path)
    
    review_id = repo.add_review(
        reviewer="CIO",
        reviewee="Momentum",
        score=5,
        comment="Great job",
        context_hash="hash123"
    )
    
    assert review_id is not None
    
    reviews = repo.get_reviews_for_agent("Momentum")
    assert len(reviews) == 1
    assert reviews[0]["reviewer"] == "CIO"
    assert reviews[0]["score"] == 5
