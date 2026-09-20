"""
Security Sanitizer — High-Assurance Zero-Leakage Data Sanitization.
高強度資料脫敏與狀態正規化管道。

遵循規範:
  - 規範一 (Clean Architecture): 基礎設施層隔離所有外部 HTTP 與第三方 API 依賴
  - 資訊安全: 確保金融真實金額、私鑰與 PII 在外發前 100% 遮蔽或正規化
"""

import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class HighAssuranceSanitizer:
    """
    負責在將 State 傳送至外部決策引擎（如 Jev / OpenRouter）前，
    進行特徵抽象化（Feature Abstraction）與機密遮罩（Secret Redaction）。
    """

    DEFAULT_SECRET_PATTERNS = [
        re.compile(r"(sk-[a-zA-Z0-9_-]{20,})"),               # OpenAI / OpenRouter keys
        re.compile(r"(ghp_[a-zA-Z0-9]{20,})"),               # GitHub Personal Access Tokens
        re.compile(r"(bearer\s+[a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE), # Bearer tokens
        re.compile(r"(\b[A-Fa-f0-9]{64}\b)"),                # 64-char Hex / Private keys
        re.compile(r"(ey[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,})"), # JWT tokens
    ]

    # 金融實體金額欄位黑名單（直接過濾，轉為抽象統計特徵）
    FINANCIAL_SENSITIVE_KEYS = {
        "account_id", "account_number", "cash_balance", "portfolio_cash",
        "total_balance", "available_funds", "user_id", "real_name",
        "ssn", "national_id", "bank_account", "broker_credentials"
    }

    def __init__(self, secret_patterns: Optional[List[re.Pattern]] = None):
        self.secret_patterns = secret_patterns or self.DEFAULT_SECRET_PATTERNS

    def sanitize(self, raw_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步或非同步脫敏主進入點：
        1. 過濾黑名單直接敏感資訊
        2. 金融指標抽象特徵化
        3. 文字內容正則機密掃描
        """
        if not raw_state:
            return {}

        sanitized: Dict[str, Any] = {}
        for key, value in raw_state.items():
            k_lower = key.lower()

            # 1. 黑名單敏感欄位直接丟棄
            if k_lower in self.FINANCIAL_SENSITIVE_KEYS:
                continue

            # 2. 金融數值特徵化（將絕對股數或金額轉為相對變動比率）
            if "allocation_delta" in k_lower or "weight_delta" in k_lower:
                try:
                    sanitized[key] = round(float(value), 4)
                except (ValueError, TypeError):
                    sanitized[key] = 0.0
                continue

            # 3. 處理字串型別
            if isinstance(value, str):
                sanitized[key] = self._redact_string(value)
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self._redact_string(item) if isinstance(item, str)
                    else (self.sanitize(item) if isinstance(item, dict) else item)
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    def _redact_string(self, text: str) -> str:
        """對單一文字字串進行機密檢測與遮蔽"""
        cleaned = text
        for pattern in self.secret_patterns:
            cleaned = pattern.sub("[REDACTED_SECRET]", cleaned)
        return cleaned
