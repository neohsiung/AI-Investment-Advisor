import pytest
import uuid
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.data.models import Base, User, Setting, EventLog, ChannelVerification, RiskKeyword
from src.data.database import BaseRepository

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing models and repository."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def repo(db_session):
    """Create a BaseRepository instance."""
    return BaseRepository(db_session.get_bind())

class TestModels:
    """Test Suite for Infrastructure Models."""
    
    def test_user_creation(self, db_session):
        user = User(email="test@example.com", name="Test User")
        db_session.add(user)
        db_session.commit()
        
        assert user.id is not None
        assert user.email == "test@example.com"
        assert isinstance(user.preferences, dict)
        assert user.created_at is not None

    def test_setting_creation(self, db_session):
        user = User(email="settings@example.com")
        db_session.add(user)
        db_session.commit()
        
        setting = Setting(user_id=user.id, key="theme", value="dark")
        db_session.add(setting)
        db_session.commit()
        
        assert setting.user_id == user.id
        assert setting.value == "dark"

    def test_event_log_creation(self, db_session):
        log = EventLog(event_type="INFO", title="Test Log", content="Test Content")
        db_session.add(log)
        db_session.commit()
        
        assert log.id is not None
        assert log.severity is None # Optional field
        assert log.created_at is not None

    def test_channel_verification(self, db_session):
        verification = ChannelVerification(
            channel="LINE", 
            channel_user_id="U12345", 
            code="123456",
            expires_at=datetime.now() + timedelta(minutes=10)
        )
        db_session.add(verification)
        db_session.commit()
        
        assert verification.status == "pending"
        assert verification.code == "123456"

    def test_risk_keyword(self, db_session):
        kw = RiskKeyword(keyword="bankruptcy", weight=0.9, category="negative")
        db_session.add(kw)
        db_session.commit()
        
        assert kw.is_active == 1
        assert float(kw.weight) == 0.9

class TestBaseRepository:
    """Test Suite for BaseRepository utility methods."""
    
    def test_json_extract_sqlite(self, repo):
        # BaseRepository detects sqlite from engine URL in fixture
        syntax = repo._get_json_extract("metadata", "$.category")
        assert syntax == "json_extract(metadata, '$.category')"

    def test_vector_distance_sqlite(self, repo):
        # sqlite-vec syntax
        syntax = repo._get_vector_distance("embedding", metric="cosine")
        assert "vec_distance_cosine" in syntax

    def test_format_vector_sqlite(self, repo):
        vector = [0.1, 0.2, 0.3]
        formatted = repo._format_vector(vector)
        assert isinstance(formatted, str)
        assert "0.1" in formatted

    def test_session_property(self, repo):
        session = repo.session
        assert session is not None
        session.close()

    def test_pg_syntax_fallback(self):
        """Manually test PG syntax branch if engine wasn't SQLite."""
        class MockEngine:
            url = "postgresql://user@localhost/db"
        
        repo = BaseRepository(MockEngine())
        
        # Test JSON extract for PG
        syntax = repo._get_json_extract("meta", "$.info")
        assert syntax == "meta->>'info'"
        
        # Test vector distance for PG
        dist = repo._get_vector_distance("vec", metric="cosine")
        assert "<=>" in dist
        dist_l2 = repo._get_vector_distance("vec", metric="l2")
        assert "<->" in dist_l2
        
        # Test format vector for PG (should return list)
        v = [0.1, 0.9]
        assert repo._format_vector(v) == v
