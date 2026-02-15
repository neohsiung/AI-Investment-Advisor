"""
Extended tests for Broker Factory.
測試券商工廠。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.services.broker_factory import BrokerFactory


class TestBrokerFactory:
    
    def test_get_broker_etoro(self):
        """Test getting eToro broker instance."""
        with patch('src.services.broker_factory.SqliteSettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            
            mock_repo_instance = MagicMock()
            mock_repo_instance.get.return_value = None
            MockRepo.return_value = mock_repo_instance
            
            mock_broker = MagicMock()
            MockEtoro.return_value = mock_broker
            
            broker = BrokerFactory.get_broker("test_user", broker_type="etoro")
            
            assert broker is not None
            MockEtoro.assert_called_once()
    
    def test_get_broker_futu(self):
        """Test getting Futu broker instance."""
        with patch('src.services.broker_factory.SqliteSettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.FutuService') as MockFutu:
            
            mock_repo_instance = MagicMock()
            mock_repo_instance.get.side_effect = lambda user_id, key: {
                "futu_host": "127.0.0.1",
                "futu_port": "11111",
                "futu_pwd": None
            }.get(key)
            MockRepo.return_value = mock_repo_instance
            
            mock_broker = MagicMock()
            MockFutu.return_value = mock_broker
            
            broker = BrokerFactory.get_broker("test_user", broker_type="futu")
            
            assert broker is not None
            MockFutu.assert_called_once()
    
    def test_get_broker_invalid_defaults_to_etoro(self):
        """Test getting broker with invalid type defaults to eToro."""
        with patch('src.services.broker_factory.SqliteSettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            
            mock_repo_instance = MagicMock()
            mock_repo_instance.get.return_value = None
            MockRepo.return_value = mock_repo_instance
            
            broker = BrokerFactory.get_broker("test_user", broker_type="invalid")
            
            # Should default to eToro
            MockEtoro.assert_called_once()
    
    def test_get_broker_case_insensitive(self):
        """Test broker type is case-insensitive."""
        with patch('src.services.broker_factory.SqliteSettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            
            mock_repo_instance = MagicMock()
            mock_repo_instance.get.return_value = None
            MockRepo.return_value = mock_repo_instance
            
            mock_broker = MagicMock()
            MockEtoro.return_value = mock_broker
            
            BrokerFactory._instances.clear()
            
            broker = BrokerFactory.get_broker("test_user", broker_type="ETORO")
            
            assert broker is not None
            # BrokerFactory converts to lowercase and caches as "etoro"
            assert "etoro" in BrokerFactory._instances

    
    def test_get_broker_caching(self):
        """Test broker instances are cached."""
        with patch('src.services.broker_factory.SqliteSettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            
            mock_repo_instance = MagicMock()
            mock_repo_instance.get.return_value = None
            MockRepo.return_value = mock_repo_instance
            
            mock_broker = MagicMock()
            MockEtoro.return_value = mock_broker
            
            # Clear cache first
            BrokerFactory._instances.clear()
            
            broker1 = BrokerFactory.get_broker("test_user", broker_type="etoro")
            broker2 = BrokerFactory.get_broker("test_user", broker_type="etoro")
            
            # Should only call constructor once due to caching
            assert MockEtoro.call_count == 1
            assert broker1 is broker2
    
    def test_get_enabled_brokers_with_etoro_enabled(self):
        """Test get_enabled_brokers returns eToro when enabled."""
        with patch('src.services.broker_factory.SqliteSettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            
            mock_repo_instance = MagicMock()
            mock_repo_instance.get.side_effect = lambda user_id, key: {
                "enable_etoro": "true"
            }.get(key)
            MockRepo.return_value = mock_repo_instance
            
            BrokerFactory._instances.clear()
            
            brokers = BrokerFactory.get_enabled_brokers("test_user")
            
            assert "etoro" in brokers
            MockEtoro.assert_called()
    
    def test_get_enabled_brokers_fallback_to_etoro(self):
        """Test get_enabled_brokers falls back to eToro when nothing enabled."""
        with patch('src.services.broker_factory.SqliteSettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            
            mock_repo_instance = MagicMock()
            mock_repo_instance.get.return_value = None
            MockRepo.return_value = mock_repo_instance
            
            BrokerFactory._instances.clear()
            
            brokers = BrokerFactory.get_enabled_brokers("test_user")
            
            # Should have at least eToro as fallback
            assert len(brokers) > 0
    
    def test_get_broker_with_settings_from_db(self):
        """Test broker initialization uses settings from database."""
        with patch('src.services.broker_factory.SqliteSettingsRepository') as MockRepo, \
             patch('src.services.broker_factory.EtoroService') as MockEtoro:
            
            mock_repo_instance = MagicMock()
            mock_repo_instance.get.side_effect = lambda user_id, key: {
                "etoro_api_key": "db_api_key",
                "etoro_user_key": "db_user_key",
                "etoro_mode": "demo"
            }.get(key)
            MockRepo.return_value = mock_repo_instance
            
            BrokerFactory._instances.clear()
            
            broker = BrokerFactory.get_broker("test_user", broker_type="etoro")
            
            # Check that EtoroService was called with DB settings
            call_kwargs = MockEtoro.call_args[1]
            assert call_kwargs["api_key"] == "db_api_key"
            assert call_kwargs["user_key"] == "db_user_key"
            assert call_kwargs["mode"] == "demo"

