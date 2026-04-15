"""
LLM Gateway — Infrastructure Layer Implementations.
模型層閘道 — 基礎設施層實作。

Implements ILLMGateway for each supported LLM provider (OpenRouter, Google Gemini, OpenAI).
All HTTP-level details are isolated here, keeping BaseAgent and Domain layers pure.

遵循規範:
  - 規範一 (Clean Architecture): 基礎設施層隔離所有外部 HTTP 依賴
  - 規範十 (MCP 整合): 標準化 LLM 通訊介面
  - 規範十三 (Atomic Workflows): 原子化 LLM 調用
"""

import time
import json
import logging
import httpx
import asyncio
import typing
from typing import List, Optional, AsyncGenerator

from src.domain.interfaces import ILLMGateway, Message, LLMConfig
from src.utils.security import redact_secrets as _redact_secrets, redact_pii as _redact_pii
from src.utils.tracing import trace_external_call

logger = logging.getLogger(__name__)


class OpenRouterGateway(ILLMGateway):
    """
    LLM Gateway for OpenRouter API.
    OpenRouter API 的 LLM 閘道實作。
    """

    def __init__(self):
        self._last_usage: Optional[dict] = None

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
        url = config.base_url or "https://openrouter.ai/api/v1/chat/completions"
        
        # Validate API key
        if not config.api_key or config.api_key.strip() == "":
            raise ValueError("OpenRouter API key is missing or empty. Cannot proceed with LLM request.")
        
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "AI Investment Advisor",
        }
        
        # Build request data with all required fields
        data = {
            "model": config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": config.max_tokens or 2048,
        }
        
        if config.temperature is not None:
            data["temperature"] = config.temperature

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, headers=headers, json=data,
                    timeout=config.timeout_seconds,
                )
            response.raise_for_status()
        except httpx.HTTPError as e:
            # Log detailed error info for debugging
            error_msg = f"OpenRouter API error: {e}"
            if hasattr(response, 'text'):
                error_msg += f"\nResponse body: {response.text}"
            import logging
            logging.error(error_msg)
            raise
        
        resp_json = response.json()
        self._last_usage = resp_json.get("usage")
        return resp_json["choices"][0]["message"]["content"]

    async def stream_chat(self, messages: List[Message], config: LLMConfig) -> AsyncGenerator[str, None]:
        url = config.base_url or "https://openrouter.ai/api/v1/chat/completions"
        
        # Validate API key
        if not config.api_key or config.api_key.strip() == "":
            raise ValueError("OpenRouter API key is missing or empty. Cannot proceed with LLM request.")
        
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "AI Investment Advisor",
        }
        
        # Build request data with all required fields
        data = {
            "model": config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "max_tokens": config.max_tokens or 2048,
        }
        
        if config.temperature is not None:
            data["temperature"] = config.temperature

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", url, headers=headers, json=data, timeout=config.timeout_seconds) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line:
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    if "choices" in chunk and chunk["choices"]:
                                        delta = chunk["choices"][0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                except json.JSONDecodeError:
                                    continue
        except httpx.HTTPError as e:
            # Log detailed error info for debugging
            error_msg = f"OpenRouter API error in stream: {e}"
            import logging
            logging.error(error_msg)
            raise

    async def embed(self, text: str, config: LLMConfig) -> List[float]:
        """OpenRouter embedding (uses /embeddings endpoint)."""
        url = config.base_url or "https://openrouter.ai/api/v1/embeddings"
        
        # Validate API key
        if not config.api_key or config.api_key.strip() == "":
            raise ValueError("OpenRouter API key is missing or empty. Cannot proceed with embedding request.")
        
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": config.model,
            "input": text,
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, headers=headers, json=data,
                    timeout=config.timeout_seconds,
                )
            response.raise_for_status()
        except httpx.HTTPError as e:
            # Log detailed error info for debugging
            error_msg = f"OpenRouter embedding API error: {e}"
            if hasattr(response, 'text'):
                error_msg += f"\nResponse body: {response.text}"
            import logging
            logging.error(error_msg)
            raise
        
        return response.json()["data"][0]["embedding"]


