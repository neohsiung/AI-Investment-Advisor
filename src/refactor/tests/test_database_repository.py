"""
Integration Tests: DatabaseModelMappingRepository
测试与真实数据库的交互
"""
import pytest
import asyncio
from datetime import datetime

from src.domain.models.model_mapping import ModelMapping
from src.infrastructure.repositories.database_model_mapping_repository import DatabaseModelMappingRepository


@pytest.fixture
async def db_repo(test_db_connection):
    """提供测试用的 Repository 实例"""
    repo = DatabaseModelMappingRepository(test_db_connection)
    # 清空测试数据
    yield repo
    # 清理


class TestDatabaseModelMappingRepository:
    
    @pytest.mark.asyncio
    async def test_save_and_find(self, db_repo):
        """测试保存和查询"""
        mapping = ModelMapping(
            local_model_name='gemma4:26b',
            provider='openrouter',
            provider_model_id='google/gemma-2-27b-it',
            is_free=False,
            created_at=datetime.now()
        )
        
        # 保存
        assert await db_repo.save(mapping)
        
        # 查询
        found = await db_repo.find('gemma4:26b', 'openrouter')
        assert found is not None
        assert found.provider_model_id == 'google/gemma-2-27b-it'
    
    @pytest.mark.asyncio
    async def test_user_level_priority(self, db_repo):
        """测试用户级映射优先级"""
        # 保存全局映射
        global_mapping = ModelMapping(
            local_model_name='gemma4:26b',
            provider='openrouter',
            provider_model_id='global-gemma',
            is_free=False,
            created_at=datetime.now()
        )
        await db_repo.save(global_mapping)
        
        # 保存用户级映射
        user_mapping = ModelMapping(
            local_model_name='gemma4:26b',
            provider='openrouter',
            provider_model_id='user-custom-gemma',
            is_free=False,
            created_at=datetime.now(),
            user_id='user123'
        )
        await db_repo.save(user_mapping)
        
        # 查询应该返回用户级映射
        found = await db_repo.find('gemma4:26b', 'openrouter', user_id='user123')
        assert found.provider_model_id == 'user-custom-gemma'
        
        # 查询不同用户应该返回全局映射
        found_other = await db_repo.find('gemma4:26b', 'openrouter', user_id='other_user')
        assert found_other.provider_model_id == 'global-gemma'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
