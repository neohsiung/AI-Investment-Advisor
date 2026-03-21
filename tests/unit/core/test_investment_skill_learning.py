"""
Tests for InvestmentSkillLearningService.

Tests cover:
1. Skill extraction from article content (mock LLM)
2. Skill extraction from podcast transcript
3. Skill merge when similar exists
4. Skill creation when no similar exists
5. Dynamic threshold adjustment (token overbudget / skill count low)
6. Skill cleanup
7. Get applicable skills
8. SkillLoader discovery
9. Webhook parser
"""
import json
import pytest
from unittest.mock import MagicMock, patch


# ── Fixtures ────────────────────────────────────────────────

@pytest.fixture
def mock_engine():
    """Create an in-memory SQLite engine for tests."""
    from src.data.database import get_db_engine, init_db
    engine = get_db_engine(":memory:")
    init_db(engine=engine)
    # Seed a test user
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT OR IGNORE INTO users (id, email, name) VALUES ('test_user', 'test@test.com', 'Test')"
        ))
    return engine


@pytest.fixture
def service(mock_engine):
    """Create service with mocked agent and patched DB engine."""
    with patch('src.services.investment_skill_learning_service.AgentFactory') as MockFactory, \
         patch('src.data.database.get_db_engine', return_value=mock_engine):
        mock_agent = MagicMock()
        MockFactory.create_agent.return_value = mock_agent
        
        from src.services.investment_skill_learning_service import InvestmentSkillLearningService
        svc = InvestmentSkillLearningService(user_id="test_user")
        svc._mock_agent = mock_agent  # expose for test assertions
        yield svc


MOCK_EXTRACTION_RESPONSE = json.dumps({
    "name": "Momentum Breakout Strategy",
    "description": "Uses price breakouts above resistance to enter positions with tight stop losses.",
    "timeframe": "short_term",
    "environment": {"market_regime": "bull", "volatility": "high", "interest_rate": "any"},
    "industry": ["tech", "energy"],
    "technique": "momentum",
    "conditions": {
        "entry_signals": "Price breaks above 20-day high with volume > 1.5x average",
        "exit_signals": "Price drops below 10-day EMA",
        "risk_management": "Stop loss at 2% below entry"
    },
    "is_valid_skill": True
})

MOCK_INVALID_EXTRACTION = json.dumps({
    "name": "N/A",
    "description": "This content discusses cooking recipes, not investment.",
    "is_valid_skill": False
})

MOCK_MERGE_RESPONSE = json.dumps({
    "action": "MERGE",
    "merge_target_id": "existing_id_1",
    "merged_description": "Enhanced momentum breakout strategy combining two approaches.",
    "merged_conditions": {"entry_signals": "Combined signals", "exit_signals": "Combined exits", "risk_management": "Tighter stops"},
    "reasoning": "High overlap in momentum technique and timeframe."
})

MOCK_CREATE_RESPONSE = json.dumps({
    "action": "CREATE",
    "merge_target_id": None,
    "merged_description": None,
    "merged_conditions": None,
    "reasoning": "Unique macro-based contrarian approach not covered by existing skills."
})


# ── Test: Skill Extraction ──────────────────────────────────

def test_extract_skill_from_article(service):
    """Test that extract_skill_from_content returns correct structure from article."""
    service._mock_agent._call_real_llm.return_value = MOCK_EXTRACTION_RESPONSE

    result = service.extract_skill_from_content(
        content="When a stock breaks above its 20-day high with above-average volume...",
        source_url="https://example.com/momentum-strategy",
        source_type="article",
    )

    assert result is not None
    assert result["name"] == "Momentum Breakout Strategy"
    assert result["timeframe"] == "short_term"
    assert result["technique"] == "momentum"
    assert result["source_article"] == "https://example.com/momentum-strategy"
    assert result["source_type"] == "article"


def test_extract_skill_from_podcast(service):
    """Test skill extraction from podcast transcript."""
    service._mock_agent._call_real_llm.return_value = MOCK_EXTRACTION_RESPONSE

    result = service.extract_skill_from_content(
        content="Transcript of investment podcast discussing breakout patterns...",
        source_url="https://podcast.example.com/ep42",
        source_type="podcast",
    )

    assert result is not None
    assert result["source_type"] == "podcast"


