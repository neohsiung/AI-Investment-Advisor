"""
Domain Service: ModelMappingService
模型映射的业务逻辑和缓存管理
"""
import time
import logging
from typing import Optional

from ..models.model_mapping import ModelMapping
from ..repositories.model_mapping_repository import IModelMappingRepository

logger = logging.getLogger(__name__)


class ModelMappingService:
    """
    Domain Service：模型映射的业务逻辑层
    
    职责：
    1. 缓存管理（LRU + TTL）
    2. Fallback 策略（映射不存在时）
    3. 多租户支持（用户级 > 全局优先级）
    4. 业务规则验证
    
    好处：
    - Gateway 不需要知道数据源细节
    - 测试时可以 mock Repository
    - 缓存逻辑集中管理
    """
    
    def __init__(
        self,
        repository: IModelMappingRepository,
        cache_ttl: int = 3600,
        max_cache_size: int = 1000
    ):
        """
        Args:
            repository: 数据访问实现
            cache_ttl: 缓存过期时间（秒），默认 1 小时
            max_cache_size: 缓存最大条数（简单 LRU）
        """
        self.repo = repository
        self.cache_ttl = cache_ttl
        self.max_cache_size = max_cache_size
        
        # 缓存格式: {cache_key: (value, timestamp)}
        self._cache = {}
        self._access_times = {}  # LRU 追踪
    
    def _get_cache_key(
        self,
        local_model_name: str,
        provider: str,
        user_id: Optional[str] = None
    ) -> str:
        """生成缓存键"""
        user_part = user_id or 'global'
        return f"{user_part}:{provider}:{local_model_name}"
    
    def _is_cache_valid(self, timestamp: float) -> bool:
        """检查缓存是否过期"""
        return (time.time() - timestamp) < self.cache_ttl
    
    def _evict_lru_if_needed(self) -> None:
        """如果缓存满了，删除最少使用的项"""
        if len(self._cache) >= self.max_cache_size:
            # 找出最少使用的键
            lru_key = min(self._access_times.items(), key=lambda x: x[1])[0]
            del self._cache[lru_key]
            del self._access_times[lru_key]
    
    async def get_provider_model_id(
        self,
        local_model_name: str,
        provider: str,
        user_id: Optional[str] = None,
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> str:
        """
        获取提供商的实际模型 ID
        
        策略（按顺序）：
        1. 检查缓存（如果 use_cache=True 且未过期）
        2. 向 Repository 查询（用户级 > 全局）
        3. Fallback 返回原名称
        
        Args:
            local_model_name: 本地模型名称
            provider: 提供商名称
            user_id: 用户ID（可选）
            use_cache: 是否使用缓存
            force_refresh: 强制刷新（跳过缓存）
        
        Returns:
            提供商的实际模型 ID，或本地名称（如果映射不存在）
        """
        cache_key = self._get_cache_key(local_model_name, provider, user_id)
        
        # Step 1: 检查缓存
        if use_cache and not force_refresh and cache_key in self._cache:
            cached_value, timestamp = self._cache[cache_key]
            if self._is_cache_valid(timestamp):
                # 更新 LRU 访问时间
                self._access_times[cache_key] = time.time()
                logger.debug(f"Cache hit: {cache_key} → {cached_value}")
                return cached_value
            else:
                # 缓存过期，删除
                del self._cache[cache_key]
                del self._access_times[cache_key]
        
        # Step 2: 查询 Repository
        try:
            mapping = await self.repo.find(local_model_name, provider, user_id)
            if mapping and mapping.is_valid():
                provider_id = mapping.provider_model_id
                
                # 更新缓存
                self._evict_lru_if_needed()
                self._cache[cache_key] = (provider_id, time.time())
                self._access_times[cache_key] = time.time()
                
                logger.info(
                    f"Model mapping: {local_model_name} "
                    f"({provider}) → {provider_id} "
                    f"(user_id={user_id})"
                )
                return provider_id
        except Exception as e:
            logger.error(f"Repository lookup failed: {e}")
        
        # Step 3: Fallback 返回原名称
        logger.warning(
            f"No mapping found for {local_model_name} on {provider}, "
            f"using fallback name"
        )
        
        # 缓存 fallback 结果（避免重复查询）
        self._cache[cache_key] = (local_model_name, time.time())
        self._access_times[cache_key] = time.time()
        
        return local_model_name
    
    def invalidate_cache(self, user_id: Optional[str] = None) -> None:
        """
        清空缓存
        
        Args:
            user_id: 如果指定，只清空该用户的缓存；否则清空全部
        """
        if user_id is None:
            self._cache.clear()
            self._access_times.clear()
            logger.info("Cache cleared (all users)")
        else:
            # 清空指定用户的缓存
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(f"{user_id}:")]
            for key in keys_to_delete:
                del self._cache[key]
                del self._access_times[key]
            logger.info(f"Cache cleared for user {user_id}")
    
    def get_cache_stats(self) -> dict:
        """获取缓存统计信息（用于监控）"""
        return {
            "size": len(self._cache),
            "max_size": self.max_cache_size,
            "ttl_seconds": self.cache_ttl,
            "keys": list(self._cache.keys())
        }
