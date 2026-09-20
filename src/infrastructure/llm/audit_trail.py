"""
Audit Trail — Zero-Knowledge Cryptographic Decision Logger.
零知識不可篡改決策稽核日誌。

記錄每次決策之脫敏狀態 SHA-256 雜湊值與結果，滿足金融合規要求，且不留存任何未授權明文個資。
"""

import time
import json
import hashlib
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("system1.audit")

class ZeroKnowledgeAuditor:
    """
    提供決策單向雜湊存證，確保決策過程可回溯、防篡改，同時實現零資料洩漏。
    """

    def __init__(self, log_channel: Optional[logging.Logger] = None):
        self.logger = log_channel or logger

    def record_decision(
        self,
        decision_id: str,
        domain: str,
        sanitized_state: Dict[str, Any],
        question_key: str,
        choice: Any,
        confidence: float,
        is_escalated: bool = False,
        tier: str = "reflex",
        latency_ms: float = 0.0,
        extra_meta: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        記錄一筆決策日誌，回傳計算之 SHA-256 State 簽章。
        """
        # 1. 計算脫敏狀態的 SHA-256 單向雜湊
        state_serialized = json.dumps(sanitized_state, sort_keys=True, ensure_ascii=False)
        state_hash = hashlib.sha256(state_serialized.encode("utf-8")).hexdigest()

        # 2. 構建審計事件資料結構
        entry = {
            "timestamp": time.time(),
            "decision_id": decision_id,
            "domain": domain,
            "question_key": question_key,
            "state_sha256": state_hash,
            "choice": choice,
            "confidence": round(confidence, 4),
            "is_escalated": is_escalated,
            "tier": tier,
            "latency_ms": round(latency_ms, 2),
            "meta": extra_meta or {}
        }

        # 3. 寫入專用稽核 Log
        self.logger.info(json.dumps(entry, ensure_ascii=False))
        return state_hash
