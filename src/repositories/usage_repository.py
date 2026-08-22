"""
LLM Usage Repository — Data Layer [Phase 14].
LLM 使用量儲存庫 — 負責記錄 API 消耗、Token 數量與成本。
"""

import logging
from typing import Optional, Dict, Any
from src.data.database import BaseRepository, get_db_engine
from src.data.models import LLMUsageLog

logger = logging.getLogger(__name__)

class UsageRepository(BaseRepository):
    """
    Repository for tracking LLM API usage and costs.
    """
    def __init__(self, engine=None):
        super().__init__(engine or get_db_engine())

    def log_usage(
        self,
        user_id: str,
        agent_name: str,
        tier: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        metadata: Optional[dict] = None
    ):
        """
        Persist an LLM usage log entry with cost calculation using TierConfig [Phase 14].
        """
        try:
            import re
            # Set user_id to None if it is not a valid UUID format (e.g., "system") to avoid ForeignKeyViolation.
            if not user_id or not re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", str(user_id)):
                user_id = None

            from src.infrastructure.llm.tier_config import TierConfig
            spec = TierConfig().get_spec(tier)
            total_cost = 0.0
            if spec:
                input_cost = (prompt_tokens / 1_000_000) * spec.input_cost_per_mtok
                output_cost = (completion_tokens / 1_000_000) * spec.output_cost_per_mtok
                total_cost = input_cost + output_cost

            log_entry = LLMUsageLog(
                user_id=user_id,
                agent_name=agent_name,
                tier=tier,
                model=model,
                provider=provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_cost_usd=total_cost,
                meta=metadata or {}
            )
            self.session.add(log_entry)
            self.session.commit()
            logger.debug(f"📊 Usage Logged: {agent_name} used {prompt_tokens + completion_tokens} tokens (${total_cost:.6f}).")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to log LLM usage: {e}")
        finally:
            self.close_session()

    def get_user_total_cost(self, user_id: str) -> float:
        """
        Calculate total USD cost for a specific user.
        """
        from sqlalchemy import func
        try:
            result = self.session.query(func.sum(LLMUsageLog.total_cost_usd)).filter_by(user_id=user_id).scalar()
            return float(result or 0.0)
        except Exception as e:
            logger.error(f"Failed to retrieve total cost: {e}")
            return 0.0
        finally:
            self.close_session()

    def get_user_cycle_cost(self, user_id: str, since) -> float:
        """
        Calculate total USD cost since a specific datetime (billing cycle start) [Phase 16].
        """
        from sqlalchemy import func
        try:
            result = self.session.query(func.sum(LLMUsageLog.total_cost_usd)).filter(
                LLMUsageLog.user_id == user_id,
                LLMUsageLog.created_at >= since
            ).scalar()
            return float(result or 0.0)
        except Exception as e:
            logger.error(f"Failed to retrieve cycle cost: {e}")
            return 0.0
        finally:
            self.close_session()
    def get_system_total_cost_today(self) -> float:
        """
        Calculate total USD cost for all users in the current UTC day [Phase 21].
        """
        from datetime import datetime, time, timezone
        from sqlalchemy import func
        today_start = datetime.combine(datetime.now(timezone.utc).date(), time.min).replace(tzinfo=timezone.utc)
        
        try:
            result = self.session.query(func.sum(LLMUsageLog.total_cost_usd)).filter(
                LLMUsageLog.created_at >= today_start
            ).scalar()
            return float(result or 0.0)
        except Exception as e:
            logger.error(f"Failed to retrieve system total cost: {e}")
            return 0.0
        finally:
            self.close_session()

    def get_top_spenders(self, limit: int = 5) -> list:
        """
        Retrieve the top users by accumulated cost [Phase 21].
        """
        from sqlalchemy import func, desc
        try:
            results = self.session.query(
                LLMUsageLog.user_id,
                func.sum(LLMUsageLog.total_cost_usd).label('total_cost')
            ).group_by(LLMUsageLog.user_id).order_by(desc('total_cost')).limit(limit).all()
            
            return [{"user_id": r.user_id, "total_cost": float(r.total_cost)} for r in results]
        except Exception as e:
            logger.error(f"Failed to retrieve top spenders: {e}")
            return []
        finally:
            self.close_session()
