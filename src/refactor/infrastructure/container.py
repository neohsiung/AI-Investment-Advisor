"""
Infrastructure: DI Container
依赖注入容器，管理 Repository 和 Service 的创建和生命周期
"""
import os
import logging
from typing import Optional

from ...domain.repositories.model_mapping_repository import IModelMappingRepository
from ...domain.services.model_mapping_service import ModelMappingService
from .database_model_mapping_repository import DatabaseModelMappingRepository
from .config_file_model_mapping_repository import ConfigFileModelMappingRepository

logger = logging.getLogger(__name__)


class DIContainer:
    """
    依赖注入容器
    
    使用方式：
        container = DIContainer(environment='production')
        service = container.get_model_mapping_service()
    """
    
    def __init__(
        self,
        environment: Optional[str] = None,
        db_connection=None,
        config_path: str = 'models.yaml',
        cache_ttl: int = 3600
    ):
        """
        Args:
            environment: 运行环境 ('production', 'staging', 'development')
            db_connection: PostgreSQL 连接对象（生产环境使用）
            config_path: 配置文件路径（开发/测试使用）
            cache_ttl: Service 缓存过期时间（秒）
        """
        self.environment = environment or os.environ.get('ENVIRONMENT', 'development')
        self.db_connection = db_connection
        self.config_path = config_path
        self.cache_ttl = cache_ttl
        
        # 单例实例（延迟创建）
        self._repository: Optional[IModelMappingRepository] = None
        self._service: Optional[ModelMappingService] = None
        
        logger.info(f"DIContainer initialized for {self.environment} environment")
    
    def get_repository(self) -> IModelMappingRepository:
        """
        获取 Repository 实例
        
        选择逻辑：
        - production: DatabaseModelMappingRepository（PostgreSQL）
        - staging: DatabaseModelMappingRepository（PostgreSQL）
        - development/testing: ConfigFileModelMappingRepository（YAML）
        """
        if self._repository is not None:
            return self._repository
        
        if self.environment in ['production', 'staging']:
            if self.db_connection is None:
                raise ValueError("db_connection is required for production environment")
            self._repository = DatabaseModelMappingRepository(self.db_connection)
            logger.info("Using DatabaseModelMappingRepository")
        else:
            # 开发/测试环境
            self._repository = ConfigFileModelMappingRepository(self.config_path)
            logger.info(f"Using ConfigFileModelMappingRepository ({self.config_path})")
        
        return self._repository
    
    def get_model_mapping_service(self) -> ModelMappingService:
        """获取 ModelMappingService 实例"""
        if self._service is not None:
            return self._service
        
        repository = self.get_repository()
        self._service = ModelMappingService(
            repository=repository,
            cache_ttl=self.cache_ttl,
            max_cache_size=1000
        )
        logger.info("ModelMappingService instance created")
        return self._service


# 全局 DI 容器实例（仅供参考，实际应该通过依赖注入传递）
_global_container: Optional[DIContainer] = None


def init_global_container(
    environment: Optional[str] = None,
    db_connection=None,
    config_path: str = 'models.yaml'
) -> DIContainer:
    """初始化全局容器"""
    global _global_container
    _global_container = DIContainer(
        environment=environment,
        db_connection=db_connection,
        config_path=config_path
    )
    return _global_container


def get_global_container() -> DIContainer:
    """获取全局容器"""
    if _global_container is None:
        raise RuntimeError("Global container not initialized. Call init_global_container() first.")
    return _global_container
