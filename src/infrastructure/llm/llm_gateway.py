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

from src.domain.interfaces import (
    ILLMGateway, Message, LLMConfig,
    PingResult, DiscoveredModel,
)
from src.utils.security import redact_secrets as _redact_secrets, redact_pii as _redact_pii
from src.utils.tracing import trace_external_call

logger = logging.getLogger(__name__)

from src.infrastructure.llm.model_id_resolver import resolve_model_id

class OpenRouterGateway(ILLMGateway):
    """
    LLM Gateway for OpenRouter API.
    OpenRouter API 的 LLM 閘道實作。
    """

    def __init__(self):
        self._last_usage: Optional[dict] = None

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
        base = (config.base_url or "https://openrouter.ai/api/v1").rstrip("/")
        url = base if base.endswith("/chat/completions") else base + "/chat/completions"

        # Validate API key
        if not config.api_key or config.api_key.strip() == "":
            raise ValueError("OpenRouter API key is missing or empty. Cannot proceed with LLM request.")
        
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "AI Investment Advisor",
        }
        if config.extra_config and "headers" in config.extra_config:
            headers.update(config.extra_config["headers"])
        
        # Resolve model ID via centralized resolver (TTL Cached)
        actual_model_id = resolve_model_id(config.model, "openrouter")

        data = {
            "model": actual_model_id,
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
        except httpx.HTTPStatusError as e:
            model_id = getattr(config, 'model', 'unknown')
            logger.error(
                f"OpenRouter HTTP error {e.response.status_code} | "
                f"Model: {model_id} | "
                f"URL: {e.request.url} | "
                f"Response: {e.response.text[:1000]}"
            )
            raise
        except httpx.HTTPError as e:
            logger.error(f"OpenRouter API error: {e}")
            raise
        
        try:
            resp_json = response.json()
        except json.JSONDecodeError as e:
            error_preview = response.text[:200]
            if "<!DOCTYPE html>" in error_preview.upper() or "<HTML" in error_preview.upper():
                logger.error(f"OpenRouter Gateway: Provider returned HTML error page instead of JSON. Preview: {error_preview}")
                raise ValueError(f"OpenRouter API returned HTML error page (provider unavailable): {error_preview}...") from e
            logger.error(f"OpenRouter JSON Decode Error: {e} | Response: {response.text[:1000]}")
            raise ValueError(f"OpenRouter API returned invalid JSON: {error_preview}...") from e
            
        self._last_usage = resp_json.get("usage")
        msg = resp_json["choices"][0]["message"]
        return msg.get("content") or msg.get("reasoning_content") or ""

    async def stream_chat(self, messages: List[Message], config: LLMConfig) -> AsyncGenerator[str, None]:
        url = config.base_url or "https://openrouter.ai/api/v1/chat/completions"

        actual_model_id = resolve_model_id(config.model, "openrouter")
        
        
        # Validate API key
        if not config.api_key or config.api_key.strip() == "":
            raise ValueError("OpenRouter API key is missing or empty. Cannot proceed with LLM request.")
        
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "AI Investment Advisor",
        }
        if config.extra_config and "headers" in config.extra_config:
            headers.update(config.extra_config["headers"])
        
        # Build request data with all required fields
        data = {
            "model": actual_model_id,
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
        actual_model_id = resolve_model_id(config.model, "openrouter")
        data = {
            "model": actual_model_id,
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
    async def ping(self, config: LLMConfig) -> PingResult:
        """Probe OpenRouter via public models endpoint (no auth required for ping)."""
        url = "https://openrouter.ai/api/v1/models"
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=config.timeout_seconds)
            response.raise_for_status()
            latency_ms = (time.perf_counter() - start) * 1000.0
            return PingResult(ok=True, latency_ms=latency_ms)
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000.0
            logger.warning("OpenRouterGateway.ping failed: %s", e)
            return PingResult(ok=False, latency_ms=latency_ms, error=str(e))

    async def list_models(self, config: LLMConfig) -> List[DiscoveredModel]:
        """Discover models via OpenRouter's public `/api/v1/models` endpoint."""
        from src.infrastructure.llm.discovery_parsers import parse_openai_models
        
        url = "https://openrouter.ai/api/v1/models"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=config.timeout_seconds)
        response.raise_for_status()
        return parse_openai_models(response.json())


