import pytest
import re
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from src.services.cognitive_memory_manager import CognitiveMemoryManager
from src.services.sentinel_service import SentinelService
from src.utils.security import redact_pii

# Configuration for test environment
@pytest.fixture
def mock_user():
    return {"sub": "test_user_unique_999", "type": "access"}

@pytest.fixture
def client(mock_user):
    from fastapi import FastAPI
    from src.services.dashboard_router import dashboard_router, get_current_user
    app = FastAPI()
    app.include_router(dashboard_router)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    return TestClient(app)

def test_cognitive_memory_path_sanitization():
    """Test that CognitiveMemoryManager sanitizes user_id to prevent path traversal."""
    with patch("src.services.cognitive_memory_manager.get_db_engine"), \
         patch("src.services.cognitive_memory_manager.Path.mkdir"):
        
        # 1. Malicious user_id
        malicious_id = "../../../etc/passwd"
        manager = CognitiveMemoryManager(user_id=malicious_id)
        
        # Expected safe ID: "etcpasswd"
        assert manager.long_term_path.name == "etcpasswd"
        assert ".." not in str(manager.long_term_path)
        
        # 2. Alphanumeric with special safe chars
        complex_id = "user-123_abc!@#"
        manager2 = CognitiveMemoryManager(user_id=complex_id)
        assert manager2.long_term_path.name == "user-123_abc"
        
        # 3. None/Empty fallback
        manager_none = CognitiveMemoryManager(user_id=None)
        assert manager_none.long_term_path.name == "default"

@pytest.mark.asyncio
async def test_sentinel_log_redaction():
    """Test that SentinelService redacts user_id in logs using redact_pii."""
    with patch("src.services.sentinel_service.logger") as mock_logger:
        with patch("src.services.sentinel_service.AlchemySentinelRepository"), \
             patch("src.services.sentinel_service.AlchemySnapshotRepository"), \
             patch("src.services.sentinel_service.SettingsService"), \
             patch("src.services.sentinel_service.MarketDataService"), \
             patch("src.services.sentinel_service.InternetSearchService"), \
             patch("src.services.sentinel_service.TransactionService") as mock_trans, \
             patch("src.services.sentinel_service.CouncilService"), \
             patch("src.services.sentinel_service.RiskKeywordService"), \
             patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer"):
            
            user_id = "PII_SENSITIVE_USER_ID"
            service = SentinelService(user_id=user_id)
            
            # Setup for process_tick
            mock_trans.return_value.get_user_tickers.return_value = ["AAPL"]
            service.market_service.get_current_prices = AsyncMock(return_value={"AAPL": 150.0})
            service._check_vix_anomaly = MagicMock(return_value=[])
            service._check_buffer_flush = AsyncMock()
            service._check_position_moves_v2 = AsyncMock(return_value=[])
            service._check_active_sources = AsyncMock(return_value=[])
            service._check_risk_consistency = AsyncMock(return_value=[])
            service._handle_cash_deployment_logic = AsyncMock()
            service._check_infrastructure_health = AsyncMock(return_value=[])
            
            await service.process_tick()
            
            # Verify that redact_pii was used for the monitoring log
            redacted = redact_pii(user_id)
            
            info_calls = [call.args[0] for call in mock_logger.info.call_args_list]
            log_found = any(f"for user {redacted}" in msg for msg in info_calls)
            raw_leaked = any(user_id in msg for msg in info_calls if "for user" in msg and redacted not in msg)
            
            assert log_found, "Redacted user_id not found in logs"
            assert not raw_leaked, "Raw user_id leaked in logs"

def test_dashboard_exception_sanitization(client):
    """Test that DashboardRouter does not expose raw exception strings to the client."""
    with patch("src.services.dashboard_router.DashboardService") as mock_service_class:
        # Mock instance and method
        mock_instance = mock_service_class.return_value
        mock_instance.prepare_dashboard_data.side_effect = Exception("SECRET_INTERNAL_DB_PATH: /usr/local/secret")
        
        response = client.get("/summary")
        
        assert response.status_code == 500
        # Payload should be generic
        data = response.json()
        assert "SECRET_INTERNAL_DB_PATH" not in str(data)
        assert "Internal server error" in data["detail"]

