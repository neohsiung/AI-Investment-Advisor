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
            return dict(row._mapping) if row else None

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
            
        return user_uuid

    def get_identities(self, user_id: str) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            query = text("SELECT * FROM user_identities WHERE user_id = :uid")
            rows = conn.execute(query, {"uid": user_id}).fetchall()
            return [dict(r._mapping) for r in rows]

        return user_uuid

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
            query = text("""
                SELECT u.* FROM users u
                JOIN user_identities ui ON u.id = ui.user_id
                WHERE ui.provider = :provider AND ui.identifier = :identifier
            """)
            result = await session.execute(query, {"provider": provider, "identifier": identifier})
            row = result.fetchone()
            return dict(row._mapping) if row else None

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
            
        return user_uuid
