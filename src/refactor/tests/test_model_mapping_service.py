"""
Unit Tests: ModelMappingService
测试缓存、Fallback、多租户等核心功能
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

# 假设导入路径
from src.domain.models.model_mapping import ModelMapping
from src.domain.services.model_mapping_service import ModelMappingService


class MockRepository:
    """Mock Repository 用于单元测试"""
    
    def __init__(self, mappings: dict = None):
        self.mappings = mappings or {}
        self.calls = []
    
    async def find(self, local_model_name, provider, user_id=None):
        self.calls.append(('find', local_model_name, provider, user_id))
        
        # 模拟查询逻辑
        key = f"{user_id or 'global'}:{provider}:{local_model_name}"
        if key in self.mappings:
            return self.mappings[key]
        return None
    
    async def invalidate_cache(self):
        pass


class TestModelMappingService:
    
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """测试缓存命中：第二次查询不应该调用 Repository"""
        mock_repo = MockRepository({
            'global:openrouter:gemma4:26b': ModelMapping(
                local_model_name='gemma4:26b',
                provider='openrouter',
                provider_model_id='google/gemma-2-27b-it',
                is_free=False,
                created_at=datetime.now()
            )
        })
        
        service = ModelMappingService(mock_repo, cache_ttl=3600)
        
        # 第一次查询
        result1 = await service.get_provider_model_id('gemma4:26b', 'openrouter')
        assert result1 == 'google/gemma-2-27b-it'
        assert len(mock_repo.calls) == 1
        
        # 第二次查询（应该使用缓存）
        result2 = await service.get_provider_model_id('gemma4:26b', 'openrouter')
        assert result2 == 'google/gemma-2-27b-it'
        assert len(mock_repo.calls) == 1  # Repository 没有被调用
    
    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self):
        """测试多租户隔离：不同用户应该有独立的映射"""
        mock_repo = MockRepository({
            'user1:openrouter:gemma4:26b': ModelMapping(
                local_model_name='gemma4:26b',
                provider='openrouter',
                provider_model_id='user1-custom-gemma',
                is_free=False,
                created_at=datetime.now(),
                user_id='user1'
            ),
            'global:openrouter:gemma4:26b': ModelMapping(
                local_model_name='gemma4:26b',
                provider='openrouter',
                provider_model_id='google/gemma-2-27b-it',
                is_free=False,
                created_at=datetime.now()
            )
        })
        
        service = ModelMappingService(mock_repo)
        
        # User 1 应该得到自己的映射
        result_user1 = await service.get_provider_model_id(
            'gemma4:26b', 'openrouter', user_id='user1'
        )
        assert result_user1 == 'user1-custom-gemma'
        
        # User 2 应该得到全局映射
        result_user2 = await service.get_provider_model_id(
            'gemma4:26b', 'openrouter', user_id='user2'
        )
        assert result_user2 == 'google/gemma-2-27b-it'
    
    @pytest.mark.asyncio
    async def test_fallback_when_not_found(self):
        """测试 Fallback：映射不存在时返回原名称"""
        mock_repo = MockRepository({})  # 空映射
        service = ModelMappingService(mock_repo)
        
        # 不存在的映射应该 Fallback 到原名称
        result = await service.get_provider_model_id('unknown-model', 'openrouter')
        assert result == 'unknown-model'
    
    @pytest.mark.asyncio
    async def test_force_refresh(self):
        """测试强制刷新：跳过缓存重新查询"""
        mock_repo = MockRepository({
            'global:openrouter:gemma4:26b': ModelMapping(
                local_model_name='gemma4:26b',
                provider='openrouter',
                provider_model_id='google/gemma-2-27b-it',
                is_free=False,
                created_at=datetime.now()
            )
        })
        
        service = ModelMappingService(mock_repo)
        
        # 第一次查询（缓存）
        await service.get_provider_model_id('gemma4:26b', 'openrouter')
        assert len(mock_repo.calls) == 1
        
        # 强制刷新
        await service.get_provider_model_id(
            'gemma4:26b', 'openrouter', force_refresh=True
        )
        assert len(mock_repo.calls) == 2  # Repository 被调用了
    
    def test_cache_stats(self):
        """测试缓存统计"""
        mock_repo = MockRepository()
        service = ModelMappingService(mock_repo, cache_ttl=3600, max_cache_size=100)
        
        stats = service.get_cache_stats()
        assert stats['size'] == 0
        assert stats['max_size'] == 100
        assert stats['ttl_seconds'] == 3600


# 运行测试
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
