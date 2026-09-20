"""
Agent implementations, published to the registry.

Each function here wraps one agent class and is the only thing a manifest's
`impl:` key may name. They exist as a thin layer rather than registering the
classes directly because the classes take different constructor arguments —
swarms do not accept `use_cache`, CIO takes a `mode` — and the manifest should
not have to know that.

The ten entries below are a transcription of the if/elif chain that was in
AgentFactory.create_agent, preserving each branch's exact constructor call.

此處每個函式包裝一個代理類別，是 manifest 的 `impl:` 唯一可指名的東西。
用薄封裝而非直接註冊類別，是因為各類別建構參數不同（swarm 不吃 use_cache、
CIO 有 mode），manifest 不該需要知道這些。下列十項是原 if/elif 鏈的逐一轉錄。
"""
from __future__ import annotations

from typing import Any

from src.agents.registry import AgentManifest, register_agent


def _persona_for(manifest: AgentManifest):
    """Resolve the manifest's named persona, if it has one."""
    if not manifest.persona:
        return None
    from src.agents.persona.persona_provider import get_default_persona_provider

    return get_default_persona_provider().get_persona(manifest.persona)


def _common(manifest: AgentManifest, kwargs: dict) -> dict:
    """
    Manifest-derived constructor arguments, with explicit kwargs taking priority.

    A caller passing `tier=` or `persona=` explicitly must still win — the
    workflow YAML sets a per-node tier, and that is more specific than the
    agent's own default.
    呼叫端明確傳入的參數優先：workflow YAML 的 per-node tier 比代理預設值更specific。
    """
    out = dict(kwargs)
    out.setdefault("manifest", manifest)
    if manifest.persona and "persona" not in out:
        persona = _persona_for(manifest)
        if persona is not None:
            out["persona"] = persona
    return out


@register_agent("cio")
def _cio(manifest: AgentManifest, use_cache: bool = True, user_id: str = None,
         mode: str = None, **kwargs) -> Any:
    from src.agents.cio import CIOAgent

    args = _common(manifest, kwargs)
    args.pop("manifest", None)
    if mode is not None:
        args["mode"] = mode
    return CIOAgent(use_cache=use_cache, user_id=user_id, **args)


@register_agent("conversation")
def _conversation(manifest: AgentManifest, use_cache: bool = True, user_id: str = None,
                  **kwargs) -> Any:
    """
    Conversational role. Uses the CIO implementation in daily mode — this is what
    the old `elif name_lower == 'conversation'` branch did.
    對話角色沿用 CIO 實作的 daily 模式，與原 conversation 分支相同。
    """
    from src.agents.cio import CIOAgent

    args = _common(manifest, kwargs)
    args.pop("manifest", None)
    args.setdefault("mode", "daily")
    return CIOAgent(use_cache=use_cache, user_id=user_id, **args)


@register_agent("macro")
def _macro(manifest: AgentManifest, use_cache: bool = True, user_id: str = None, **kwargs) -> Any:
    from src.agents.macro import MacroAgent

    args = _common(manifest, kwargs)
    args.pop("manifest", None)
    return MacroAgent(use_cache=use_cache, user_id=user_id, **args)


@register_agent("risk")
def _risk(manifest: AgentManifest, use_cache: bool = True, user_id: str = None, **kwargs) -> Any:
    from src.agents.risk import RiskAgent

    args = _common(manifest, kwargs)
    args.pop("manifest", None)
    return RiskAgent(use_cache=use_cache, user_id=user_id, **args)


@register_agent("thematic")
def _thematic(manifest: AgentManifest, use_cache: bool = True, user_id: str = None, **kwargs) -> Any:
    from src.agents.thematic import ThematicAgent

    args = _common(manifest, kwargs)
    args.pop("manifest", None)
    return ThematicAgent(use_cache=use_cache, user_id=user_id, **args)


@register_agent("sentinel")
def _sentinel(manifest: AgentManifest, use_cache: bool = True, user_id: str = None, **kwargs) -> Any:
    from src.agents.sentinel import SentinelAgent

    args = _common(manifest, kwargs)
    args.pop("manifest", None)
    return SentinelAgent(use_cache=use_cache, user_id=user_id, **args)


@register_agent("engineer")
def _engineer(manifest: AgentManifest, use_cache: bool = True, user_id: str = None, **kwargs) -> Any:
    from src.agents.system_engineer_agent import SystemEngineerAgent

    args = _common(manifest, kwargs)
    args.pop("manifest", None)
    return SystemEngineerAgent(use_cache=use_cache, user_id=user_id, **args)


# Swarms manage their own sub-agent tiers and do NOT accept use_cache —
# passing it was a TypeError in the original chain too, which is why those
# branches omitted it.
# swarm 自行管理子代理 tier，且不接受 use_cache（原本的分支也因此省略它）。
@register_agent("momentum_swarm")
def _momentum(manifest: AgentManifest, user_id: str = None, **kwargs) -> Any:
    from src.agents.swarm.momentum_swarm import MomentumSwarm

    args = _common(manifest, kwargs)
    args.pop("manifest", None)
    args.pop("use_cache", None)
    return MomentumSwarm(user_id=user_id, **args)


@register_agent("fundamental_swarm")
def _fundamental(manifest: AgentManifest, user_id: str = None, **kwargs) -> Any:
    from src.agents.swarm.fundamental_swarm import FundamentalSwarm

    args = _common(manifest, kwargs)
    args.pop("manifest", None)
    args.pop("use_cache", None)
    return FundamentalSwarm(user_id=user_id, **args)


@register_agent("sentiment_swarm")
def _sentiment(manifest: AgentManifest, user_id: str = None, **kwargs) -> Any:
    from src.agents.swarm.sentiment_swarm import SentimentSwarm

    args = _common(manifest, kwargs)
    args.pop("manifest", None)
    args.pop("use_cache", None)
    return SentimentSwarm(user_id=user_id, **args)