def test_extract_invalid_content(service):
    """Test that non-investment content returns None."""
    service._mock_agent._call_real_llm.return_value = MOCK_INVALID_EXTRACTION

    result = service.extract_skill_from_content(
        content="Today we will discuss how to make spaghetti carbonara...",
        source_type="article",
    )

    assert result is None


# ── Test: Merge or Create ───────────────────────────────────

def test_merge_with_existing_skill(service, mock_engine):
    """Test that skill is merged when similar exists and LLM says MERGE."""
    from sqlalchemy import text

    # Insert an existing skill
    with mock_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO investment_skills (id, user_id, name, description, technique, timeframe, is_active) "
            "VALUES ('existing_id_1', 'test_user', 'Basic Momentum', 'Simple momentum', 'momentum', 'short_term', 1)"
        ))

    service._mock_agent._call_real_llm.return_value = MOCK_MERGE_RESPONSE

    new_skill = {
        "name": "Advanced Momentum",
        "technique": "momentum",
        "timeframe": "short_term",
        "source_article": "https://example.com/adv-momentum",
    }

    similar = [{"id": "existing_id_1", "name": "Basic Momentum", "description": "Simple momentum", "technique": "momentum", "timeframe": "short_term"}]
    result = service.merge_or_create_skill(new_skill, similar)

    assert result["action"] == "MERGED"
    assert result["id"] == "existing_id_1"


def test_create_when_no_similar(service, mock_engine):
    """Test that a new skill is created when no similar skills exist."""
    new_skill = {
        "name": "Contrarian Macro",
        "description": "Buy when everyone is selling based on macro indicators.",
        "technique": "contrarian",
        "timeframe": "long_term",
        "environment": {"market_regime": "bear"},
        "industry": ["all"],
        "conditions": {},
        "source_article": "https://example.com/contrarian",
        "source_type": "article",
    }

    result = service.merge_or_create_skill(new_skill, [])

    assert result["action"] == "CREATED"
    assert result["name"] == "Contrarian Macro"


# ── Test: Dynamic Threshold ─────────────────────────────────

def test_threshold_increase_on_token_overbudget(service, mock_engine):
    """Test threshold increases when token usage exceeds budget."""
    from sqlalchemy import text

    with mock_engine.begin() as conn:
        conn.execute(text(
            "INSERT OR REPLACE INTO skill_learning_config "
            "(user_id, merge_threshold, max_token_budget, last_token_usage, total_skills_count) "
            "VALUES ('test_user', 0.70, 2000, 3000, 10)"
        ))

    service.adjust_merge_threshold()

    # Verify threshold was increased
    with mock_engine.connect() as conn:
        result = conn.execute(text(
            "SELECT merge_threshold FROM skill_learning_config WHERE user_id = 'test_user'"
        )).fetchone()

    assert float(result[0]) == pytest.approx(0.75, abs=0.01)


def test_threshold_decrease_on_low_skill_count(service, mock_engine):
    """Test threshold decreases when skill count is low."""
    from sqlalchemy import text

    with mock_engine.begin() as conn:
        conn.execute(text(
            "INSERT OR REPLACE INTO skill_learning_config "
            "(user_id, merge_threshold, max_token_budget, last_token_usage, total_skills_count) "
            "VALUES ('test_user', 0.70, 2000, 500, 3)"
        ))

    service.adjust_merge_threshold()

    with mock_engine.connect() as conn:
        result = conn.execute(text(
            "SELECT merge_threshold FROM skill_learning_config WHERE user_id = 'test_user'"
        )).fetchone()

    assert float(result[0]) == pytest.approx(0.65, abs=0.01)


# ── Test: Cleanup ───────────────────────────────────────────

def test_cleanup_runs_without_error(service, mock_engine):
    """Test that cleanup runs without error (SQLite doesn't support INTERVAL)."""
    from sqlalchemy import text

    with mock_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO investment_skills (id, user_id, name, technique, usage_count, is_active) "
            "VALUES ('stale_1', 'test_user', 'Old Unused Skill', 'momentum', 0, 1)"
        ))
        conn.execute(text(
            "INSERT INTO investment_skills (id, user_id, name, technique, usage_count, is_active) "
            "VALUES ('active_1', 'test_user', 'Popular Skill', 'fundamental', 50, 1)"
        ))

    result = service.cleanup_skills()
    assert "deactivated" in result