class GeminiGateway(ILLMGateway):
    """
    LLM Gateway for Google Gemini API.
    Google Gemini API 的 LLM 閘道實作。
    """

    def __init__(self):
        self._last_usage: Optional[dict] = None

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
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
            response = await client.post(
                url, headers=headers, json=data,
                timeout=config.timeout_seconds,
            )
        response.raise_for_status()
        try:
            resp_json = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Gemini JSON Decode Error: {e} | Response: {response.text[:1000]}")
            raise ValueError(f"Gemini API returned invalid JSON: {response.text[:200]}") from e

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
        import requests
        def _sync_embed():
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
    async def ping(self, config: LLMConfig) -> PingResult:
        """Probe Gemini via API key validation on models endpoint."""
        if not config.api_key:
            return PingResult(ok=False, latency_ms=0, error="Google API Key is missing.")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={config.api_key}"
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=config.timeout_seconds)
            response.raise_for_status()
            latency_ms = (time.perf_counter() - start) * 1000.0
            return PingResult(ok=True, latency_ms=latency_ms)
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000.0
            logger.warning("GeminiGateway.ping failed: %s", e)
            return PingResult(ok=False, latency_ms=latency_ms, error=str(e))

    async def list_models(self, config: LLMConfig) -> List[DiscoveredModel]:
        """Discover models via Google Gemini `/v1beta/models` endpoint."""
        from src.infrastructure.llm.discovery_parsers import parse_gemini_models
        
        if not config.api_key:
            raise ValueError("Google API Key is required for model discovery.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={config.api_key}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=config.timeout_seconds)
        response.raise_for_status()
        return parse_gemini_models(response.json())


class OpenAIGateway(ILLMGateway):
    """
    LLM Gateway for OpenAI-compatible APIs.
    OpenAI 相容 API 的 LLM 閘道實作。
    """

    def __init__(self):
        self._last_usage: Optional[dict] = None

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
        base = (config.base_url or "https://api.openai.com/v1").rstrip("/")
        url = base if base.endswith("/chat/completions") else base + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        if config.extra_config and "headers" in config.extra_config:
            headers.update(config.extra_config["headers"])
        actual_model_id = resolve_model_id(config.model, "openai")
        data = {
            "model": actual_model_id,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if config.temperature is not None:
            data["temperature"] = config.temperature
        if config.max_tokens:
            data["max_tokens"] = config.max_tokens

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, headers=headers, json=data,
                timeout=config.timeout_seconds,
            )
        response.raise_for_status()
        try:
            resp_json = response.json()
        except json.JSONDecodeError as e:
            error_preview = response.text[:200]
            if "<!DOCTYPE html>" in error_preview.upper() or "<HTML" in error_preview.upper():
                 logger.error(f"OpenAI Gateway: Provider returned HTML error page instead of JSON. Preview: {error_preview}")
                 raise ValueError(f"OpenAI API returned HTML error page (provider unavailable): {error_preview}...") from e
            logger.error(f"OpenAI JSON Decode Error: {e} | Response: {response.text[:1000]}")
            raise ValueError(f"OpenAI API returned invalid JSON: {error_preview}...") from e

        self._last_usage = resp_json.get("usage")
        msg = resp_json["choices"][0]["message"]
        return msg.get("content") or msg.get("reasoning_content") or ""

    async def stream_chat(self, messages: List[Message], config: LLMConfig) -> AsyncGenerator[str, None]:
        url = config.base_url or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        if config.extra_config and "headers" in config.extra_config:
            headers.update(config.extra_config["headers"])
        actual_model_id = resolve_model_id(config.model, "openai")
        data = {
            "model": actual_model_id,
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
        actual_model_id = resolve_model_id(config.model, "openai")
        data = {
            "model": actual_model_id,
            "input": text,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, headers=headers, json=data,
                timeout=config.timeout_seconds,
            )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]
    async def ping(self, config: LLMConfig) -> PingResult:
        """Probe OpenAI (or compatible) via `/v1/models` (requires auth)."""
        if not config.api_key:
             return PingResult(ok=False, latency_ms=0, error="API Key is missing.")

        url = config.base_url.rstrip("/").replace("/chat/completions", "") + "/models" if config.base_url else "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {config.api_key}"}
        
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=config.timeout_seconds)
            response.raise_for_status()
            latency_ms = (time.perf_counter() - start) * 1000.0
            return PingResult(ok=True, latency_ms=latency_ms)
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000.0
            logger.warning("OpenAIGateway.ping failed: %s", e)
            return PingResult(ok=False, latency_ms=latency_ms, error=str(e))

    async def list_models(self, config: LLMConfig) -> List[DiscoveredModel]:
        """Discover models via OpenAI-compatible `/v1/models` endpoint."""
        from src.infrastructure.llm.discovery_parsers import parse_openai_models
        
        if not config.api_key:
            raise ValueError("API Key is required for model discovery.")

        url = config.base_url.rstrip("/").replace("/chat/completions", "") + "/models" if config.base_url else "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {config.api_key}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=config.timeout_seconds)
        response.raise_for_status()
        return parse_openai_models(response.json())


