"""
Token Logger Service — LLM Usage and Cost Tracking.
Token 記錄服務 — LLM 使用量與成本追蹤。

Provides centralized logging of prompt and completion tokens, calculates
costs based on TierConfig, and persists records to PostgreSQL.

遵循規範八 (Cognitive Memory Tiering): 預算監控
遵循規範十五 (AI-Support First): 結構化日誌
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from src.data.database import BaseRepository, get_db_engine
from src.infrastructure.llm.tier_config import TierConfig

logger = logging.getLogger("TokenLoggerService")


class TokenLoggerService(BaseRepository):
    """
    Service for logging LLM token usage and calculating costs.
    記錄 LLM Token 使用量並計算成本的服務。
    """

    def __init__(self, engine=None):
        if engine is None:
            engine = get_db_engine()
        super().__init__(engine)
        self.tier_config = TierConfig()

    def log_usage(
        self,
        user_id: str,
        agent_name: str,
        tier: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Log LLM usage to the database and calculate cost.
        將 LLM 使用量記錄至資料庫並計算成本。

        Args:
            user_id: The ID of the user (email or UUID)
            agent_name: Name of the agent making the call (e.g., "IntentClassifier")
            tier: Logic tier used ("nano", "fast", "smart", "advanced")
            model: Actual model name (e.g., "gpt-4o-mini")
            provider: Provider name (e.g., "OpenRouter")
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            metadata: Optional additional context
        """
        try:
            # 1. Get tier specification for cost calculation
            spec = self.tier_config.get_spec(tier)
            total_cost = 0.0
            
            if spec:
                # Cost is stored per million tokens in TierSpec
                input_cost = (prompt_tokens / 1_000_000) * spec.input_cost_per_mtok
                output_cost = (completion_tokens / 1_000_000) * spec.output_cost_per_mtok
                total_cost = input_cost + output_cost
            else:
                logger.warning(f"TokenLoggerService: Unknown tier '{tier}', cost will be logged as 0.0")

            # 2. Persist to database
            from sqlalchemy import text
            
            query = text("""
                INSERT INTO llm_usage_logs (
                    id, user_id, agent_name, provider, model, tier, 
                    prompt_tokens, completion_tokens, total_cost_usd, metadata
                ) VALUES (
                    :id, :user_id, :agent_name, :provider, :model, :tier,
                    :prompt_tokens, :completion_tokens, :total_cost, :metadata
                )
            """)
            
            # Ensure metadata is serializable
            import json
            metadata_json = json.dumps(metadata or {})
            
            with self.engine.connect() as conn:
                conn.execute(query, {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "agent_name": agent_name,
                    "provider": provider,
                    "model": model,
                    "tier": tier,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_cost": total_cost,
                    "metadata": metadata_json
                })
                # For SQLAlchemy 2.0+ or with autocommit, we might need conn.commit() 
                # but connect() context manager usually handles it if configured.
                # In this project's database.py, autocommit is standard for raw SQL.
            
            logger.debug(
                f"Logged LLM usage for {agent_name} ({tier}): "
                f"{prompt_tokens + completion_tokens} tokens, ${total_cost:.6f}"
            )
            return True

        except Exception as e:
            logger.error(f"TokenLoggerService: Failed to log usage: {e}", exc_info=True)
            return False

    def get_user_spending(
        self, user_id: str, days: int = 7
    ) -> Dict[str, Any]:
        """
        Get total spending and token counts for a user over a period.
        查詢使用者在特定期間內的總花費與 Token 數。
        """
        summary = {
            "total_cost": 0.0,
            "total_tokens": 0,
            "tiers": {}
        }
        
        try:
             from sqlalchemy import text
             # Check dialect for interval syntax
             if self.engine.name == 'sqlite':
                 query = text("""
                     SELECT 
                         SUM(total_cost_usd) as total_cost,
                         SUM(prompt_tokens + completion_tokens) as total_tokens,
                         tier,
                         COUNT(*) as call_count
                     FROM llm_usage_logs
                     WHERE user_id = :user_id 
                       AND timestamp >= datetime('now', '-' || :days || ' days')
                     GROUP BY tier
                 """)
             else:
                 # Default to Postgres syntax
                 query = text("""
                     SELECT 
                         SUM(total_cost_usd) as total_cost,
                         SUM(prompt_tokens + completion_tokens) as total_tokens,
                         tier,
                         COUNT(*) as call_count
                     FROM llm_usage_logs
                     WHERE user_id = :user_id 
                       AND timestamp >= NOW() - (CAST(:days AS INTEGER) * INTERVAL '1 day')
                     GROUP BY tier
                 """)
             
             with self.engine.connect() as conn:
                 result = conn.execute(query, {"user_id": user_id, "days": days})
                 rows = result.fetchall()
             
             for row in rows:
                 cost = float(row.total_cost or 0.0)
                 tokens = int(row.total_tokens or 0)
                 tier = str(row.tier or "unknown")
                 
                 summary["total_cost"] += cost
                 summary["total_tokens"] += tokens
                 summary["tiers"][tier] = {
                     "cost": cost,
                     "tokens": tokens,
                     "calls": int(row.call_count or 0)
                 }
                 
             return summary

        except Exception as e:
             logger.error(f"TokenLoggerService: Failed to get user spending: {e}")
             # Return current summary (even if empty) to avoid -1.0 issues in budget logic
             return summary
