"""
Infrastructure: ConfigFileModelMappingRepository
使用 YAML 配置文件的 Repository 实现
"""
import logging
from typing import Optional, List
from datetime import datetime
import yaml

from ...domain.models.model_mapping import ModelMapping
from ...domain.repositories.model_mapping_repository import IModelMappingRepository

logger = logging.getLogger(__name__)


class ConfigFileModelMappingRepository(IModelMappingRepository):
    """
    使用 YAML 配置文件的 Repository 实现
    
    配置文件格式（models.yaml）：
    ```yaml
    openrouter:
      gemma4:26b: google/gemma-2-27b-it
      qwen-3.6-plus: qwen/qwen-max
      deepseek-v4-flash: deepseek/deepseek-chat
    
    ollama:
      gemma3:4b: gemma3:4b
      qwen2.5:7b: qwen2.5:7b
    ```
    
    用途：
    - 开发环境：快速测试
    - Bootstrap：初始化 Database 数据
    - 降级：Database 故障时的本地备份
    """
    
    def __init__(self, config_path: str):
        """
        Args:
            config_path: YAML 配置文件路径
        """
        self.config_path = config_path
        self.data = {}
        self.last_modified = None
        self._load_config()
    
    def _load_config(self):
        """加载 YAML 配置文件"""
        try:
            with open(self.config_path, 'r') as f:
                self.data = yaml.safe_load(f) or {}
            logger.info(f"Config loaded from {self.config_path}")
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.config_path}")
            self.data = {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.data = {}
    
    async def find(
        self,
        local_model_name: str,
        provider: str,
        user_id: Optional[str] = None
    ) -> Optional[ModelMapping]:
        """
        从配置文件查找映射
        
        注：配置文件不支持用户级映射，始终返回全局映射
        """
        provider_models = self.data.get(provider, {})
        provider_model_id = provider_models.get(local_model_name)
        
        if provider_model_id:
            return ModelMapping(
                local_model_name=local_model_name,
                provider=provider,
                provider_model_id=provider_model_id,
                is_free=False,  # 配置文件中没有 is_free 信息
                created_at=datetime.now(),
                user_id=None  # 配置文件不支持用户级
            )
        return None
    
    async def find_all(
        self,
        provider: str,
        user_id: Optional[str] = None
    ) -> List[ModelMapping]:
        """查找某提供商的所有映射"""
        provider_models = self.data.get(provider, {})
        results = []
        
        for local_name, provider_id in provider_models.items():
            results.append(ModelMapping(
                local_model_name=local_name,
                provider=provider,
                provider_model_id=provider_id,
                is_free=False,
                created_at=datetime.now(),
                user_id=None
            ))
        
        return results
    
    async def find_global(self, provider: str) -> List[ModelMapping]:
        """查找全局映射"""
        return await self.find_all(provider, user_id=None)
    
    async def save(self, mapping: ModelMapping) -> bool:
        """
        配置文件通常是只读的
        如果需要修改，应该手动编辑 YAML 文件
        """
        logger.warning(
            "ConfigFileModelMappingRepository is read-only. "
            "Edit models.yaml manually to update mappings."
        )
        return False
    
    async def delete(
        self,
        local_model_name: str,
        provider: str,
        user_id: Optional[str] = None
    ) -> bool:
        """配置文件不支持删除"""
        logger.warning(
            "ConfigFileModelMappingRepository is read-only. "
            "Edit models.yaml manually to remove mappings."
        )
        return False
    
    async def invalidate_cache(self) -> None:
        """重新加载配置文件"""
        self._load_config()
        logger.info("Config file reloaded")