# ── Test: Get Applicable Skills ─────────────────────────────

def test_get_applicable_skills(service, mock_engine):
    """Test querying skills by context."""
    from sqlalchemy import text

    with mock_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO investment_skills (id, user_id, name, description, technique, timeframe, "
            "environment, industry, usage_count, is_active) "
            "VALUES ('skill_1', 'test_user', 'Momentum Play', 'Fast momentum', 'momentum', 'short_term', "
            "'{\"market_regime\": \"bull\"}', '[\"tech\"]', 10, 1)"
        ))
        conn.execute(text(
            "INSERT INTO investment_skills (id, user_id, name, description, technique, timeframe, "
            "environment, industry, usage_count, is_active) "
            "VALUES ('skill_2', 'test_user', 'Value Buy', 'Value investing', 'value', 'long_term', "
            "'{\"market_regime\": \"bear\"}', '[\"financials\"]', 5, 1)"
        ))
        # Config for token tracking
        conn.execute(text(
            "INSERT OR REPLACE INTO skill_learning_config (user_id) VALUES ('test_user')"
        ))

    skills = service.get_applicable_skills(technique="momentum")

    assert len(skills) >= 1
    assert any(s["name"] == "Momentum Play" for s in skills)


# ── Test: SkillLoader Discovery ─────────────────────────────

def test_skill_loader_discovers_investment_skill():
    """Test that SkillLoader discovers the investment_skill metadata."""
    from src.agents.skills.skill_loader import SkillLoader

    loader = SkillLoader()
    discovered = loader.discover_skills()
    assert "investment_skill" in discovered, f"investment_skill not found in: {list(discovered.keys())}"


# ── Test: Webhook Parser ────────────────────────────────────

def test_skill_learning_parser_article():
    """Test SkillLearningParser with article payload."""
    from src.services.webhook_service import SkillLearningParser

    payload = {
        "event_type": "DAILY_SKILL_LEARNING",
        "article_text": "This article discusses momentum investing...",
        "article_url": "https://example.com/article",
        "source_type": "article",
    }
    result = SkillLearningParser.parse(payload)

    assert result["type"] == "DAILY_SKILL_LEARNING"
    assert "momentum" in result["content"]
    assert result["source_url"] == "https://example.com/article"
    assert result["source_type"] == "article"


def test_skill_learning_parser_podcast():
    """Test SkillLearningParser with podcast transcript payload."""
    from src.services.webhook_service import SkillLearningParser

    payload = {
        "event_type": "PODCAST_SKILL_LEARNING",
        "transcript": "Today on the show we discuss breakout trading...",
        "source_type": "podcast",
        "source_name": "Market Masters",
    }
    result = SkillLearningParser.parse(payload)

    assert result["type"] == "PODCAST_SKILL_LEARNING"
    assert "breakout" in result["content"]
    assert result["source_type"] == "podcast"
    assert result["source_name"] == "Market Masters"


# ── Test: Daily Learning Flow ───────────────────────────────

def test_daily_learning_full_flow(service, mock_engine):
    """Test the complete daily learning flow with article input."""
    from sqlalchemy import text

    # Seed config
    with mock_engine.begin() as conn:
        conn.execute(text(
            "INSERT OR REPLACE INTO skill_learning_config (user_id) VALUES ('test_user')"
        ))

    service._mock_agent._call_real_llm.side_effect = [
        MOCK_EXTRACTION_RESPONSE,  # extract_skill_from_content
    ]

    result = service.run_daily_learning(
        content="When a stock breaks above its 20-day high...",
        source_url="https://example.com/strategy",
        source_type="article",
    )

    assert result["status"] == "completed"
    assert result["action"] == "CREATED"
    assert result["skill_name"] == "Momentum Breakout Strategy"


def test_daily_learning_skips_no_content(service, mock_engine):
    """Test that daily learning skips when no content is available."""
    with patch.object(service, '_fetch_readwise_content', return_value=""):
        result = service.run_daily_learning()

    assert result["status"] == "skipped"


# ── Test: Registry ──────────────────────────────────────────

def test_registry_has_investment_skill():
    """Test that the default registry includes investment_skill."""
    from src.agents.skills.registry import SkillRegistry

    registry = SkillRegistry()
    registry._ensure_builtins()  # Builtins are lazy-loaded
    assert registry.has("investment_skill")
