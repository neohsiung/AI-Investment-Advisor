"""
Memory-layer naming and reachability guards (2026-08-13).

Two things this pins:

1. **No two memory classes share a name.** `CognitiveMemoryManager` used to be
   defined in *both* `src/services/cognitive_memory_manager.py` (a memory store:
   `store_insight` / `get_recent_memories` / `archive_to_long_term`, five
   callers) and `src/infrastructure/memory/cognitive_memory.py` (a DIKW
   distillation pipeline, one caller). They shared nothing but the name, so
   `from ... import CognitiveMemoryManager` resolved to a completely different
   object depending on which module path was typed — and both paths look
   plausible from a call site. The pipeline is now `DikwDistillationPipeline`.

2. **The modules deleted in this pass stay deleted.** Ten zero-import modules
   (~1200 LOC) plus `three_tier_memory` and `memory_factory` were removed. If
   one is restored, it should be because something imports it — not because it
   was copied back in.

同名不同物的兩個 CognitiveMemoryManager 已更名區分；本輪刪除的死碼模組不應悄悄回來。
"""
import importlib

import pytest


def test_cognitive_memory_manager_name_is_not_shared():
    store = importlib.import_module("src.services.cognitive_memory_manager")
    pipeline = importlib.import_module("src.infrastructure.memory.cognitive_memory")

    assert hasattr(store, "CognitiveMemoryManager")
    assert not hasattr(pipeline, "CognitiveMemoryManager"), (
        "the DIKW pipeline is exporting CognitiveMemoryManager again — that name "
        "belongs to the memory store in src/services/cognitive_memory_manager.py"
    )
    assert hasattr(pipeline, "DikwDistillationPipeline")


def test_the_two_classes_remain_different_shapes():
    """A store and a pipeline. If these ever converge, merge them deliberately
    rather than letting the names drift back together."""
    from src.infrastructure.memory.cognitive_memory import DikwDistillationPipeline
    from src.services.cognitive_memory_manager import CognitiveMemoryManager

    store_api = {"store_insight", "get_recent_memories", "archive_to_long_term"}
    pipeline_api = {"compact_stm_to_episodic", "distill_episodic_to_knowledge",
                    "crystallize_knowledge_to_wisdom"}

    assert store_api <= set(dir(CognitiveMemoryManager))
    assert pipeline_api <= set(dir(DikwDistillationPipeline))
    assert not (store_api & set(dir(DikwDistillationPipeline)))


DELETED_MODULES = [
    "src.infrastructure.llm_router",
    "src.infrastructure.llm.agent_tier_mapping_loader",
    "src.infrastructure.llm.enterprise_router",
    "src.infrastructure.mcp.tool_loader",
    "src.infrastructure.scrapers.crawl4ai_scraper",
    "src.infrastructure.streaming_scheduler",
    "src.services.backtesting_engine",
    "src.services.browser_service",
    "src.services.event_agents.rebalance_worker",
    "src.services.portfolio_optimizer_service",
    "src.infrastructure.memory.three_tier_memory",
    "src.services.memory_factory",
]


@pytest.mark.parametrize("module", DELETED_MODULES)
def test_deleted_module_stays_deleted(module):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_live_memory_modules_are_still_importable():
    """The counterweight: this pass deliberately kept the memory modules that
    have real callers. `unified_memory_service` in particular was on the
    delete list until `ConversationAgent` turned out to use it on the live
    reply path."""
    for module in [
        "src.services.cognitive_memory_manager",
        "src.services.memory_service",
        "src.services.memory_distillation_service",
        "src.services.unified_memory_service",
        "src.infrastructure.memory.memory_manager",
        "src.infrastructure.memory.channel_memory_manager",
        "src.infrastructure.memory.cognitive_memory",
    ]:
        assert importlib.import_module(module) is not None