class GeminiGateway(ILLMGateway):
    """
    LLM Gateway for Google Gemini API.
    Google Gemini API 的 LLM 閘道實作。
    """

    def __init__(self):
        self._last_usage: Optional[dict] = None

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
        model_id = config.model if config.model.startswith("models/") else f"models/{config.model}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent?key={config.api_key}"
        headers = {"Content-Type": "application/json"}

        combined_text = ""
        for m in messages:
            combined_text += m.content + "\n\n"

        data = {
            "contents": [{"parts": [{"text": combined_text.strip()}]}],
        }
        if config.temperature is not None:
            data["generationConfig"] = {"temperature": config.temperature}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, headers=headers, json=data,
                timeout=config.timeout_seconds,
            )
        response.raise_for_status()
        resp_json = response.json()

        usage = resp_json.get("usageMetadata")
        if usage:
            self._last_usage = {
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0)
            }
        
        return resp_json["candidates"][0]["content"]["parts"][0]["text"]

    async def stream_chat(self, messages: List[Message], config: LLMConfig) -> AsyncGenerator[str, None]:
        model_id = config.model if config.model.startswith("models/") else f"models/{config.model}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:streamGenerateContent?alt=sse&key={config.api_key}"
        headers = {"Content-Type": "application/json"}

        combined_text = ""
        for m in messages:
            combined_text += m.content + "\n\n"

        data = {
            "contents": [{"parts": [{"text": combined_text.strip()}]}],
        }
        if config.temperature is not None:
            data["generationConfig"] = {"temperature": config.temperature}

        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, headers=headers, json=data, timeout=config.timeout_seconds) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line:
                        if line.startswith("data: "):
                            try:
                                chunk = json.loads(line[6:])
                                if "candidates" in chunk and chunk["candidates"]:
                                    parts = chunk["candidates"][0].get("content", {}).get("parts", [])
                                    for p in parts:
                                        content = p.get("text", "")
                                        if content:
                                            yield content
                            except (json.JSONDecodeError, KeyError):
                                continue

    async def embed(self, text: str, config: LLMConfig) -> List[float]:
        """Gemini embedding via embedContent API."""
        model_id = config.model if config.model.startswith("models/") else f"models/{config.model}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:embedContent?key={config.api_key}"
        headers = {"Content-Type": "application/json"}
        data = {"content": {"parts": [{"text": text}]}}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, headers=headers, json=data,
                timeout=config.timeout_seconds,
            )
        response.raise_for_status()
        return response.json()["embedding"]["values"]


class OpenAIGateway(ILLMGateway):
    """
    LLM Gateway for OpenAI-compatible APIs.
    OpenAI 相容 API 的 LLM 閘道實作。
    """

    def __init__(self):
        self._last_usage: Optional[dict] = None

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
        url = config.base_url or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if config.temperature is not None:
            data["temperature"] = config.temperature

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, headers=headers, json=data,
                timeout=config.timeout_seconds,
            )
        response.raise_for_status()
        resp_json = response.json()
        self._last_usage = resp_json.get("usage")
        return resp_json["choices"][0]["message"]["content"]

    async def stream_chat(self, messages: List[Message], config: LLMConfig) -> AsyncGenerator[str, None]:
        url = config.base_url or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        if config.temperature is not None:
            data["temperature"] = config.temperature

        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, headers=headers, json=data, timeout=config.timeout_seconds) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line:
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                if "choices" in chunk and chunk["choices"]:
                                    delta = chunk["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue

    async def embed(self, text: str, config: LLMConfig) -> List[float]:
        """OpenAI embedding via /v1/embeddings."""
        url = config.base_url.rstrip("/").replace("/chat/completions", "") + "/embeddings" if config.base_url else "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": config.model,
            "input": text,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, headers=headers, json=data,
                timeout=config.timeout_seconds,
            )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]


