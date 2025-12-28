"""
Test coverage for SqliteSnapshotRepository
"""
import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from src.repositories.snapshot_repository import SqliteSnapshotRepository


class TestSnapshotRepository:
    """Test suite for SqliteSnapshotRepository"""
    
    @pytest.fixture
    def repo(self):
        """Create repository instance"""
        return SqliteSnapshotRepository(db_path=':memory:')
    
    def test_initialization(self, repo):
        """Test repository initializes correctly"""
        assert repo is not None
        assert hasattr(repo, 'db_path')
        assert repo.db_path == ':memory:'
    
    def test_initialization_with_custom_path(self):
        """Test initialization with custom database path"""
        repo = SqliteSnapshotRepository(db_path='/custom/path/db.sqlite')
        assert repo.db_path == '/custom/path/db.sqlite'
    
    @patch('src.repositories.snapshot_repository.get_db_connection')
    @patch('src.repositories.snapshot_repository.pd.read_sql')
    def test_get_history_by_user(self, mock_read_sql, mock_conn, repo):
        """Test retrieving snapshot history for a user"""
        mock_df = pd.DataFrame({
            'date': ['2025-01-01', '2025-01-02'],
            'user_id': ['test@example.com', 'test@example.com'],
            'total_nlv': [10000, 10500],
            'cash_balance': [2000, 2500],
            'invested_capital': [8000, 8000],
            'pnl': [500, 1000],
            'leverage_ratio': [1.2, 1.1]
        })
        mock_read_sql.return_value = mock_df
        
        result = repo.get_history_by_user('test@example.com')
        
        assert result is not None
        assert len(result) == 2
        mock_conn.assert_called_once_with(':memory:')
        mock_read_sql.assert_called_once()
    
    @patch('src.repositories.snapshot_repository.get_db_connection')
    @patch('src.repositories.snapshot_repository.pd.read_sql')
    def test_get_latest_by_user(self, mock_read_sql, mock_conn, repo):
        """Test getting most recent snapshot"""
        mock_df = pd.DataFrame({
            'date': ['2025-01-02'],
            'user_id': ['test@example.com'],
            'total_nlv': [10500],
            'cash_balance': [2500],
            'pnl': [1000]
        })
        mock_read_sql.return_value = mock_df
        
        result = repo.get_latest_by_user('test@example.com')
        
        assert result is not None
        assert result['total_nlv'] == 10500
        mock_read_sql.assert_called_once()
    
    @patch('src.repositories.snapshot_repository.get_db_connection')
    @patch('src.repositories.snapshot_repository.pd.read_sql')
    def test_get_latest_returns_none_when_no_data(self, mock_read_sql, mock_conn, repo):
        """Test get_latest returns None for user with no snapshots"""
        mock_read_sql.return_value = pd.DataFrame()  # Empty dataframe
        
        result = repo.get_latest_by_user('nonexistent@example.com')
        
        assert result is None
    
    @patch('src.repositories.snapshot_repository.get_db_connection')
    def test_save_snapshot(self, mock_conn, repo):
        """Test saving a snapshot"""
        mock_connection = Mock()
        mock_conn.return_value = mock_connection
        
        repo.save_snapshot(
            user_id='test@example.com',
            date='2025-01-01',
            nlv=10000.0,
            cash_balance=2000.0,
            invested_capital=8000.0,
            pnl=500.0,
            total_tnv=12000.0,
            leverage_ratio=1.2
        )
        
        # Verify connection was obtained and commit was called
        mock_conn.assert_called_once_with(':memory:')
        mock_connection.execute.assert_called_once()
        mock_connection.commit.assert_called_once()
        mock_connection.close.assert_called_once()
    
    @patch('src.repositories.snapshot_repository.get_db_connection')
    @patch('src.repositories.snapshot_repository.pd.read_sql')
    def test_get_history_returns_empty_dataframe_when_no_data(self, mock_read_sql, mock_conn, repo):
        """Test empty dataframe returned when no history"""
        mock_read_sql.return_value = pd.DataFrame()
        
        result = repo.get_history_by_user('nonexistent@example.com')
        
        assert isinstance(result, pd.DataFrame)
        assert result.empty
    
    def test_repository_interface_methods_exist(self, repo):
        """Test repository has required interface methods"""
        assert hasattr(repo, 'get_history_by_user')
        assert hasattr(repo, 'get_latest_by_user')
        assert hasattr(repo, 'save_snapshot')
        assert callable(repo.get_history_by_user)
        assert callable(repo.get_latest_by_user)
        assert callable(repo.save_snapshot)
