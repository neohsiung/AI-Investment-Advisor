"""
Rate Limiting Utility - Phase 8 System Hardening.
API 頻率限制工具。

Provides a centralized Limiter instance for use across FastAPI routers.
基於 slowapi 提供中央 Limiter 實例。
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Global limiter instance
# 100 requests per minute as a soft default for IP-based limiting
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