class OllamaGateway(OpenAIGateway):
    """
    Ollama local-model Gateway.

    Ollama exposes an OpenAI-compatible `/v1/chat/completions` endpoint, so we
    reuse `OpenAIGateway`'s chat / stream / embed. We override `list_models`
    to hit the native `/api/tags` endpoint (which returns richer info than
    the OpenAI-style `/v1/models`), and provide `ping()` that just probes
    `/api/tags` — Ollama needs no auth.
    """

    DEFAULT_BASE_URL = "http://localhost:11434/v1"

    def __init__(self):
        super().__init__()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_v1(base_url: Optional[str]) -> str:
        """
        Given an OpenAI-compat base_url ending with `/v1`, return the root
        so we can append `/api/tags`. If no `/v1` suffix, return as-is.
        """
        url = (base_url or OllamaGateway.DEFAULT_BASE_URL).rstrip("/")
        if url.endswith("/v1"):
            return url[: -len("/v1")]
        return url

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------
    async def ping(self, config: LLMConfig) -> PingResult:
        """Probe Ollama daemon via `/api/tags`. Success ⇒ healthy (200 OK)."""
        url = self._strip_v1(config.base_url) + "/api/tags"
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=config.timeout_seconds)
            response.raise_for_status()
            latency_ms = (time.perf_counter() - start) * 1000.0
            payload = response.json()
            models = payload.get("models") or []
            return PingResult(
                ok=True,
                latency_ms=latency_ms,
                detail={"available_models": len(models)},
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000.0
            logger.warning("OllamaGateway.ping failed: %s", e)
            return PingResult(ok=False, latency_ms=latency_ms, error=str(e))

    async def list_models(self, config: LLMConfig) -> List[DiscoveredModel]:
        """
        Discover locally pulled models via Ollama's `GET /api/tags`.

        Response shape (Ollama >= 0.1):
            {
              "models": [
                {
                  "name": "qwen2.5:7b",
                  "modified_at": "...",
                  "size": 4730000000,
                  "details": {
                     "parameter_size": "7.6B",
                     "family": "qwen2",
                     ...
                  }
                }, ...
              ]
            }
        """
        # Defer parsing to discovery_parsers to keep logic unit-testable.
        from src.infrastructure.llm.discovery_parsers import parse_ollama_tags

        url = self._strip_v1(config.base_url) + "/api/tags"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=config.timeout_seconds)
        response.raise_for_status()
        return parse_ollama_tags(response.json())


