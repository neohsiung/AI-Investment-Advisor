from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine, AsyncBaseRepository, get_async_db_engine
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

class IUserRepository(ABC):
    """
    Interface for User and Identity management.
    使用者與身分官理介面。
    """
    @abstractmethod
    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_by_identity(self, provider: str, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a user by any of their identities (email, line, etc).
        透過任何身分 (Email, LINE 等) 解析使用者。
        """
        pass

    @abstractmethod
    def link_identity(self, user_id: str, provider: str, identifier: str, is_primary: bool = False) -> bool:
        """
        Link a new identity to an existing user.
        將新身分連結至現有使用者。
        """
        pass

    @abstractmethod
    def create_user(self, email: str, name: str = None) -> str:
        """
        Create a new user and return their UUID.
        """
        pass

    @abstractmethod
    def get_all_active_users(self) -> List[str]:
        """
        Returns all real user IDs (excludes test/default accounts).
        """
        pass

class IAsyncUserRepository(ABC):
    """
    Async interface for User and Identity management.
    """
    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_by_identity(self, provider: str, identifier: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def create_user(self, email: str, name: str = None) -> str:
        pass

    @abstractmethod
    async def get_all_active_users(self) -> List[str]:
        pass

class AlchemyUserRepository(BaseRepository, IUserRepository):
    """
    SQLAlchemy implementation of IUserRepository.
    """
    def __init__(self, engine: Any = None):
        BaseRepository.__init__(self, engine or get_db_engine())

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as conn:
            query = text("SELECT * FROM users WHERE id = :uid")
            row = conn.execute(query, {"uid": user_id}).fetchone()
            return dict(row._mapping) if row else None

    def get_by_identity(self, provider: str, identifier: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as conn:
            query = text("""
                SELECT u.* FROM users u
                JOIN user_identities ui ON u.id = ui.user_id
                WHERE ui.provider = :provider AND ui.identifier = :identifier
            """)
            row = conn.execute(query, {"provider": provider, "identifier": identifier}).fetchone()
            if row:
                return dict(row._mapping)

        if provider == "email":
            with self.engine.begin() as conn:
                query_legacy = text("SELECT * FROM users WHERE email = :identifier OR id = :identifier")
                row_legacy = conn.execute(query_legacy, {"identifier": identifier}).fetchone()
                if row_legacy:
                    user_id = row_legacy._mapping["id"]
                    conn.execute(text("""
                        INSERT INTO user_identities (id, user_id, provider, identifier, is_primary)
                        VALUES (:id, :user_id, 'email', :identifier, 1)
                    """), {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "identifier": identifier
                    })
                    return dict(row_legacy._mapping)

        return None

    def link_identity(self, user_id: str, provider: str, identifier: str, is_primary: bool = False) -> bool:
        with self.engine.begin() as conn:
            # Check if exists
            check = conn.execute(text("SELECT 1 FROM user_identities WHERE provider = :p AND identifier = :i"), 
                                {"p": provider, "i": identifier}).fetchone()
            if check:
                return False
            
            query = text("""
                INSERT INTO user_identities (id, user_id, provider, identifier, is_primary)
                VALUES (:id, :user_id, :provider, :identifier, :is_primary)
            """)
            conn.execute(query, {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "provider": provider,
                "identifier": identifier,
                "is_primary": 1 if is_primary else 0
            })
            return True

    def create_user(self, email: str, name: str = None) -> str:
        user_uuid = str(uuid.uuid4())
        with self.engine.begin() as conn:
            # 1. Create User
            conn.execute(
                text("INSERT INTO users (id, email, name) VALUES (:id, :email, :name)"),
                {"id": user_uuid, "email": email, "name": name or email}
            )
            
            # 2. Link primary email identity
            conn.execute(text("""
                INSERT INTO user_identities (id, user_id, provider, identifier, is_primary)
                VALUES (:id, :user_id, 'email', :identifier, 1)
            """), {
                "id": str(uuid.uuid4()),
                "user_id": user_uuid,
                "identifier": email
            })
        
        # v9.1: Seed LLM defaults for new user
        try:
            from src.services.llm_onboarding_service import LLMOnboardingService
            LLMOnboardingService().seed_defaults_for_user(user_uuid)
        except Exception as e:
            # Don't fail the whole user creation if seeding fails, but log it.
            import logging
            logging.getLogger(__name__).error(f"Failed to seed LLM defaults for new user {user_uuid}: {e}")

        return user_uuid

    def get_identities(self, user_id: str) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT provider, identifier, is_primary FROM user_identities WHERE user_id = :uid"),
                {"uid": user_id}
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    def get_all_active_users(self) -> List[str]:
        """
        Returns all real user IDs (excludes test/default accounts).
        B2C 多租戶排程器使用，不依賴 ENV。
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id FROM users "
                "WHERE email NOT LIKE 'test%' "
                "AND email NOT LIKE '%@example.com' "
                "AND id != 'default' "
                "ORDER BY created_at ASC"
            )).fetchall()
        return [row[0] for row in rows]

