
# src/agents/settings_aware_model_router.py
"""智能模型路由器 - 根據認知層級選擇最佳模型"""

import json
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime
from pathlib import Path
from enum import Enum
import httpx

class ModelTier(str, Enum):
    DEEP_RESEARCH = "DeepResearch"
    MEMORY_DIG = "MemoryDig"
    FAST_THINK = "FastThink"
    REFLEXIVE = "Reflexive"

class ProviderType(str, Enum):
    OLLAMA = "ollama"
    NVIDIA_NIM = "nvidia_nim"
    OPENROUTER = "openrouter"

class SettingsAwareModelRouter:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.registry = self._load_registry()
        self.routing = self._load_routing()
        self.usage_metrics = {}
        self.cost_tracker = {}
        
    def _load_registry(self) -> Dict:
        with open(self.config_dir / "model_registry.json") as f:
            return json.load(f)
    
    def _load_routing(self) -> Dict:
        import yaml
        with open(self.config_dir / "model_routing.yaml") as f:
            return yaml.safe_load(f)
    
    async def route(self, request: str, tier: ModelTier) -> Dict[str, Any]:
        """主路由邏輯"""
        config = self.routing[tier.value]
        
        # 嘗試主模型
        result = await self._try_model(
            config['primary']['provider'],
            config['primary']['model'],
            request,
            tier
        )
        if result['success']:
            return result
        
        # 嘗試 fallback
        for fb in config['fallbacks']:
            result = await self._try_model(
                fb['provider'],
                fb['model'],
                request,
                tier,
                fallback_priority=fb['priority']
            )
            if result['success']:
                return result
        
        return {'success': False, 'error': 'All models failed'}
    
    async def _try_model(self, provider: str, model: str, 
                        request: str, tier: ModelTier,
                        fallback_priority: int = 0) -> Dict:
        try:
            if provider == 'ollama':
                response = await self._call_ollama(model, request)
            elif provider == 'nvidia_nim':
                response = await self._call_nim(model, request)
            elif provider == 'openrouter':
                response = await self._call_openrouter(model, request)
            
            self._record_success(provider, model, tier, response)
            return {
                'success': True,
                'provider': provider,
                'model': model,
                'response': response,
                'fallback': fallback_priority > 0
            }
        except Exception as e:
            self._record_failure(provider, model, tier, str(e))
            return {'success': False, 'provider': provider, 'error': str(e)}
    
    async def _call_ollama(self, model: str, prompt: str) -> Dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                'http://localhost:11434/api/generate',
                json={'model': model, 'prompt': prompt, 'stream': False},
                timeout=30
            )
            return r.json()
    
    async def _call_nim(self, model: str, text: str) -> Dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                'https://integrate.api.nvidia.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {self._get_nim_key()}'},
                json={'model': model, 'messages': [{'role': 'user', 'content': text}]},
                timeout=30
            )
            return r.json()
    
    async def _call_openrouter(self, model: str, text: str) -> Dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': f'Bearer {self._get_or_key()}'},
                json={'model': model, 'messages': [{'role': 'user', 'content': text}]}
            )
            return r.json()
    
    def _record_success(self, provider: str, model: str, tier: ModelTier, response):
        key = f'{provider}/{model}'
        if key not in self.usage_metrics:
            self.usage_metrics[key] = {'total': 0, 'success': 0, 'failed': 0}
        self.usage_metrics[key]['success'] += 1
        self.usage_metrics[key]['total'] += 1
    
    def _record_failure(self, provider: str, model: str, tier: ModelTier, error: str):
        key = f'{provider}/{model}'
        if key not in self.usage_metrics:
            self.usage_metrics[key] = {'total': 0, 'success': 0, 'failed': 0}
        self.usage_metrics[key]['failed'] += 1
        self.usage_metrics[key]['total'] += 1
    
    def get_metrics(self) -> Dict:
        return {
            'timestamp': datetime.now().isoformat(),
            'metrics': self.usage_metrics,
            'success_rate': self._calc_success_rate()
        }
    
    def _calc_success_rate(self) -> float:
        total_success = sum(m['success'] for m in self.usage_metrics.values())
        total = sum(m['total'] for m in self.usage_metrics.values())
        return (total_success / total * 100) if total > 0 else 0
    
    def _get_nim_key(self) -> str:
        import os
        return os.getenv('NVIDIA_NIM_API_KEY', '')
    
    def _get_or_key(self) -> str:
        import os
        return os.getenv('OPENROUTER_API_KEY', '')
