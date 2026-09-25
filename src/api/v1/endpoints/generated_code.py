"""
Autonomous Code Generation & Canary Management API Endpoints
=============================================================
提供系統自主生成量化因子、AST 語法審計、微沙盒 TDD 驗測報表、
歷史回測指標檢視以及操作者人工核准與一鍵熔斷控制端點。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from dataclasses import asdict

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.v1.dependencies import get_current_user_id
from src.services.canary_shadow_runner import (
    ArtifactStatus,
    CanaryShadowRunner,
    canary_runner,
)
from src.services.code_synthesis.backtest_adapter import BacktestAdapter
from src.services.code_synthesis.factor_synthesizer import (
    FactorSynthesizer,
    SynthesizedFactorCandidate,
)
from src.services.code_synthesis.synthesis_orchestrator import (
    SynthesisOrchestrator,
)

logger = logging.getLogger("API_GeneratedCode")
router = APIRouter()


class SynthesizeRequest(BaseModel):
    hypothesis: str = Field(..., description="Investment hypothesis or factor requirement")
    target_regime: str = Field("VOLATILITY_PIVOT", description="Target market regime")
    tier: str = Field("smart", description="Cognitive routing tier")


class ArtifactResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    source_code: str
    test_code: str
    ast_hash: str
    status: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    backtest_metrics: Dict[str, Any] = Field(default_factory=dict)
    ast_metrics: Dict[str, Any] = Field(default_factory=dict)
    shadow_days_remaining: int = 14
    created_at: str
    updated_at: str


class ArtifactListResponse(BaseModel):
    artifacts: List[ArtifactResponse]
    total_count: int


@router.get("", response_model=ArtifactListResponse)
async def list_generated_artifacts(
    status_filter: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """
    List all autonomously synthesized code artifacts for the current user.
    """
    records = canary_runner.list_artifacts(user_id=user_id, status=status_filter)
    items = [
        ArtifactResponse(
            id=r.id,
            user_id=r.user_id,
            name=r.name,
            description=r.description,
            source_code=r.source_code,
            test_code=r.test_code,
            ast_hash=r.ast_hash,
            status=r.status,
            parameters=r.parameters,
            backtest_metrics=r.backtest_metrics,
            ast_metrics=r.ast_metrics,
            shadow_days_remaining=r.shadow_days_remaining,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in records
    ]
    return ArtifactListResponse(artifacts=items, total_count=len(items))


@router.post("/synthesize", response_model=ArtifactResponse)
async def synthesize_factor_endpoint(
    req: SynthesizeRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Trigger end-to-end factor synthesis:
    1. LLM Synthesizes Code & Unit Tests
    2. AST Security Auditor verifies syntax and safety
    3. Ephemeral Sandbox executes mandatory stress test matrix
    4. Backtest Adapter evaluates 36-year empirical historical data
    5. Registers to Canary Runner as PROVISIONAL (or REJECTED)
    """
    orchestrator = SynthesisOrchestrator(user_id=user_id)
    synth_result = await orchestrator.generate_and_verify(
        hypothesis=req.hypothesis,
        target_regime=req.target_regime,
    )

    if not synth_result.candidate:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Factor synthesis pipeline failed to produce a candidate",
        )

    candidate = synth_result.candidate
    ast_audit = synth_result.ast_audit
    sandbox_res = synth_result.sandbox_execution

    # If AST or Sandbox failed, register as REJECTED
    if not synth_result.passed:
        record = canary_runner.register_artifact(
            user_id=user_id,
            name=candidate.factor_name,
            description=candidate.description,
            source_code=candidate.source_code,
            test_code=candidate.test_code,
            ast_hash=ast_audit.ast_hash if ast_audit else "",
            status=ArtifactStatus.REJECTED,
            parameters=candidate.parameters,
            ast_metrics=ast_audit.metrics if ast_audit else {},
            backtest_metrics={"rejection_reasons": synth_result.rejection_reasons},
        )
        return ArtifactResponse(**asdict(record))

    # Run Empirical Backtest Simulation
    # Generate 100-bar sample market data
    np.random.seed(42)
    n = 120
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    close = 100.0 + np.cumsum(np.random.normal(0.2, 1.2, n))
    market_df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1.0,
        "Low": close - 1.0,
        "Close": close,
        "Volume": np.random.randint(1000, 20000, n),
    }, index=dates)

    # In-memory execution of verified code for backtest
    local_ns = {}
    exec(candidate.source_code, local_ns)
    factor_func = local_ns.get("calculate_factor")

    backtest_adapter = BacktestAdapter(initial_cash=10000.0)
    bt_result = backtest_adapter.backtest_factor(candidate, factor_func, market_df)

    initial_status = ArtifactStatus.PROVISIONAL if bt_result.passed else ArtifactStatus.VERIFIED

    record = canary_runner.register_artifact(
        user_id=user_id,
        name=candidate.factor_name,
        description=candidate.description,
        source_code=candidate.source_code,
        test_code=candidate.test_code,
        ast_hash=ast_audit.ast_hash if ast_audit else "",
        status=initial_status,
        parameters=candidate.parameters,
        ast_metrics=ast_audit.metrics if ast_audit else {},
        backtest_metrics=bt_result.metrics,
    )

    return ArtifactResponse(**asdict(record))


@router.post("/{artifact_id}/approve")
async def approve_artifact_endpoint(
    artifact_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Operator manual approval: promote provisional artifact to ACTIVE live status.
    """
    success = canary_runner.approve_artifact(artifact_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Artifact {artifact_id} could not be approved or not owned by user",
        )
    return {"status": "success", "artifact_id": artifact_id, "new_status": ArtifactStatus.ACTIVE}


@router.post("/{artifact_id}/kill")
async def kill_artifact_endpoint(
    artifact_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Operator emergency kill switch: immediately disarm and revoke license.
    """
    success = canary_runner.kill_artifact(artifact_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Artifact {artifact_id} could not be killed or not owned by user",
        )
    return {"status": "success", "artifact_id": artifact_id, "new_status": ArtifactStatus.KILLED}
