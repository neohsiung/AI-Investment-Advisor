"""
Domain Repository Interface
定义数据访问的抽象接口
"""
from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import datetime

from ..models.model_mapping import ModelMapping


class IModelMappingRepository(ABC):
    """
    Repository 接口：模型映射的数据访问层抽象
    
    实现类可以使用不同的数据源：
    - DatabaseModelMappingRepository: PostgreSQL
    - ConfigFileModelMappingRepository: YAML 配置文件
    - InMemoryModelMappingRepository: 单元测试用
    """
    
    @abstractmethod
    async def find(
        self,
        local_model_name: str,
        provider: str,
        user_id: Optional[str] = None
    ) -> Optional[ModelMapping]:
        """
        查找单条映射
        
        查询优先级：
        1. 如果 user_id 提供，先查用户级映射
        2. 不存在则查全局映射（user_id = NULL）
        3. 都不存在返回 None
        
        Args:
            local_model_name: 本地模型名称
            provider: 提供商名称
            user_id: 用户ID（可选）
        
        Returns:
            ModelMapping 对象或 None
        """
        pass
    
    @abstractmethod
    async def find_all(
        self,
        provider: str,
        user_id: Optional[str] = None
    ) -> List[ModelMapping]:
        """查找某提供商的所有映射（用户级或全局）"""
        pass
    
    @abstractmethod
    async def find_global(self, provider: str) -> List[ModelMapping]:
        """查找全局映射（不包括用户级）"""
        pass
    
    @abstractmethod
    async def save(self, mapping: ModelMapping) -> bool:
        """保存或更新映射"""
        pass
    
    @abstractmethod
    async def delete(
        self,
        local_model_name: str,
        provider: str,
        user_id: Optional[str] = None
    ) -> bool:
        """删除映射"""
        pass
    
    @abstractmethod
    async def invalidate_cache(self) -> None:
        """
        清空缓存（如果实现有缓存的话）
        在批量更新映射后调用
        """
        pass
