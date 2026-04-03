"""
Unit tests for UnifiedMemoryService.
"""
import pytest
from unittest.mock import MagicMock
from typing import Dict, List

from src.services.unified_memory_service import UnifiedMemoryService
from src.infrastructure.memory.channel_memory_manager import ChannelMemoryManager
from src.services.settings_service import SettingsService

@pytest.fixture
def mock_memory_manager():
    manager = MagicMock(spec=ChannelMemoryManager)
    
    def mock_get_stm(channel_id, limit):
        if channel_id == "tg123":
            return [
                {"role": "user", "content": "hello tg"},
                {"role": "assistant", "content": "hi tg"}
            ]
        elif channel_id == "line456":
            return [
                {"role": "user", "content": "hello line"}
            ]
        return []
        
    manager.get_short_term_as_messages.side_effect = mock_get_stm
    
    def mock_get_metadata(channel_id, key):
        if channel_id == "tg123" and key == "pending_clarification":
            return "Yes"
        return None
        
    manager.get_metadata.side_effect = mock_get_metadata
    return manager

@pytest.fixture
def mock_settings_service():
    service = MagicMock(spec=SettingsService)
    def mock_get_channels(user_id):
        if user_id == "u1":
            return {"telegram": "tg123", "line": "line456"}
        return {}
    service.get_channel_ids_for_user.side_effect = mock_get_channels
    return service

@pytest.fixture
def unified_service(mock_memory_manager, mock_settings_service):
    return UnifiedMemoryService(mock_memory_manager, mock_settings_service)

def test_get_unified_short_term_multiple_channels(unified_service, mock_memory_manager):
    msgs = unified_service.get_unified_short_term("u1", limit_per_channel=5)
    
    # tg (2 msgs) + line (1 msg) = 3 total msgs
    assert len(msgs) == 3
    
    # Check annotations
    assert msgs[0]["content"] == "[TELEGRAM] hello tg"
    assert msgs[0]["_source_channel"] == "telegram"
    assert msgs[1]["content"] == "[TELEGRAM] hi tg"
    assert msgs[2]["content"] == "[LINE] hello line"
    assert msgs[2]["_source_channel"] == "line"

def test_get_unified_short_term_no_channels(unified_service):
    msgs = unified_service.get_unified_short_term("u2")
    assert msgs == []

def test_get_unified_metadata_found(unified_service):
    val = unified_service.get_unified_metadata("u1", "pending_clarification")
    assert val == "Yes"

def test_get_unified_metadata_not_found(unified_service):
    val = unified_service.get_unified_metadata("u1", "nonexistent")
    assert val is None