class NvidiaGateway(OpenAIGateway):
    """
    NVIDIA NIM Gateway — OpenAI-compatible inference at integrate.api.nvidia.com.
    Inherits all OpenAIGateway logic; only overrides the fallback base URL.
    """

    _CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

    def _resolve_config(self, config: LLMConfig) -> LLMConfig:
        if not config.base_url:
            import dataclasses
            return dataclasses.replace(config, base_url=self._CHAT_URL)
        return config

    async def chat(self, messages: List[Message], config: LLMConfig) -> str:
        return await super().chat(messages, self._resolve_config(config))

    async def stream_chat(self, messages: List[Message], config: LLMConfig) -> AsyncGenerator[str, None]:
        async for chunk in super().stream_chat(messages, self._resolve_config(config)):
            yield chunk

    async def ping(self, config: LLMConfig) -> PingResult:
        return await super().ping(self._resolve_config(config))

    async def list_models(self, config: LLMConfig) -> List[DiscoveredModel]:
        conf = self._resolve_config(config)
        base = conf.base_url.rstrip("/").replace("/chat/completions", "")
        if not base or "integrate.api.nvidia.com" not in base:
            base = "https://integrate.api.nvidia.com/v1"
        url = f"{base}/models"
        headers = {}
        if conf.api_key:
            headers["Authorization"] = f"Bearer {conf.api_key}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=conf.timeout_seconds)
        response.raise_for_status()
        from src.infrastructure.llm.discovery_parsers import parse_openai_models
        return parse_openai_models(response.json())


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
        "Ollama": OllamaGateway,
        "ollama": OllamaGateway,
        "Nvidia": NvidiaGateway,
        "nvidia": NvidiaGateway,
        "NVIDIA": NvidiaGateway,
        "mock": MockLLMGateway,
    }

    @classmethod
    def create(cls, provider: str) -> ILLMGateway:
        gateway_cls = cls._REGISTRY.get(provider)
        if gateway_cls is None:
            supported_names = sorted(list(cls._REGISTRY.keys()))
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
            is_tier_fallback = False
            try:
                from src.services.billing_service import BillingService, TierAccessDeniedError
                billing = BillingService(user_id=self._user_id)
                try:
                    billing.check_quota(requested_tier=self._tier)
                except TierAccessDeniedError as e:
                    # v20.1: Automatic Downgrade on Tier Denial [Phase 20]
                    if self._tier in ('smart', 'advanced'):
                        logger.warning(f"LLM Gateway: Agent '{self._agent_name}' tier '{self._tier}' denied. Falling back to 'fast'.")
                        is_tier_fallback = True
                        from src.infrastructure.llm.tier_config import TierConfig
                        fallback_model = TierConfig().resolve('fast')
                        
                        import dataclasses
                        config = dataclasses.replace(config, model=fallback_model)
                        
                        # Re-verify quota for fast tier
                        billing.check_quota(requested_tier='fast')
                    else:
                        raise e
            except Exception as e:
                # If QuotaExceeded or TierAccessDenied (after fallback attempt), we re-raise
                logger.error(f"LLM Gateway: Request blocked by billing policy: {e}")
                raise e
            
            # T13.1: Semantic Cache lookup
            content = None # Initialize to avoid UnboundLocalError
            try:
                from src.repositories.vector_cache_repository import VectorCacheRepository
                cache_repo = VectorCacheRepository()
                # Use a combined prompt string for caching
                prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])
                
                # We need the embedding for semantic search
                # We reuse the gateway's embed function
                # v13.1: Only cache for 'smart' or 'advanced' tiers where cost is higher
                # [Fix] If we fell back, we might still want to check cache for the original tier or just skip
                if not is_tier_fallback and self._tier in ('smart', 'advanced'):
                    prompt_embedding = await self.embed(prompt_text, config)
                    # 2026-08-02: run the pgvector similarity search on a
                    # worker thread. This is synchronous DB I/O inside an
                    # `async def`, so on the loop thread it stalls every other
                    # in-flight request. Matches the asyncio.to_thread usage
                    # already applied to usage logging further down.
                    # 2026-08-02：pgvector 相似度查詢是同步 DB I/O，留在 event loop
                    # 上會卡住所有其他請求，改丟 worker thread。
                    import asyncio as _asyncio
                    cached_res = await _asyncio.to_thread(
                        cache_repo.get_cached_response,
                        self._user_id, prompt_text, prompt_embedding,
                    )
                    if cached_res:
                        span.set_attribute("cache.hit", True)
                        return cached_res
            except Exception as e:
                logger.warning(f"Cache lookup bypassed due to error: {e}")
                prompt_embedding = None
            
            # T11.4: PII Redaction before sending to external API
            redacted_messages = [
                Message(role=m.role, content=_redact_pii(m.content)) for m in messages
            ]
            
            try:
                # v19.3: AI Model Automatic Fallback on Rate Limit [Phase 19]
                content = await self._inner.chat(redacted_messages, config)
                
                # If we were in a tier fallback, prepend the note
                if is_tier_fallback and content:
                    # Note: Prepending text here might break naive JSON parsers. 
                    # Use src.utils.json_utils.json_loads_safe which handles this robustly.
                    content = "*(注意：由於高階模型權限限制，本分析已自動切換至高速模型生成)*\n\n" + content
                    
            except Exception as e:
                # Common rate limit strings in error messages
                is_rate_limit = any(s in str(e).lower() for s in ("429", "rate limit", "quota exceeded"))
                
                # Only fallback if it's a rate limit and we are using a premium tier
                # And only if we haven't already fallen back due to tier denial
                if not is_tier_fallback and is_rate_limit and self._tier in ('smart', 'advanced'):
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
                    # Note: Prepending text here might break naive JSON parsers. 
                    # Use src.utils.json_utils.json_loads_safe which handles this robustly.
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
                     # 2026-08-02: off the loop thread, same reasoning as the
                     # cache read above. A FRESH repository instance is used
                     # because sessions are per-instance and this runs on a
                     # different worker thread than the read did.
                     # 2026-08-02：同樣移出 event loop；因 session 現在是 per-instance
                     # 且這裡在另一條 worker thread，需用新的 repository 實例。
                     import asyncio as _asyncio
                     from src.repositories.vector_cache_repository import (
                         VectorCacheRepository as _VecRepo,
                     )
                     await _asyncio.to_thread(
                         _VecRepo().save_cache,
                         self._user_id, prompt_text, prompt_embedding, content,
                     )
                 except Exception as e:
                     logger.warning(f'Exception in llm_gateway.py: {e}', exc_info=True)

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

        # Force a dedicated embedding model, avoiding Text Generation models.
        # LLMConfig is a frozen dataclass — use dataclasses.replace() with the
        # new model value directly instead of post-assignment.
        import dataclasses
        provider = (config.provider or "").lower()
        if "openrouter" in provider:
            embed_model = "text-embedding-3-small"  # OpenRouter resolves this to OpenAI
        elif "gemini" in provider:
            embed_model = "text-embedding-004"
        elif "openai" in provider:
            embed_model = "text-embedding-3-small"
        else:
            embed_model = config.model  # keep original for other providers
        embed_config = dataclasses.replace(config, model=embed_model)

        with tracer.start_as_current_span(f"LLM.{self._agent_name}.embed") as span:
            span.set_attribute("llm.model", embed_config.model)
            span.set_attribute("agent.name", self._agent_name)
            # T11.4: PII Redaction for embedding
            return await self._inner.embed(_redact_pii(text), embed_config)

    async def stream_chat(self, messages: List[Message], config: LLMConfig) -> typing.AsyncGenerator[str, None]:
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

