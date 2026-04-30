import logging
import time
from typing import Dict, Optional, Any
from sqlalchemy import text
from src.data.database import get_db_engine

logger = logging.getLogger(__name__)

class ModelIdResolver:
    """
    Resolves logical model identifiers to provider-specific model IDs.
    Includes a TTL cache to avoid redundant database queries.
    [Phase 2 - Task 2.1]
    """
    _instance = None
    _cache: Dict[str, Dict[str, Any]] = {}
    _ttl = 3600  # 1 hour

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelIdResolver, cls).__new__(cls)
        return cls._instance

    def resolve(self, local_model_name: str, gateway_type: str) -> str:
        """
        Resolve a local model name (e.g. 'gemini-2.0-flash') to a provider ID
        for a specific gateway (e.g. 'openrouter' -> 'google/gemini-2.0-flash-001').
        """
        cache_key = f"{gateway_type}:{local_model_name}"
        now = time.time()

        # Check cache
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry['timestamp'] < self._ttl:
                return entry['value']

        # Fallback to DB lookup
        # Task 2.2: Using engine instead of direct psycopg2 connection
        resolved_id = self._lookup_db(local_model_name, gateway_type)
        
        # Cache the result (even if it's the same as local_model_name)
        self._cache[cache_key] = {
            'value': resolved_id,
            'timestamp': now
        }
        
        return resolved_id

    def _lookup_db(self, local_model_name: str, gateway_type: str) -> str:
        """
        Internal DB lookup for model mapping.
        Note: We look into llm_models table first, then a legacy mapping table if it exists.
        """
        engine = get_db_engine()
        try:
            with engine.connect() as conn:
                # 1. Try to find the model in llm_models by model_code
                # If we are using OpenRouter, we might have stored the full path in model_code.
                result = conn.execute(text(
                    "SELECT model_code FROM llm_models WHERE model_code = :code"
                ), {"code": local_model_name})
                row = result.fetchone()
                if row:
                    return row[0]

                # 2. Try to find in a mapping (we'll implement this as a fallback 
                # using the logic previously in llm_gateway.py, but safe)
                # Since provider_model_id_mapping might not exist, we wrap in try-except
                try:
                    result = conn.execute(text(
                        "SELECT provider_model_id FROM provider_model_id_mapping "
                        "WHERE local_model_name = :name AND provider = :prov"
                    ), {"name": local_model_name, "prov": gateway_type})
                    row = result.fetchone()
                    if row:
                        return row[0]
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"ModelIdResolver: DB lookup failed for {local_model_name}: {e}")
            
        return local_model_name  # Final fallback: return the original name

    def clear_cache(self):
        self._cache.clear()

def resolve_model_id(local_model_name: str, gateway_type: str) -> str:
    """Helper function to access the resolver singleton."""
    return ModelIdResolver().resolve(local_model_name, gateway_type)