class AsyncAlchemyUserRepository(AsyncBaseRepository, IAsyncUserRepository):
    """
    Async SQLAlchemy implementation of IUserRepository.
    v8.0: High-performance non-blocking implementation.
    """
    def __init__(self, engine: Any = None):
        AsyncBaseRepository.__init__(self, engine or get_async_db_engine())

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        async with await self.get_session() as session:
            query = text("SELECT * FROM users WHERE id = :uid")
            result = await session.execute(query, {"uid": user_id})
            row = result.fetchone()
            return dict(row._mapping) if row else None

    async def get_by_identity(self, provider: str, identifier: str) -> Optional[Dict[str, Any]]:
        async with await self.get_session() as session:
            # 1. 嘗試標準身份對應 (New UUID System)
            query = text("""
                SELECT u.* FROM users u
                JOIN user_identities ui ON u.id = ui.user_id
                WHERE ui.provider = :provider AND ui.identifier = :identifier
            """)
            result = await session.execute(query, {"provider": provider, "identifier": identifier})
            row = result.fetchone()
            if row:
                return dict(row._mapping)

            # 2. Legacy / Existing email check:
            # 如果是 Email 登入且沒找到與之關聯的 Identity，檢查 Users 表是否存在 email == identifier 或 id == identifier
            if provider == "email":
                query_legacy = text("SELECT * FROM users WHERE email = :identifier OR id = :identifier")
                res_legacy = await session.execute(query_legacy, {"identifier": identifier})
                row_legacy = res_legacy.fetchone()
                if row_legacy:
                    # 發現已有帳號但未關聯 Identity！主動建立身份連結，確保下次登入一致
                    user_id = row_legacy._mapping["id"]
                    await session.execute(text("""
                        INSERT INTO user_identities (id, user_id, provider, identifier, is_primary)
                        VALUES (:id, :uid, 'email', :identifier, 1)
                    """), {
                        "id": str(uuid.uuid4()),
                        "uid": user_id,
                        "identifier": identifier
                    })
                    await session.commit()
                    return dict(row_legacy._mapping)

            return None

    async def create_user(self, email: str, name: str = None) -> str:
        user_uuid = str(uuid.uuid4())
        async with await self.get_session() as session:
            # 1. Create User
            await session.execute(
                text("INSERT INTO users (id, email, name) VALUES (:id, :email, :name)"),
                {"id": user_uuid, "email": email, "name": name or email}
            )
            
            # 2. Link primary email identity
            await session.execute(text("""
                INSERT INTO user_identities (id, user_id, provider, identifier, is_primary)
                VALUES (:id, :user_id, 'email', :identifier, 1)
            """), {
                "id": str(uuid.uuid4()),
                "user_id": user_uuid,
                "identifier": email
            })
            await session.commit()
            
        # v9.1: Seed LLM defaults for new user (Async)
        try:
            from src.services.llm_onboarding_service import LLMOnboardingService
            await LLMOnboardingService().async_seed_defaults_for_user(user_uuid)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to async seed LLM defaults for new user {user_uuid}: {e}")

        return user_uuid

    async def get_all_active_users(self) -> List[str]:
        """
        Async version of get_all_active_users.
        """
        async with await self.get_session() as session:
            result = await session.execute(text(
                "SELECT id FROM users "
                "WHERE email NOT LIKE 'test%' "
                "AND email NOT LIKE '%@example.com' "
                "AND id != 'default'"
            ))
            rows = result.fetchall()
            return [row[0] for row in rows]
