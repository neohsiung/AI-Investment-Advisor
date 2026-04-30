"""
Infrastructure: DatabaseModelMappingRepository
使用 PostgreSQL 的 Repository 实现
"""
import logging
from typing import Optional, List
from datetime import datetime
import psycopg2
from psycopg2.extras import DictCursor

from ...domain.models.model_mapping import ModelMapping
from ...domain.repositories.model_mapping_repository import IModelMappingRepository

logger = logging.getLogger(__name__)


class DatabaseModelMappingRepository(IModelMappingRepository):
    """
    使用 PostgreSQL 存储的 Repository 实现
    
    表结构（已在 provider_model_id_mapping 中）：
    - id: UUID
    - local_model_name: VARCHAR
    - provider: VARCHAR
    - provider_model_id: VARCHAR
    - is_free: BOOLEAN
    - user_id: VARCHAR (nullable) - 用户特定映射
    - created_at: TIMESTAMP
    - updated_at: TIMESTAMP
    """
    
    def __init__(self, db_connection):
        """
        Args:
            db_connection: psycopg2 连接对象
        """
        self.db = db_connection
    
    async def find(
        self,
        local_model_name: str,
        provider: str,
        user_id: Optional[str] = None
    ) -> Optional[ModelMapping]:
        """
        查找映射，优先级：用户级 > 全局
        """
        try:
            cur = self.db.cursor(cursor_factory=DictCursor)
            
            # 如果提供了 user_id，先查用户级映射
            if user_id:
                query = """
                    SELECT * FROM provider_model_id_mapping
                    WHERE local_model_name = %s
                      AND provider = %s
                      AND user_id = %s
                    LIMIT 1
                """
                cur.execute(query, (local_model_name, provider, user_id))
                result = cur.fetchone()
                if result:
                    return self._row_to_model(dict(result), user_id)
            
            # 查全局映射
            query = """
                SELECT * FROM provider_model_id_mapping
                WHERE local_model_name = %s
                  AND provider = %s
                  AND (user_id IS NULL OR user_id = '')
                LIMIT 1
            """
            cur.execute(query, (local_model_name, provider))
            result = cur.fetchone()
            cur.close()
            
            if result:
                return self._row_to_model(dict(result), None)
            
            return None
        
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            return None
    
    async def find_all(
        self,
        provider: str,
        user_id: Optional[str] = None
    ) -> List[ModelMapping]:
        """查找某提供商的所有映射"""
        try:
            cur = self.db.cursor(cursor_factory=DictCursor)
            
            if user_id:
                # 用户级 + 全局
                query = """
                    SELECT * FROM provider_model_id_mapping
                    WHERE provider = %s
                      AND (user_id = %s OR user_id IS NULL OR user_id = '')
                    ORDER BY user_id DESC
                """
                cur.execute(query, (provider, user_id))
            else:
                # 只查全局
                query = """
                    SELECT * FROM provider_model_id_mapping
                    WHERE provider = %s
                      AND (user_id IS NULL OR user_id = '')
                """
                cur.execute(query, (provider,))
            
            results = cur.fetchall()
            cur.close()
            
            return [self._row_to_model(dict(r), user_id) for r in results]
        
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            return []
    
    async def find_global(self, provider: str) -> List[ModelMapping]:
        """查找全局映射（不包括用户级）"""
        return await self.find_all(provider, user_id=None)
    
    async def save(self, mapping: ModelMapping) -> bool:
        """保存或更新映射"""
        try:
            cur = self.db.cursor()
            now = datetime.now()
            
            # 检查是否已存在
            check_query = """
                SELECT id FROM provider_model_id_mapping
                WHERE local_model_name = %s
                  AND provider = %s
                  AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
            """
            cur.execute(check_query, (
                mapping.local_model_name,
                mapping.provider,
                mapping.user_id,
                mapping.user_id
            ))
            exists = cur.fetchone() is not None
            
            if exists:
                # UPDATE
                update_query = """
                    UPDATE provider_model_id_mapping
                    SET provider_model_id = %s,
                        is_free = %s,
                        updated_at = %s
                    WHERE local_model_name = %s
                      AND provider = %s
                      AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
                """
                cur.execute(update_query, (
                    mapping.provider_model_id,
                    mapping.is_free,
                    now,
                    mapping.local_model_name,
                    mapping.provider,
                    mapping.user_id,
                    mapping.user_id
                ))
            else:
                # INSERT
                import uuid
                insert_query = """
                    INSERT INTO provider_model_id_mapping
                    (id, local_model_name, provider, provider_model_id, is_free, user_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cur.execute(insert_query, (
                    str(uuid.uuid4()),
                    mapping.local_model_name,
                    mapping.provider,
                    mapping.provider_model_id,
                    mapping.is_free,
                    mapping.user_id,
                    now,
                    now
                ))
            
            self.db.commit()
            cur.close()
            logger.info(f"Mapping saved: {mapping.local_model_name} → {mapping.provider_model_id}")
            return True
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to save mapping: {e}")
            return False
    
    async def delete(
        self,
        local_model_name: str,
        provider: str,
        user_id: Optional[str] = None
    ) -> bool:
        """删除映射"""
        try:
            cur = self.db.cursor()
            
            delete_query = """
                DELETE FROM provider_model_id_mapping
                WHERE local_model_name = %s
                  AND provider = %s
                  AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
            """
            cur.execute(delete_query, (
                local_model_name,
                provider,
                user_id,
                user_id
            ))
            
            self.db.commit()
            cur.close()
            logger.info(f"Mapping deleted: {local_model_name} on {provider}")
            return True
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete mapping: {e}")
            return False
    
    async def invalidate_cache(self) -> None:
        """Database 没有缓存，这个是空操作"""
        pass
    
    @staticmethod
    def _row_to_model(row: dict, user_id: Optional[str] = None) -> ModelMapping:
        """将数据库行转换为 ModelMapping 对象"""
        return ModelMapping(
            local_model_name=row['local_model_name'],
            provider=row['provider'],
            provider_model_id=row['provider_model_id'],
            is_free=row.get('is_free', False),
            created_at=row['created_at'],
            updated_at=row.get('updated_at'),
            user_id=user_id or row.get('user_id')
        )
