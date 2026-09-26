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

    def auto_enroll_verified_artifacts(self, user_id: str) -> List[CodeArtifactRecord]:
        """
        Scan all VERIFIED artifacts owned by user_id and enroll them into PROVISIONAL canary tracking (14 days).
        掃描所有通過沙盒驗測之 VERIFIED 因子，自動登錄進入 14 天金絲雀灰度考覈。
        """
        verified = self.list_artifacts(user_id=user_id, status=ArtifactStatus.VERIFIED)
        enrolled = []
        now_iso = datetime.now(timezone.utc).isoformat()
        repo = self._get_repo()

        for art in verified:
            art.status = ArtifactStatus.PROVISIONAL
            art.shadow_days_remaining = 14
            art.updated_at = now_iso
            enrolled.append(art)
            if repo:
                try:
                    repo.update_lifecycle(
                        artifact_id=art.id,
                        status=ArtifactStatus.PROVISIONAL,
                        shadow_days_remaining=14,
                    )
                except Exception as e:
                    logger.warning("Failed to enroll artifact %s to provisional in DB: %s", art.id, e)
            logger.info("Auto-enrolled VERIFIED artifact %s (%s) into 14-day canary tracking", art.id, art.name)

        return enrolled

    def evaluate_auto_promotion(self, record: CodeArtifactRecord) -> Dict[str, Any]:
        """
        Evaluate if a PROVISIONAL artifact meets rigid statistical and canary stability criteria for automated promotion.
        評估灰度影子期因子是否滿足統計健壯性與即時跟蹤穩定度，符合自動晉升實盤門檻。
        """
        if record.status != ArtifactStatus.PROVISIONAL:
            return {"eligible": False, "reason": f"Status is {record.status}, expected PROVISIONAL", "weight_tier": 0.0}

        metrics = record.backtest_metrics or {}
        params = record.parameters or {}

        # 1. Backtest & Robustness Hard Gates
        sharpe = float(metrics.get("sharpe_ratio", 0.0) or 0.0)
        mdd = float(metrics.get("max_drawdown_pct", 100.0) or 100.0)
        wfe = float(metrics.get("wfe", params.get("wfe", 0.0)) or 0.0)
        mc_win_rate = float(metrics.get("monte_carlo_win_rate", params.get("monte_carlo_win_rate", 0.0)) or 0.0)

        if sharpe < 1.0 or mdd > 25.0:
            return {
                "eligible": False,
                "reason": f"Backtest metrics below gate: Sharpe={sharpe:.2f} (min 1.0), MDD={mdd:.1f}% (max 25%)",
                "weight_tier": 0.0,
            }

        # 2. Canary Shadow Tracking Gates
        # Rule out any severe single-day drop in shadow tracking
        shadow_log = record.shadow_tracking_log or []
        severe_drops = [entry for entry in shadow_log if float(entry.get("daily_pnl_pct", 0.0)) <= -5.0]
        if severe_drops:
            return {
                "eligible": False,
                "reason": f"Severe single-day drawdown encountered in shadow period ({len(severe_drops)} events)",
                "weight_tier": 0.0,
            }

        # Condition A: Completed full 14-day canary shadow tracking
        if record.shadow_days_remaining == 0:
            return {
                "eligible": True,
                "reason": "Graduated: Completed full 14-day canary shadow tracking with zero severe drawdowns",
                "weight_tier": 0.05,
            }

        # Condition B: Fast-track promotion for superior robustness after >= 7 shadow days
        if record.shadow_days_remaining <= 7 and len(shadow_log) >= 7:
            cum_pnl = sum(float(e.get("daily_pnl_pct", 0.0)) for e in shadow_log)
            # Must have non-negative cumulative simulated pnl and solid WFE / MC scores
            is_wfe_robust = (wfe >= 0.70 or wfe == 0.0)  # if WFE was computed, must be >= 0.70
            is_mc_robust = (mc_win_rate >= 75.0 or mc_win_rate == 0.0)
            if cum_pnl >= 0.0 and is_wfe_robust and is_mc_robust:
                return {
                    "eligible": True,
                    "reason": f"Fast-Track: 7-day shadow track positive ({cum_pnl:+.2f}%) with WFE={wfe:.2f}, MC={mc_win_rate:.1f}%",
                    "weight_tier": 0.05,
                }

        return {
            "eligible": False,
            "reason": f"Shadow tracking in progress: {record.shadow_days_remaining} days remaining (logged {len(shadow_log)} days)",
            "weight_tier": 0.0,
        }

    def auto_promote_artifact(self, artifact_id: str, user_id: str) -> bool:
        """
        Execute automated promotion from PROVISIONAL to ACTIVE with stepped weight allocation and notifications.
        執行自動核准晉升：將符合標準之因子轉為 ACTIVE 狀態，配賦 5% 初始階梯權重並發送推播。
        """
        record = self.get_artifact(artifact_id)
        if not record or record.user_id != user_id:
            return False

        eval_res = self.evaluate_auto_promotion(record)
        if not eval_res["eligible"]:
            logger.info("Artifact %s not eligible for auto-promotion: %s", artifact_id, eval_res["reason"])
            return False

        now_iso = datetime.now(timezone.utc).isoformat()
        initial_weight = eval_res.get("weight_tier", 0.05)

        record.status = ArtifactStatus.ACTIVE
        record.updated_at = now_iso
        record.parameters["approval_type"] = "automated"
        record.parameters["weight_cap"] = initial_weight
        record.parameters["promoted_at"] = now_iso
        record.parameters["promotion_reason"] = eval_res["reason"]

        logger.info(
            "Auto-promoted artifact '%s' (%s) to ACTIVE live status (initial weight: %.1f%%, reason: %s)",
            record.name,
            artifact_id,
            initial_weight * 100,
            eval_res["reason"],
        )

        repo = self._get_repo()
        if repo:
            try:
                repo.update_lifecycle(
                    artifact_id=artifact_id,
                    status=ArtifactStatus.ACTIVE,
                    parameters=record.parameters,
                )
            except Exception as e:
                logger.warning("Failed to update auto-promoted status in DB for %s: %s", artifact_id, e)

        # Dispatch multi-channel notification
        try:
            from src.services.factor_notification_service import factor_notification_service
            import asyncio
            coro = factor_notification_service.notify_factor_promoted(
                artifact_name=record.name,
                regime=record.parameters.get("target_regime", "DYNAMIC"),
                user_id=user_id,
                metrics=record.backtest_metrics,
                approval_type="automated",
            )
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(coro)
                else:
                    loop.run_until_complete(coro)
            except Exception:
                asyncio.run(coro)
        except Exception as notif_err:
            logger.warning("Failed to dispatch auto-promotion notification for %s: %s", artifact_id, notif_err)

        return True

    def get_effective_weight_cap(self, record: CodeArtifactRecord) -> float:
        """
        Compute effective weight cap for active factor.
        Stepped release: Freshly auto-promoted factors start at 5% cap;
        after 7 days of live stability, step up to full 15% cap.
        計算因子實盤有效權重上限：新自動晉升因子初始 5%，平穩運行 7 天後階梯釋放至 15%。
        """
        params = record.parameters or {}
        if params.get("approval_type") != "automated":
            # Manual approval defaults to full 15% cap
            return float(params.get("weight_cap", 0.15))

        promoted_at_str = params.get("promoted_at")
        if not promoted_at_str:
            return float(params.get("weight_cap", 0.05))

        try:
            promoted_dt = datetime.fromisoformat(promoted_at_str)
            now_dt = datetime.now(timezone.utc)
            days_active = (now_dt - promoted_dt).total_seconds() / 86400.0
            if days_active >= 7.0:
                # Stepped up to full 15%
                return 0.15
            return float(params.get("weight_cap", 0.05))
        except Exception:
            return float(params.get("weight_cap", 0.05))


# Global Singleton Instance for Runtime Tracking
canary_runner = CanaryShadowRunner()

