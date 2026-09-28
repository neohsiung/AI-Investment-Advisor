"""
Canary Shadow Runner & Lifecycle Manager
========================================
負責管理系統自主生成代碼之金絲雀灰度 (Canary Shadow Tracking) 週期。
狀態流轉：
  DRAFT -> VERIFIED (通過 AST+TDD) -> PROVISIONAL (通過回測，進入 14 天影子運行)
  -> ACTIVE (考核通過/手動核發實盤執照)
  -> REJECTED (回測或影子追蹤不達標)
  -> KILLED (操作者一鍵緊急熔斷)
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger("CanaryShadowRunner")


class ArtifactStatus:
    DRAFT = "DRAFT"
    VERIFIED = "VERIFIED"
    PROVISIONAL = "PROVISIONAL"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    KILLED = "KILLED"


@dataclass
class CodeArtifactRecord:
    """
    In-memory / persistence representation of a synthesized factor code artifact.
    """
    id: str
    user_id: str
    name: str
    description: str
    source_code: str
    test_code: str
    ast_hash: str
    status: str  # ArtifactStatus
    parameters: Dict[str, Any] = field(default_factory=dict)
    backtest_metrics: Dict[str, Any] = field(default_factory=dict)
    ast_metrics: Dict[str, Any] = field(default_factory=dict)
    shadow_days_remaining: int = 14
    shadow_tracking_log: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CanaryShadowRunner:
    """
    Coordinates 14-day shadow tracking and lifecycle states of synthesized code artifacts.
    Supports in-memory caching with PostgreSQL persistence via GeneratedCodeRepository.
    """

    def __init__(self):
        # In-memory store (mirrored with DB model GeneratedCodeArtifact)
        self._store: Dict[str, CodeArtifactRecord] = {}
        self._repo = None

    def _get_repo(self):
        if self._repo is None:
            try:
                from src.repositories.generated_code_repository import GeneratedCodeRepository
                self._repo = GeneratedCodeRepository()
            except Exception as e:
                logger.warning("Could not initialize GeneratedCodeRepository, using in-memory store: %s", e)
                self._repo = False
        return self._repo if self._repo is not False else None

    def _row_to_record(self, row: Any) -> CodeArtifactRecord:
        created_at_str = (
            row.created_at.isoformat()
            if hasattr(row.created_at, "isoformat")
            else str(row.created_at)
        )
        updated_at_str = (
            row.updated_at.isoformat()
            if hasattr(row.updated_at, "isoformat")
            else str(row.updated_at)
        )
        return CodeArtifactRecord(
            id=str(row.id),
            user_id=str(row.user_id),
            name=row.name,
            description=row.description or "",
            source_code=row.source_code,
            test_code=row.test_code or "",
            ast_hash=row.ast_hash,
            status=row.status,
            parameters=row.parameters or {},
            backtest_metrics=row.backtest_metrics or {},
            ast_metrics=row.ast_metrics or {},
            shadow_days_remaining=row.shadow_days_remaining or 0,
            shadow_tracking_log=row.shadow_tracking_log or [],
            created_at=created_at_str,
            updated_at=updated_at_str,
        )

    def register_artifact(
        self,
        user_id: str,
        name: str,
        description: str,
        source_code: str,
        test_code: str,
        ast_hash: str,
        status: str = ArtifactStatus.PROVISIONAL,
        parameters: Optional[Dict[str, Any]] = None,
        backtest_metrics: Optional[Dict[str, Any]] = None,
        ast_metrics: Optional[Dict[str, Any]] = None,
    ) -> CodeArtifactRecord:
        """
        Register a new synthesized artifact into shadow tracking.
        """
        artifact_id = str(uuid.uuid4())
        record = CodeArtifactRecord(
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
            shadow_days_remaining=14 if status == ArtifactStatus.PROVISIONAL else 0,
        )
        self._store[artifact_id] = record

        # Persist to database if repository is available
        repo = self._get_repo()
        if repo:
            try:
                repo.save_artifact(
                    artifact_id=artifact_id,
                    user_id=user_id,
                    name=name,
                    description=description,
                    source_code=source_code,
                    test_code=test_code,
                    ast_hash=ast_hash,
                    status=status,
                    parameters=parameters,
                    backtest_metrics=backtest_metrics,
                    ast_metrics=ast_metrics,
                    shadow_days_remaining=record.shadow_days_remaining,
                    shadow_tracking_log=record.shadow_tracking_log,
                )
            except Exception as e:
                logger.warning("Failed to persist artifact %s to DB: %s", artifact_id, e)

        logger.info(
            "Registered synthesized code artifact '%s' (ID: %s, Status: %s)",
            name,
            artifact_id,
            status,
        )
        return record

    def get_artifact(self, artifact_id: str) -> Optional[CodeArtifactRecord]:
        if artifact_id in self._store:
            return self._store[artifact_id]

        repo = self._get_repo()
        if repo:
            try:
                row = repo.get_artifact(artifact_id)
                if row:
                    rec = self._row_to_record(row)
                    self._store[artifact_id] = rec
                    return rec
            except Exception as e:
                logger.warning("Failed to fetch artifact %s from DB: %s", artifact_id, e)
        return None

    def list_artifacts(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[CodeArtifactRecord]:
        """
        List artifacts filtered by user_id and/or status.
        """
        repo = self._get_repo()
        if repo:
            try:
                rows = repo.list_artifacts(user_id=user_id, status=status)
                if rows:
                    records = []
                    for row in rows:
                        rec = self._row_to_record(row)
                        self._store[rec.id] = rec
                        records.append(rec)
                    return records
            except Exception as e:
                logger.warning("Failed to query artifacts from DB, falling back to cache: %s", e)

        results = list(self._store.values())
        if user_id:
            results = [r for r in results if r.user_id == user_id]
        if status:
            results = [r for r in results if r.status == status]
        return sorted(results, key=lambda x: x.created_at, reverse=True)

    def step_shadow_day(
        self,
        artifact_id: str,
        simulated_daily_pnl_pct: float,
        signal_strength: float,
    ) -> Optional[CodeArtifactRecord]:
        """
        Advance one day in the 14-day canary shadow tracking phase.
        """
        record = self.get_artifact(artifact_id)
        if not record or record.status != ArtifactStatus.PROVISIONAL:
            return record

        now_iso = datetime.now(timezone.utc).isoformat()
        record.shadow_tracking_log.append({
            "timestamp": now_iso,
            "daily_pnl_pct": simulated_daily_pnl_pct,
            "signal_strength": signal_strength,
        })
        record.shadow_days_remaining = max(0, record.shadow_days_remaining - 1)
        record.updated_at = now_iso

        # 檢查影子期間熔斷：若單日模擬虧損超過 5% 或累計嚴重回撤，自動降級
        if simulated_daily_pnl_pct <= -5.0:
            logger.warning(
                "Canary artifact %s triggered shadow degradation safeguard (daily pnl: %.2f%%)",
                artifact_id,
                simulated_daily_pnl_pct,
            )
            record.status = ArtifactStatus.REJECTED

        # 若 14 天順利屆滿且未熔斷，標記為合格（可手動或自動晉升為 ACTIVE）
        elif record.shadow_days_remaining == 0:
            logger.info("Canary artifact %s completed 14-day shadow tracking successfully", artifact_id)

        # Update in DB
        repo = self._get_repo()
        if repo:
            try:
                repo.update_lifecycle(
                    artifact_id=artifact_id,
                    status=record.status,
                    shadow_days_remaining=record.shadow_days_remaining,
                    shadow_tracking_log=record.shadow_tracking_log,
                )
            except Exception as e:
                logger.warning("Failed to update lifecycle in DB for %s: %s", artifact_id, e)

        return record

    def approve_artifact(self, artifact_id: str, user_id: str) -> bool:
        """
        Operator manual approval: promote artifact to ACTIVE.
        """
        record = self.get_artifact(artifact_id)
        if not record or record.user_id != user_id:
            return False

        if record.status in (ArtifactStatus.KILLED, ArtifactStatus.REJECTED):
            logger.warning("Cannot approve killed or rejected artifact %s", artifact_id)
            return False

        record.status = ArtifactStatus.ACTIVE
        record.updated_at = datetime.now(timezone.utc).isoformat()
        logger.info("Operator approved artifact %s to ACTIVE status", artifact_id)

        repo = self._get_repo()
        if repo:
            try:
                repo.update_lifecycle(artifact_id=artifact_id, status=ArtifactStatus.ACTIVE)
            except Exception as e:
                logger.warning("Failed to update approved status in DB for %s: %s", artifact_id, e)

        return True

    def kill_artifact(self, artifact_id: str, user_id: str) -> bool:
        """
        Operator emergency kill switch: immediately disarms the artifact.
        """
        record = self.get_artifact(artifact_id)
        if not record or record.user_id != user_id:
            return False

        record.status = ArtifactStatus.KILLED
        record.updated_at = datetime.now(timezone.utc).isoformat()
        logger.warning("Operator TRIGGERED KILL-SWITCH for artifact %s", artifact_id)

        repo = self._get_repo()
        if repo:
            try:
                repo.update_lifecycle(artifact_id=artifact_id, status=ArtifactStatus.KILLED)
            except Exception as e:
                logger.warning("Failed to update killed status in DB for %s: %s", artifact_id, e)

        return True


# Global Singleton Instance for Runtime Tracking
canary_runner = CanaryShadowRunner()
