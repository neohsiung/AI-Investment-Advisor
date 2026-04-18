import logging
import uuid
from typing import Any, Dict, List
import yaml
from pathlib import Path

from src.data.database import SessionLocal
from src.data.models import LLMProvider, LLMModel, LLMTierBinding

logger = logging.getLogger(__name__)

# Default tier → (provider_code, model_code) mapping
DEFAULT_TIER_CHAIN: Dict[str, List[tuple[str, str]]] = {
    "nano": [("openai", "gpt-4.1-nano")],
    "fast": [("gemini", "gemini-2.5-flash"), ("openai", "gpt-4.1-nano")],
    "smart": [("gemini", "gemini-2.5-pro"), ("anthropic", "claude-sonnet-4-5-20250929")],
    "advanced": [("anthropic", "claude-sonnet-4-5-20250929"), ("gemini", "gemini-2.5-pro")],
}

def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

class LLMOnboardingService:
    """
    Service to seed default LLM Providers, Models, and Tier Bindings for a new user.
    Uses synchronous SQLAlchemy ORM internally for encapsulation of the seeding process.
    """
    def __init__(self):
        from src.config.paths import get_project_root
        self.config_dir = get_project_root() / "config"
        self.providers_yaml = load_yaml(self.config_dir / "llm_providers.yaml").get("providers", [])
        self.models_yaml = load_yaml(self.config_dir / "llm_models_seed.yaml").get("models", [])

    def seed_defaults_for_user(self, user_id: str, force: bool = False) -> None:
        """
        Main entry point for onboarding a user (Sync). Opens a short-lived sync session.
        """
        if not self.providers_yaml or not self.models_yaml:
            logger.warning("Missing LLM seed configs. Skipping LLM onboarding for user %s", user_id)
            return

        with SessionLocal() as session:
            try:
                code_to_id = self._seed_providers(session, user_id)
                model_key_to_id = self._seed_models(session, code_to_id)
                self._seed_tier_bindings(session, user_id, model_key_to_id, force=force)
                session.commit()
                logger.info("Successfully seeded LLM defaults for user=%s (sync)", user_id)
            except Exception as e:
                session.rollback()
                logger.error("Failed to seed LLM defaults for user=%s: %s", user_id, e)
                raise

    async def async_seed_defaults_for_user(self, user_id: str, force: bool = False) -> None:
        """
        Main entry point for onboarding a user (Async).
        """
        from src.data.database import get_async_db_engine
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy import select

        if not self.providers_yaml or not self.models_yaml:
            logger.warning("Missing LLM seed configs. Skipping async LLM onboarding for user %s", user_id)
            return

        engine = get_async_db_engine()
        async with AsyncSession(engine) as session:
            try:
                code_to_id = await self._async_seed_providers(session, user_id)
                model_key_to_id = await self._async_seed_models(session, code_to_id)
                await self._async_seed_tier_bindings(session, user_id, model_key_to_id, force=force)
                await session.commit()
                logger.info("Successfully seeded LLM defaults for user=%s (async)", user_id)
            except Exception as e:
                await session.rollback()
                logger.error("Failed to async seed LLM defaults for user=%s: %s", user_id, e)
                raise

    def _seed_providers(self, session: Any, user_id: str) -> Dict[str, str]:
        # ... (existing sync code)
        code_to_id: Dict[str, str] = {}
        for spec in self.providers_yaml:
            code = spec["provider_code"]
            display_name = spec.get("display_name", code)
            existing = session.query(LLMProvider).filter_by(user_id=user_id, provider_code=code).one_or_none()
            if existing:
                code_to_id[code] = existing.id
                continue

            provider = LLMProvider(
                id=str(uuid.uuid4()),
                user_id=user_id,
                provider_code=code,
                display_name=display_name,
                base_url=spec.get("default_base_url"),
                encrypted_api_key=None,
                enabled=True,
                extra_config={},
            )
            session.add(provider)
            session.flush()
            code_to_id[code] = provider.id
        return code_to_id

    async def _async_seed_providers(self, session: Any, user_id: str) -> Dict[str, str]:
        from sqlalchemy import select
        code_to_id: Dict[str, str] = {}
        for spec in self.providers_yaml:
            code = spec["provider_code"]
            display_name = spec.get("display_name", code)
            
            # Async query
            stmt = select(LLMProvider).filter_by(user_id=user_id, provider_code=code)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                code_to_id[code] = existing.id
                continue

            provider = LLMProvider(
                id=str(uuid.uuid4()),
                user_id=user_id,
                provider_code=code,
                display_name=display_name,
                base_url=spec.get("default_base_url"),
                encrypted_api_key=None,
                enabled=True,
                extra_config={},
            )
            session.add(provider)
            await session.flush()
            code_to_id[code] = provider.id
        return code_to_id

    def _seed_models(self, session: Any, provider_code_to_id: Dict[str, str]) -> Dict[tuple[str, str], str]:
        # ... (rest of the file needs to be updated too, I'll do it in chunks if needed but this looks okay for a first step)

    def _seed_models(self, session: Any, provider_code_to_id: Dict[str, str]) -> Dict[tuple[str, str], str]:
        key_to_id: Dict[tuple[str, str], str] = {}
        for m in self.models_yaml:
            p_code = m["provider_code"]
            m_code = m["model_code"]
            p_id = provider_code_to_id.get(p_code)
            if not p_id:
                continue

            existing = session.query(LLMModel).filter_by(provider_id=p_id, model_code=m_code).one_or_none()
            if existing:
                key_to_id[(p_code, m_code)] = existing.id
                continue

            caps = m.get("capabilities", {})
            model = LLMModel(
                id=str(uuid.uuid4()),
                provider_id=p_id,
                model_code=m_code,
                display_name=m.get("display_name", m_code),
                capability_tool_calling=caps.get("tool_calling", False),
                capability_vision=caps.get("vision", False),
                capability_json_mode=caps.get("json_mode", False),
                capability_streaming=caps.get("streaming", True),
                capability_embeddings=caps.get("embeddings", False),
                context_window=m.get("context_window"),
                input_cost_per_1k=m.get("input_cost_per_1k"),
                output_cost_per_1k=m.get("output_cost_per_1k"),
                source="seed",
                enabled=True,
                notes=m.get("notes"),
            )
            session.add(model)
            session.flush()
            key_to_id[(p_code, m_code)] = model.id
        return key_to_id

    async def _async_seed_models(self, session: Any, provider_code_to_id: Dict[str, str]) -> Dict[tuple[str, str], str]:
        from sqlalchemy import select
        key_to_id: Dict[tuple[str, str], str] = {}
        for m in self.models_yaml:
            p_code = m["provider_code"]
            m_code = m["model_code"]
            p_id = provider_code_to_id.get(p_code)
            if not p_id:
                continue

            stmt = select(LLMModel).filter_by(provider_id=p_id, model_code=m_code)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                key_to_id[(p_code, m_code)] = existing.id
                continue

            caps = m.get("capabilities", {})
            model = LLMModel(
                id=str(uuid.uuid4()),
                provider_id=p_id,
                model_code=m_code,
                display_name=m.get("display_name", m_code),
                capability_tool_calling=caps.get("tool_calling", False),
                capability_vision=caps.get("vision", False),
                capability_json_mode=caps.get("json_mode", False),
                capability_streaming=caps.get("streaming", True),
                capability_embeddings=caps.get("embeddings", False),
                context_window=m.get("context_window"),
                input_cost_per_1k=m.get("input_cost_per_1k"),
                output_cost_per_1k=m.get("output_cost_per_1k"),
                source="seed",
                enabled=True,
                notes=m.get("notes"),
            )
            session.add(model)
            await session.flush()
            key_to_id[(p_code, m_code)] = model.id
        return key_to_id

    def _seed_tier_bindings(self, session: Any, user_id: str, model_key_to_id: Dict[tuple[str, str], str], force: bool) -> None:
        for tier, chain in DEFAULT_TIER_CHAIN.items():
            existing = session.query(LLMTierBinding).filter_by(user_id=user_id, tier=tier).one_or_none()
            if existing and not force:
                continue

            model_ids = [model_key_to_id[(p, m)] for p, m in chain if (p, m) in model_key_to_id]
            if not model_ids:
                continue

            primary_id = model_ids[0]
            fallback_ids = model_ids[1:]

            if existing:
                existing.primary_model_id = primary_id
                existing.fallback_model_ids = fallback_ids
            else:
                binding = LLMTierBinding(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    tier=tier,
                    primary_model_id=primary_id,
                    fallback_model_ids=fallback_ids,
                    per_candidate_config={},
                    budget_aware=True,
                )
                session.add(binding)

    async def _async_seed_tier_bindings(self, session: Any, user_id: str, model_key_to_id: Dict[tuple[str, str], str], force: bool) -> None:
        from sqlalchemy import select
        for tier, chain in DEFAULT_TIER_CHAIN.items():
            stmt = select(LLMTierBinding).filter_by(user_id=user_id, tier=tier)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing and not force:
                continue

            model_ids = [model_key_to_id[(p, m)] for p, m in chain if (p, m) in model_key_to_id]
            if not model_ids:
                continue

            primary_id = model_ids[0]
            fallback_ids = model_ids[1:]

            if existing:
                existing.primary_model_id = primary_id
                existing.fallback_model_ids = fallback_ids
            else:
                binding = LLMTierBinding(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    tier=tier,
                    primary_model_id=primary_id,
                    fallback_model_ids=fallback_ids,
                    per_candidate_config={},
                    budget_aware=True,
                )
                session.add(binding)
