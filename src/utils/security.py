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

    # 3. Generic API Keys (sk-..., etc.)
    # OpenAI/Anthropic patterns
    redacted = re.sub(
        r"(sk-[a-zA-Z0-9]{20,})",
        r"[REDACTED]",
        redacted,
    )

    # 4. JSON / Query parameter keys (api_key, token, secret)
    # Pattern: "api_key": "val" or api_key=val
    patterns = [
        r"([\"']?api_key[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]+([\"'])",
        r"([\"']?API_KEY[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]+([\"'])",
        r"([\"']?access_token[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]+([\"'])",
        r"([\"']?webhook_secret[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]+([\"'])",
        r"(token=)[A-Za-z0-9_\-\.]+",
    ]
    
    for p in patterns:
        if "token=" in p:
             redacted = re.sub(p, r"\1[REDACTED]", redacted, flags=re.IGNORECASE)
        else:
             redacted = re.sub(p, r"\1[REDACTED]\2", redacted, flags=re.IGNORECASE)

    # 5. Financial Sensitive Identifiers (Optional, to satisfy CodeQL taint analysis)
    # If CodeQL flags specific IDs, we can add them here if they match a pattern.
    
    return redacted
