import re
import typing
from typing import Any, Union

def redact_secrets(text_value: Any) -> Any:
    """
    Best-effort redaction of common secret patterns (API keys, bearer tokens, etc.)
    before persisting content to disk or logging.
    符合 Rule #13 (No-Hardcoded-Secrets) 的脫敏工具。
    """
    if not isinstance(text_value, str):
        return text_value

    redacted = text_value

    # 1. Authorization: Bearer <token>
    redacted = re.sub(
        r"(Authorization:\s*Bearer\s+)[^\s\"']+",
        r"\1[REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )
    
    # 2. Bearer <token> (standalone or in JSON)
    redacted = re.sub(
        r"(Bearer\s+)[a-zA-Z0-9\._\-]{10,}",
        r"\1[REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )

    # 3. Generic API Keys (sk-..., orp-..., etc.)
    # OpenAI/Anthropic/OpenRouter patterns
    redacted = re.sub(
        r"((?:sk|orp|ant|gl|gh|pt)-[a-zA-Z0-9_\-]{24,})",
        r"[REDACTED]",
        redacted,
    )

    # 4. JSON / Query parameter keys (api_key, token, secret, password)
    patterns = [
        (r"([\"']?api_key[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]{10,}([\"'])", r"\1[REDACTED]\2"),
        (r"([\"']?API_KEY[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]{10,}([\"'])", r"\1[REDACTED]\2"),
        (r"([\"']?access_token[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]{20,}([\"'])", r"\1[REDACTED]\2"),
        (r"([\"']?webhook_secret[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]{10,}([\"'])", r"\1[REDACTED]\2"),
        (r"([\"']?password[\"']?\s*[:=]\s*[\"'])[^\s\"']{4,}([\"'])", r"\1[REDACTED]\2"),
        (r"(token=)[A-Za-z0-9_\-\.]{10,}", r"\1[REDACTED]"),
        (r"(&?key=)[A-Za-z0-9_\-\.]{16,}", r"\1[REDACTED]"),
    ]
    
    for p, repl in patterns:
        redacted = re.sub(p, repl, redacted, flags=re.IGNORECASE)

    # 5. Financial Sensitive Data Redaction (Optional)
    # v7.1: Redact large specific balance numbers if they look like precise account values
    # e.g., "Account Balance: $100240321.45" -> "Account Balance: $[REDACTED]"
    # This is useful for public logs.
    redacted = re.sub(
        r"(\$\s?\d{7,}\.\d{2})",
        r"$[AMOUNT_REDACTED]",
        redacted
    )
    
    return redacted

def redact_pii(text: str) -> str:
    """
    Enterprise-grade PII redaction (Emails, Account numbers, precise IDs)
    to protect data privacy before sending to external LLM APIs.
    """
    if not isinstance(text, str):
        return text
    
    # 1. Emails
    redacted = re.sub(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        r"[REDACTED_EMAIL]",
        text
    )
    
    # 2. Phone numbers (e.g., +886 912345678, 0912-345-678)
    # Require either a + prefix or specific separator patterns
    redacted = re.sub(
        r"(\+?[0-9]{1,3}[ -][0-9]{3,4}[ -][0-9]{3,6})|(\b09[0-9]{2}-[0-9]{3}-[0-9]{3}\b)",
        r"[REDACTED_PHONE]",
        redacted
    )

    # 3. Generic Account IDs (8-20 digits) - Use strict word boundaries
    redacted = re.sub(
        r"\b\d{8,20}\b",
        r"[REDACTED_ACCOUNT_ID]",
        redacted
    )
    
    return redacted
