import pytest
from unittest.mock import MagicMock, patch
from src.repositories.user_repository import AlchemyUserRepository
from src.infrastructure.tasks import _resolve_target_users

def test_user_repository_get_first_user_id():
    with patch.object(AlchemyUserRepository, 'get_all_active_users', return_value=['user-uuid-1', 'user-uuid-2']):
        repo = AlchemyUserRepository(engine=MagicMock())
        assert repo.get_first_user_id() == 'user-uuid-1'

def test_user_repository_get_first_user_id_empty():
    with patch.object(AlchemyUserRepository, 'get_all_active_users', return_value=[]):
        repo = AlchemyUserRepository(engine=MagicMock())
        assert repo.get_first_user_id() is None

def test_resolve_target_users_explicit():
    assert _resolve_target_users('explicit-user-id') == ['explicit-user-id']

def test_resolve_target_users_from_db():
    with patch.object(AlchemyUserRepository, 'get_all_active_users', return_value=['user-1', 'user-2']):
        assert _resolve_target_users() == ['user-1', 'user-2']

def test_resolve_target_users_fallback_env(monkeypatch):
    monkeypatch.setenv("PRIMARY_USER_ID", "env-user-id")
    with patch.object(AlchemyUserRepository, 'get_all_active_users', return_value=[]):
        assert _resolve_target_users() == ['env-user-id']