def test_dashboard_reports_exception_sanitization(client):
    """Test that /reports endpoint sanitizes exceptions."""
    with patch("src.services.dashboard_router.AsyncAlchemyReportRepository") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.get_latest_reports = AsyncMock(side_effect=Exception("DB_QUERY_FAILURE_EXPOSE_SCHEMA"))
        
        response = client.get("/reports")
        assert response.status_code == 500
        assert "DB_QUERY_FAILURE_EXPOSE_SCHEMA" not in response.text
        assert "Failed to fetch reports" in response.json()["detail"]

def test_dashboard_rebalance_exception_sanitization(client):
    """Test that /rebalance endpoint sanitizes exceptions."""
    with patch("src.infrastructure.tasks.trigger_portfolio_rebalance.delay") as mock_delay:
        mock_delay.side_effect = Exception("CELERY_CONNECTION_ERROR_IP_LEAK: 10.0.0.5")
        
        response = client.post("/rebalance")
        assert response.status_code == 500
        assert "CELERY_CONNECTION_ERROR_IP_LEAK" not in response.text
        assert "Failed to trigger rebalance flow" in response.json()["detail"]

@pytest.mark.asyncio
async def test_sentinel_macro_check():
    """Test Dimension 4+6 macro and global event checks in SentinelService."""
    with patch("src.services.sentinel_service.AlchemySentinelRepository"), \
         patch("src.services.sentinel_service.AlchemySnapshotRepository"), \
         patch("src.services.sentinel_service.SettingsService"), \
         patch("src.services.sentinel_service.MarketDataService"), \
         patch("src.services.sentinel_service.InternetSearchService"), \
         patch("src.services.sentinel_service.TransactionService"), \
         patch("src.services.sentinel_service.CouncilService"), \
         patch("src.services.sentinel_service.RiskKeywordService"), \
         patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer"):
        
        service = SentinelService(user_id="macro_test_user")
        
        # Mock macro data for _check_macro_shifts
        macro_data = {
            "economics": {
                "10Y2Y_Spread": {"value": -0.5} # Yield curve inversion
            },
            "market_indicators": {
                "^VIX": 45.0 # Extreme panic
            }
        }
        
        service.market_service.get_macro_data = MagicMock(return_value=macro_data)
        service.thresholds = {"vix_extreme": 40.0}
        
        triggers = await service._check_macro_shifts()
        ids = [t["id"] for t in triggers]
        assert "macro_yield_inversion" in ids
        assert "macro_vix_extreme" in ids

def test_cognitive_memory_storage_fallback():
    """Test that CognitiveMemoryManager successfully falls back to local storage on DB error."""
    with patch("src.services.cognitive_memory_manager.get_db_engine") as mock_engine, \
         patch("src.services.cognitive_memory_manager.Path.mkdir"), \
         patch("builtins.open", new_callable=patch_open) as mock_file:
        
        # Force DB failure on first connect
        mock_engine.return_value.connect.side_effect = Exception("No DB")
        
        manager = CognitiveMemoryManager(user_id="test_fallback_user")
        assert manager._db_available is False
        
        # Test store_insight
        manager.store_insight("TestAgent", "test_memory", {"data": "val"})
        
        # Verify it tried to write to fallback_path
        assert mock_file.called
        # Check that the filename contains the memory_type
        args, kwargs = mock_file.call_args
        assert "test_memory" in str(args[0])

def test_dashboard_add_transaction_sanitization(client):
    """Test that /data/transactions (POST) sanitizes exceptions."""
    with patch("src.services.dashboard_router.TransactionService") as mock_service_class:
        mock_service = mock_service_class.return_value
        # Mock add_manual_trade returning success=False with a sensitive message
        mock_service.add_manual_trade.return_value = (False, "SQL_ERROR: Table 'users_private' not found")
        
        payload = {"ticker": "AAPL", "quantity": 10, "price": 150}
        response = client.post("/data/transactions", json=payload)
        
        assert response.status_code == 400
        assert "SQL_ERROR" not in response.text
        assert "交易新增失敗" in response.json()["detail"]

def test_dashboard_delete_transaction_sanitization(client):
    """Test that /data/transactions/{id} (DELETE) sanitizes exceptions."""
    with patch("src.services.dashboard_router.TransactionService") as mock_service_class:
        mock_service = mock_service_class.return_value
        mock_service.delete_transaction.return_value = (False, "OS_ERROR: Cannot delete file /root/db/tx_999.lock")
        
        response = client.delete("/data/transactions/999")
        
        assert response.status_code == 400
        assert "OS_ERROR" not in response.text
        assert "交易刪除失敗" in response.json()["detail"]

def patch_open(*args, **kwargs):
    return MagicMock()
