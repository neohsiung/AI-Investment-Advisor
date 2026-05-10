"""
Domain Model: ModelMapping
代表模型名称到提供商特定 ID 的映射
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ModelMapping:
    """
    模型映射的域模型
    
    业务规则：
    - local_model_name: 系统内部使用的模型名称
    - provider_model_id: 提供商实际的模型 ID
    - provider: 提供商名称 (openrouter, ollama, nim)
    - is_free: 是否免费模型
    - user_id: 如果设置，这是用户特定的映射（优先级高于全局映射）
    """
    local_model_name: str
    provider: str
    provider_model_id: str
    is_free: bool
    created_at: datetime
    
    # 可选字段
    updated_at: Optional[datetime] = None
    user_id: Optional[str] = None  # 多租户支持
    
    def is_valid(self) -> bool:
        """业务规则检查：映射是否有效"""
        return (
            bool(self.local_model_name.strip()) and
            bool(self.provider_model_id.strip()) and
            self.provider in ['openrouter', 'ollama', 'nim']
        )
    
    def is_user_specific(self) -> bool:
        """是否是用户级映射"""
        return self.user_id is not None
