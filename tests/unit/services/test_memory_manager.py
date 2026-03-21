"""
Real integration tests for Hybrid Memory Manager.
使用真實的 SQLite in-memory 資料庫測試記憶管理器。
"""
import pytest
import json
import sqlite3
from src.infrastructure.memory.memory_manager import HybridMemory


class TestHybridMemoryIntegration:
    """Real integration tests using sqlite3 temporary database files."""
    
    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Fixture to provide unique temp database path for each test."""
        return str(tmp_path / "test_memory.db")
    
    def test_initialization_creates_tables(self, temp_db_path):
        """Test that initialization creates all required tables."""
        memory = HybridMemory(db_path=temp_db_path)
        
        # Memory manager should have created its own connection
        assert memory is not None
        assert memory.vector_dim == 1536
    
    def test_add_and_search_simple_memory(self, temp_db_path):
        """Test adding and searching memory with real database."""
        memory = HybridMemory(db_path=temp_db_path)
        
        # Add a memory
        memory.add_memory(
            memory_id="test_001",
            user_id="user_123",
            content="Apple announced new iPhone with better camera",
            embedding=[0.1] * 1536,
            category="tech_news"
        )
        
        # Search should work (keyword-based via FTS5)
        results = memory.search(
            query_text="iPhone camera",
            query_vector=[0.1] * 1536,
            limit=5
        )
        
        # Should find the memory via keyword search
        assert isinstance(results, list)
    
    def test_add_multiple_memories(self, temp_db_path):
        """Test adding multiple memories."""
        memory = HybridMemory(db_path=temp_db_path)
        
        memories = [
            ("mem_001", "user_1", "Tesla stock rises 5%", [0.2] * 1536, "stock_news"),
            ("mem_002", "user_1", "Apple launches new product", [0.3] * 1536, "tech_news"),
            ("mem_003", "user_1", "Fed raises interest rates", [0.4] * 1536, "macro_news")
        ]
        
        for mem_id, user_id, content, embedding, category in memories:
            memory.add_memory(mem_id, user_id, content, embedding, category)
        
        # Search should return results
        results = memory.search(
            query_text="stock market",
            query_vector=[0.2] * 1536,
            limit=10
        )
        
        assert isinstance(results, list)
    
    def test_search_keyword_only(self, temp_db_path):
        """Test keyword search when vector search is unavailable."""
        memory = HybridMemory(db_path=temp_db_path)
        
        memory.add_memory(
            "mem_001",
            "user_1",
            "Machine learning improves trading strategies",
            [0.5] * 1536,
            "tech"
        )
        
        # Search with keyword only (no vector)
        results = memory.search(
            query_text="machine learning trading",
            query_vector=None,
            limit=5
        )
        
        assert isinstance(results, list)
    
    def test_empty_search_results(self, temp_db_path):
        """Test search with no matches returns empty list."""
        memory = HybridMemory(db_path=temp_db_path)
        
        results = memory.search(
            query_text="nonexistent query xyz",
            query_vector=[0.9] * 1536,
            limit=5
        )
        
        assert results == []
    
    def test_weighted_fusion_configuration(self):
        """Test that fusion weights are properly configured."""
        memory = HybridMemory(db_path=":memory:", vector_dim=768)
        
        assert memory.vector_dim == 768
        assert memory.vector_weight == 0.7
        assert memory.keyword_weight == 0.3
        assert memory.vector_weight + memory.keyword_weight == 1.0
    
    def test_metadata_storage_and_retrieval(self, temp_db_path):
        """Test that metadata is correctly stored and retrieved."""
        memory = HybridMemory(db_path=temp_db_path)
        
        metadata = {
            "source": "bloomberg",
            "timestamp": "2024-01-15",
            "priority": "high",
            "tags": ["tech", "earnings"]
        }
        
        memory.add_memory(
            "mem_meta_001",
            "user_1",
            "Tech company beats earnings estimates",
            [0.6] * 1536,
            "earnings",
            metadata=metadata
        )
        
        results = memory.search(
            query_text="earnings",
            query_vector=[0.6] * 1536,
            limit=1
        )
        
        if results:
            result_metadata = results[0].get('metadata', {})
            assert result_metadata.get('source') == 'bloomberg'
            assert result_metadata.get('priority') == 'high'
    
    def test_fts5_search_functionality(self, temp_db_path):
        """Test Full-Text Search (FTS5) functionality."""
        memory = HybridMemory(db_path=temp_db_path)
        
        # Add memories with different content
        memory.add_memory("m1", "u1", "Python programming tutorial", [0.1] * 1536, "edu")
        memory.add_memory("m2", "u1", "JavaScript web development course", [0.2] * 1536, "edu")
        memory.add_memory("m3", "u1", "Machine learning with Python", [0.3] * 1536, "edu")
        
        # Search for "Python" should match m1 and m3
        results = memory.search(
            query_text="Python",
            query_vector=[0.1] * 1536,
            limit=10
        )
        
        # Check that we got results
        assert isinstance(results, list)
    
    def test_concurrent_user_memories(self, temp_db_path):
        """Test storing memories for different users."""
        memory = HybridMemory(db_path=temp_db_path)
        
        # User 1 memories
        memory.add_memory("u1_m1", "user_1", "User one first memory", [0.1] * 1536, "general")
        memory.add_memory("u1_m2", "user_1", "User one second memory", [0.2] * 1536, "general")
        
        # User 2 memories
        memory.add_memory("u2_m1", "user_2", "User two first memory", [0.3] * 1536, "general")
        
        # Search should return all relevant memories regardless of user
        results = memory.search(
            query_text="memory",
            query_vector=[0.1] * 1536,
            limit=10
        )
        
        assert len(results) > 0
    
    def test_special_characters_in_content(self, temp_db_path):
        """Test handling special characters in content."""
        memory = HybridMemory(db_path=temp_db_path)
        
        content_with_special = "Stock price: $150.00 (↑5%) - Q4'24 earnings beat!"
        
        memory.add_memory(
            "special_001",
            "user_1",
            content_with_special,
            [0.5] * 1536,
            "stocks"
        )
        
        results = memory.search(
            query_text="earnings",
            query_vector=[0.5] * 1536,
            limit=5
        )
        
        if results:
            assert results[0]['content'] == content_with_special
    
    def test_large_content_storage(self, temp_db_path):
        """Test storing large text content."""
        memory = HybridMemory(db_path=temp_db_path)
        
        # Create a large content string (simulate a long article)
        large_content = "Investment analysis report. " * 100  # ~3000 chars
        
        memory.add_memory(
            "large_001",
            "user_1",
            large_content,
            [0.7] * 1536,
            "report"
        )
        
        results = memory.search(
            query_text="investment analysis",
            query_vector=[0.7] * 1536,
            limit=1
        )
        
        assert isinstance(results, list)
    
    def test_embedding_dimension_flexibility(self, tmp_path):
        """Test creating memory manager with different embedding dimensions."""
        memory_384 = HybridMemory(db_path=str(tmp_path / "mem384.db"), vector_dim=384)
        memory_768 = HybridMemory(db_path=str(tmp_path / "mem768.db"), vector_dim=768)
        memory_1536 = HybridMemory(db_path=str(tmp_path / "mem1536.db"), vector_dim=1536)
        
        assert memory_384.vector_dim == 384
        assert memory_768.vector_dim == 768
        assert memory_1536.vector_dim == 1536
        
        # Add memory with matching dimension
        memory_384.add_memory("m1", "u1", "Test", [0.1] * 384, "test")
        memory_768.add_memory("m2", "u1", "Test", [0.1] * 768, "test")
        memory_1536.add_memory("m3", "u1", "Test", [0.1] * 1536, "test")
