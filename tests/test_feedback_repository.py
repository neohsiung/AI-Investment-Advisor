import pytest
import os
import json
from datetime import datetime
from src.data.repositories.feedback_repository import SqliteFeedbackRepository
from src.data.database import init_db
from src.domain.entities import FeedbackExample, SecurityContext, SignalType

@pytest.fixture
def temp_db_path(tmp_path):
    # Use a temp directory for DB
    db_file = tmp_path / "test_portfolio.db"
    init_db(str(db_file)) # Init schema
    return str(db_file)

def test_repository_save_and_retrieve(temp_db_path):
    repo = SqliteFeedbackRepository(db_path=temp_db_path)
    
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
    
    # Save
    repo.save(example)
    
    # Retrieve
    # Note: min_score=0.1 should include 0.5
    results = repo.get_training_examples(agent_name="Momentum", min_score=0.1, limit=10)
    
    assert len(results) == 1
    retrieved = results[0]
    
    assert retrieved.agent_name == "Momentum"
    assert retrieved.signal == SignalType.SELL
    assert retrieved.context.ticker == "TSLA"
    assert retrieved.outcome_score == 0.5