class LLMGatewayFactory:
    """
    Factory for creating ILLMGateway instances based on provider name.
    """

    _REGISTRY = {
        "OpenRouter": OpenRouterGateway,
        "openrouter": OpenRouterGateway,
        "Google Gemini": GeminiGateway,
        "google_gemini": GeminiGateway,
        "gemini": GeminiGateway,
        "OpenAI": OpenAIGateway,
        "openai": OpenAIGateway,
    }

    @classmethod
    def create(cls, provider: str) -> ILLMGateway:
        gateway_cls = cls._REGISTRY.get(provider)
        if gateway_cls is None:
            supported = sorted(set(cls._REGISTRY.values()), key=lambda c: c.__name__)
            supported_names = [c.__name__ for c in supported]
            raise ValueError(
                f"Unsupported LLM provider: '{provider}'. "
                f"Supported: {supported_names}"
            )
        return gateway_cls()

    @classmethod
    def register(cls, provider_name: str, gateway_cls: type) -> None:
        cls._REGISTRY[provider_name] = gateway_cls


class RetryLLMGateway(ILLMGateway):
    """
    Decorator Gateway that adds retry logic.
    """

    def __init__(self, inner: ILLMGateway, max_retries: int = 3):
        self._inner = inner
        self._max_retries = max_retries

    @property
    def _last_usage(self) -> Optional[dict]:
        return getattr(self._inner, "_last_usage", None)

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
        last_error = None
        for attempt in range(self._max_retries):
            try:
                return await self._inner.chat(messages, config)
            except Exception as e:
                last_error = e
                wait = 2 ** (attempt + 1)
                logger.warning(
                    f"LLM chat attempt {attempt + 1}/{self._max_retries} failed: "
                    f"{_redact_secrets(str(e))}. Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)
        raise last_error

    async def stream_chat(self, messages: List[Message], config: LLMConfig) -> AsyncGenerator[str, None]:
        # Retry logic for streaming is simplified (no backoff between chunks)
        async for chunk in self._inner.stream_chat(messages, config):
            yield chunk

    async def embed(self, text: str, config: LLMConfig) -> List[float]:
        last_error = None
        for attempt in range(self._max_retries):
            try:
                return await self._inner.embed(text, config)
            except Exception as e:
                last_error = e
                wait = 2 ** (attempt + 1)
                logger.warning(
                    f"LLM embed attempt {attempt + 1}/{self._max_retries} failed: "
                    f"{_redact_secrets(str(e))}. Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)
        raise last_error


class LoggingLLMGateway(ILLMGateway):
    """
    Decorator Gateway that logs LLM usage and costs to a central service.
    """

    def __init__(
        self,
        inner: ILLMGateway,
        agent_name: str,
        tier: str,
        user_id: str,
        metadata: dict = None,
    ):
        self._inner = inner
        self._agent_name = agent_name
        self._tier = tier
        self._user_id = user_id
        self._metadata = metadata or {}

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
        from opentelemetry import trace
        tracer = trace.get_tracer(__name__)
        
        with tracer.start_as_current_span(f"LLM.{self._agent_name}.chat") as span:
            span.set_attribute("llm.model", config.model)
            span.set_attribute("agent.name", self._agent_name)
            
            # T16.3: SaaS Quota and Tier Access Enforcement [Phase 16]
            try:
                from src.services.billing_service import BillingService
                billing = BillingService(user_id=self._user_id)
                billing.check_quota(requested_tier=self._tier)
            except Exception as e:
                # If QuotaExceeded or TierAccessDenied, we re-raise to block execution
                logger.error(f"LLM Gateway: Request blocked by billing policy: {e}")
                raise e
            
            # T13.1: Semantic Cache lookup
            try:
                from src.repositories.vector_cache_repository import VectorCacheRepository
                cache_repo = VectorCacheRepository()
                # Use a combined prompt string for caching
                prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])
                
                # We need the embedding for semantic search
                # We reuse the gateway's embed function
                # v13.1: Only cache for 'smart' or 'advanced' tiers where cost is higher
                if self._tier in ('smart', 'advanced'):
                    prompt_embedding = await self.embed(prompt_text, config)
                    cached_res = cache_repo.get_cached_response(self._user_id, prompt_text, prompt_embedding)
                    if cached_res:
                        span.set_attribute("cache.hit", True)
                        return cached_res
            except Exception as e:
                logger.warning(f"Cache lookup bypassed due to error: {e}")
                prompt_embedding = None
            else:
                prompt_embedding = None
            
            # T11.4: PII Redaction before sending to external API
            redacted_messages = [
                Message(role=m.role, content=_redact_pii(m.content)) for m in messages
            ]
            
            try:
                # v19.3: AI Model Automatic Fallback on Rate Limit [Phase 19]
                content = await self._inner.chat(redacted_messages, config)
            except Exception as e:
                # Common rate limit strings in error messages
                is_rate_limit = any(s in str(e).lower() for s in ("429", "rate limit", "quota exceeded"))
                
                # Only fallback if it's a rate limit and we are using a premium tier
                if is_rate_limit and self._tier in ('smart', 'advanced'):
                    logger.warning(f"LLM Gateway: [{self._agent_name}] '{self._tier}' limit hit. Falling back to 'fast' tier.")
                    from src.infrastructure.llm.tier_config import TierConfig
                    fallback_config = TierConfig().resolve('fast') # Resolve a fast model
                    
                    # Create a new config for the fallback
                    new_cfg = LLMConfig(
                        provider=config.provider, 
                        model=fallback_config, 
                        api_key=config.api_key,
                        temperature=config.temperature
                    )
                    content = await self._inner.chat(redacted_messages, new_cfg)
                    content = "*(注意：由於高階模型目前載載過高，本分析由高速模型生成備援)*\n\n" + content
                else:
                    raise e
            
            # T14.1: Log usage for observability and cost tracking
            usage = getattr(self._inner, "_last_usage", None)
            if usage:
                try:
                    from src.repositories.usage_repository import UsageRepository
                    usage_repo = UsageRepository()
                    # Execute logging in background to avoid blocking
                    asyncio.create_task(asyncio.to_thread(
                        usage_repo.log_usage,
                        user_id=self._user_id,
                        agent_name=self._agent_name,
                        tier=self._tier,
                        model=config.model,
                        provider=config.provider or "unknown",
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        metadata=self._metadata
                    ))
                except Exception as e:
                    logger.warning(f"Failed to log LLM usage: {e}")

            # T13.1: Save result to semantic cache if it was a miss
            if self._tier in ('smart', 'advanced') and prompt_embedding:
                 try:
                     cache_repo.save_cache(self._user_id, prompt_text, prompt_embedding, content)
                 except Exception:
                     pass

            return content

    async def stream_chat(self, messages: List[Message], config: LLMConfig) -> AsyncGenerator[str, None]:
        from opentelemetry import trace
        tracer = trace.get_tracer(__name__)
        
        with tracer.start_as_current_span(f"LLM.{self._agent_name}.stream") as span:
            span.set_attribute("llm.model", config.model)
            span.set_attribute("agent.name", self._agent_name)
            # T11.4: PII Redaction for streaming
            redacted_messages = [
                Message(role=m.role, content=_redact_pii(m.content)) for m in messages
            ]
            async for chunk in self._inner.stream_chat(redacted_messages, config):
                yield chunk

    async def embed(self, text: str, config: LLMConfig) -> List[float]:
        from opentelemetry import trace
        tracer = trace.get_tracer(__name__)
        
        with tracer.start_as_current_span(f"LLM.{self._agent_name}.embed") as span:
            span.set_attribute("llm.model", config.model)
            span.set_attribute("agent.name", self._agent_name)
            # T11.4: PII Redaction for embedding
            return await self._inner.embed(_redact_pii(text), config)


class MockLLMGateway(ILLMGateway):
    """
    Mock Gateway for testing and simulation mode.
    """

    def __init__(self, default_response: str = None):
        self._default_response = default_response

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
        if self._default_response:
            return self._default_response

        prompt_len = sum(len(m.content) for m in messages)
        return (
            f"### ⚠️ Simulation Mode (Missing API Key)\n\n"
            f"**Provider**: {config.provider}\n"
            f"**Model**: {config.model}\n\n"
            f"- **Trend**: Neutral.\n"
            f"- **Signal**: HOLD.\n"
            f"(Context size: {prompt_len} chars)"
        )

    async def stream_chat(self, messages: List[Message], config: LLMConfig) -> AsyncGenerator[str, None]:
        resp = await self.chat(messages, config)
        for word in resp.split(" "):
            yield word + " "
            await asyncio.sleep(0.02)

    async def embed(self, text: str, config: LLMConfig) -> List[float]:
        return [0.0] * 1536
