"""
Generated Code Repository
=========================
Database persistence layer for autonomous code synthesis artifacts, AST audits,
and 14-day canary shadow tracking cycles.
提供系統自主生成量化代碼、AST 審計指標、金絲雀灰度日誌之資料持久化存取。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.data.database import BaseRepository, get_db_engine
from src.data.models import GeneratedCodeArtifact

logger = logging.getLogger(__name__)


class GeneratedCodeRepository(BaseRepository):
    """
    CRUD repository for GeneratedCodeArtifact table.
    """

    def __init__(self, engine: Any = None):
        super().__init__(engine or get_db_engine())

    def save_artifact(
        self,
        artifact_id: str,
        user_id: str,
        name: str,
        description: str,
        source_code: str,
        test_code: str,
        ast_hash: str,
        status: str,
        parameters: Optional[Dict[str, Any]] = None,
        backtest_metrics: Optional[Dict[str, Any]] = None,
        ast_metrics: Optional[Dict[str, Any]] = None,
        shadow_days_remaining: int = 14,
        shadow_tracking_log: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[GeneratedCodeArtifact]:
        """
        Create or update a generated code artifact record.
        """
        session = self.session
        try:
            row = session.query(GeneratedCodeArtifact).filter(
                GeneratedCodeArtifact.id == artifact_id
            ).first()

            if not row:
                row = GeneratedCodeArtifact(
                    id=artifact_id,
                    user_id=user_id,
                    name=name,
                    description=description,
                    source_code=source_code,
                    test_code=test_code,
                    ast_hash=ast_hash,
                    status=status,
                    parameters=parameters or {},
                    backtest_metrics=backtest_metrics or {},
                    ast_metrics=ast_metrics or {},
                    shadow_days_remaining=shadow_days_remaining,
                    shadow_tracking_log=shadow_tracking_log or [],
                )
                session.add(row)
            else:
                row.name = name
                row.description = description
                row.source_code = source_code
                row.test_code = test_code
                row.ast_hash = ast_hash
                row.status = status
                row.parameters = parameters or {}
                row.backtest_metrics = backtest_metrics or {}
                row.ast_metrics = ast_metrics or {}
                row.shadow_days_remaining = shadow_days_remaining
                row.shadow_tracking_log = shadow_tracking_log or []
                row.updated_at = datetime.now(timezone.utc)

            session.commit()
            session.refresh(row)
            return row
        except Exception as e:
            session.rollback()
            logger.error("Failed to save GeneratedCodeArtifact %s: %s", artifact_id, e, exc_info=True)
            raise
        finally:
            session.close()

    def get_artifact(self, artifact_id: str) -> Optional[GeneratedCodeArtifact]:
        """
        Retrieve a single artifact by primary key ID.
        """
        session = self.session
        try:
            return session.query(GeneratedCodeArtifact).filter(
                GeneratedCodeArtifact.id == artifact_id
            ).first()
        except Exception as e:
            logger.error("Failed to get GeneratedCodeArtifact %s: %s", artifact_id, e, exc_info=True)
            return None
        finally:
            session.close()

    def list_artifacts(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[GeneratedCodeArtifact]:
        """
        List artifacts with optional user_id and status filters.
        """
        session = self.session
        try:
            query = session.query(GeneratedCodeArtifact)
            if user_id:
                query = query.filter(GeneratedCodeArtifact.user_id == user_id)
            if status:
                query = query.filter(GeneratedCodeArtifact.status == status)
            return query.order_by(GeneratedCodeArtifact.created_at.desc()).all()
        except Exception as e:
            logger.error("Failed to list GeneratedCodeArtifacts: %s", e, exc_info=True)
            return []
        finally:
            session.close()

    def update_lifecycle(
        self,
        artifact_id: str,
        status: str,
        shadow_days_remaining: Optional[int] = None,
        shadow_tracking_log: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Update the lifecycle status and shadow tracking state of an artifact.
        """
        session = self.session
        try:
            row = session.query(GeneratedCodeArtifact).filter(
                GeneratedCodeArtifact.id == artifact_id
            ).first()
            if not row:
                return False

            row.status = status
            if shadow_days_remaining is not None:
                row.shadow_days_remaining = shadow_days_remaining
            if shadow_tracking_log is not None:
                row.shadow_tracking_log = shadow_tracking_log
            row.updated_at = datetime.now(timezone.utc)

            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error("Failed to update lifecycle for %s: %s", artifact_id, e, exc_info=True)
            return False
        finally:
            session.close()
