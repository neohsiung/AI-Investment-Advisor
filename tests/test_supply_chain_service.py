import pytest
from unittest.mock import MagicMock
from src.services.supply_chain_service import SupplyChainService

@pytest.fixture
def service():
    mock_settings = MagicMock()
    mock_settings.user_id = "test_user"
    mock_settings.get_setting.return_value = None  # triggers default knowledge graph
    mock_settings.save_setting.return_value = (True, "ok")
    return SupplyChainService(settings_service=mock_settings)

def test_supply_chain_service_init(service):
    assert "NVDA" in service.knowledge_graph
    assert "TSM" in service.knowledge_graph

def test_get_shortage_premium_mag7(service):
    result = service.get_shortage_premium("NVDA")
    assert result["has_premium"] is True
    assert "CoWoS" in result["bottlenecks"]
    assert "TSM" in result["suppliers"]
    assert "Supply Chain Bottleneck Alert" in result["narrative"]

def test_get_shortage_premium_supplier(service):
    result = service.get_shortage_premium("TSM")
    # TSM is both a constraint creator (Packaging) AND a supplier to others
    # Since it's in the graph as a key, it hits the first condition
    assert result["has_premium"] is True
    assert "Packaging Capacity" in result["narrative"]

def test_get_shortage_premium_pure_supplier(service):
    result = service.get_shortage_premium("MU")
    assert result["has_premium"] is True
    assert not result["bottlenecks"]
    assert not result["suppliers"]
    assert "Shortage Premium Beneficiary" in result["narrative"]
    assert "NVDA" in result["narrative"] or "AMD" in result["narrative"]

def test_get_shortage_premium_no_premium(service):
    result = service.get_shortage_premium("KO")
    assert result["has_premium"] is False
    assert not result["bottlenecks"]
    assert not result["suppliers"]
    assert result["narrative"] == ""
