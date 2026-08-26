import pytest
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock
from src.repositories.memory_repository import AgentState
from src.domain.interfaces import Message, LLMConfig
from src.infrastructure.llm.resilient_pipeline import ModelCandidate, ResilientLLMPipeline
from src.infrastructure.llm.llm_config_chain import build_config_chain
from src.services.council_service import CouncilService
from src.services.outcome_reflection_service import OutcomeReflectionService


# ──────────────────────────────────────────────────────────────────────
# AgentState Tests
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_workspace():
    # Setup temporary directory for workspace testing
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


def test_agent_state_get_path(temp_workspace):
    state_mgr = AgentState(workspace_root=temp_workspace)
    path = state_mgr.get_state_path("Macro")
    assert path.endswith("macro-evaluator/STATE.md")


def test_agent_state_load_empty(temp_workspace):
    state_mgr = AgentState(workspace_root=temp_workspace)
    rules = state_mgr.load_general_rules("Macro")
    assert rules == ""


def test_agent_state_save_and_load(temp_workspace):
    state_mgr = AgentState(workspace_root=temp_workspace)
    rules_content = "- Rule 1: Always check volume\n- Rule 2: Don't buy TSLA at ATH"
    
    state_mgr.save_general_rules("Macro", rules_content)
    
    loaded_rules = state_mgr.load_general_rules("Macro")
    assert loaded_rules == rules_content


def test_agent_state_save_and_load_with_existing_file(temp_workspace):
    state_mgr = AgentState(workspace_root=temp_workspace)
    path = state_mgr.get_state_path("Macro")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write("# STATE\n\n## Verified Facts\n- The sky is blue\n\n## General Rules\n- Old Rule\n\n## Last Failures\n- None")
        
    loaded = state_mgr.load_general_rules("Macro")
    assert loaded == "- Old Rule"
    
    state_mgr.save_general_rules("Macro", "- New Rule")
    
    new_loaded = state_mgr.load_general_rules("Macro")
    assert new_loaded == "- New Rule"
    
    # Verify other sections were preserved
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "## Verified Facts" in content
    assert "- The sky is blue" in content


# ──────────────────────────────────────────────────────────────────────
# CouncilService Prompt Injection & Verifier Isolation Tests
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_council_service_injects_rules(temp_workspace):
    state_mgr = AgentState(workspace_root=temp_workspace)
    state_mgr.save_general_rules("Macro", "- Always test volume")

    with patch('src.services.council_service.AlchemyVectorRepository'), \
         patch('src.services.council_service.LaneManager'), \
         patch('src.services.council_service.AlchemySettingsRepository'), \
         patch('src.data.database.get_db_engine'):

        service = CouncilService(user_id="test_user")

        with patch('src.infrastructure.llm.llm_config_chain.build_config_chain') as mock_build_chain:
            mock_build_chain.return_value = [
                ModelCandidate("model-1", "openrouter", "google/gemini", MagicMock(), max_retries=0)
            ]
            with patch('src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute', new_callable=AsyncMock) as mock_execute:
                mock_execute.return_value = ("Success response", None)
                with patch('src.utils.prompt_utils.load_agent_prompt', return_value="Base prompt content") as mock_load_prompt:

                    # Temporarily redirect workspace to temp_workspace
                    with patch('src.repositories.memory_repository.AgentState.get_state_path', side_effect=state_mgr.get_state_path), \
                         patch('src.data.database.get_db_engine', side_effect=Exception("no DB in unit test — exercise the STATE.md fallback path")):
                        await service._call_agent_llm("Macro", {"topic": "TSLA"}, tier="smart")
                        
                        mock_execute.assert_called_once()
                        messages = mock_execute.call_args[0][0]
                        system_msg = next(m for m in messages if m.role == "system")
                        assert "## Dynamic Rules" in system_msg.content
                        assert "- Always test volume" in system_msg.content


@pytest.mark.asyncio
async def test_council_service_verifier_isolation():
    with patch('src.services.council_service.AlchemyVectorRepository'), \
         patch('src.services.council_service.LaneManager'), \
         patch('src.services.council_service.AlchemySettingsRepository'), \
         patch('src.data.database.get_db_engine'):
        
        service = CouncilService(user_id="test_user")
        
        # We want to mock _call_agent_llm calls and check the arguments
        with patch.object(service, '_call_agent_llm', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Mock decision"
            
            with patch('src.services.user_focus_service.UserFocusService.get_user_focus', new_callable=AsyncMock, return_value="Focus"):
                with patch.object(service, '_archive_minutes'):
                    with patch.object(service, '_verify_grounding', new_callable=AsyncMock) as mock_verify:
                        mock_verify.return_value = "No issues"
                        
                        await service._run_debate_logic(
                            session_id="123",
                            topic="TSLA analysis",
                            context_data={"market_data": {"price": 200}},
                            user_id="test_user"
                        )
                        
                        # Find the Risk agent challenge call in mock_call
                        challenge_calls = [args for args in mock_call.call_args_list if args[0][0] == "Risk" and "draft_decision" in args[0][1]]
                        assert len(challenge_calls) == 1
                        
                        risk_context = challenge_calls[0][0][1]
                        assert "council_transcript" not in risk_context
                        assert risk_context["market_data"] == {"price": 200}
                        assert risk_context["draft_decision"] == "Mock decision"


# ──────────────────────────────────────────────────────────────────────
# OutcomeReflectionService Failure Distillation Tests
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_outcome_reflection_failure_distillation(temp_workspace):
    # Setup temporary AgentState
    state_mgr = AgentState(workspace_root=temp_workspace)
    
    with patch('src.data.database.get_db_engine'):
        service = OutcomeReflectionService(user_id="test_user")
        
        # Stub the required database queries and LLM execution
        with patch.object(service, '_generate_lesson', return_value="Lesson about Nvidia"):
            with patch.object(service, 'engine') as mock_engine:
                with patch('src.infrastructure.llm.llm_config_chain.build_config_chain') as mock_build_chain:
                    mock_build_chain.return_value = [
                        ModelCandidate("model-1", "openrouter", "google/gemini", MagicMock(), max_retries=0)
                    ]
                    with patch('src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute', new_callable=AsyncMock) as mock_execute:
                        mock_execute.return_value = ("- Avoid trading NVDA high Beta at earnings", None)
                        
                        with patch('src.repositories.memory_repository.AgentState.get_state_path', side_effect=state_mgr.get_state_path):
                            from datetime import datetime, timedelta, timezone
                            row = {
                                "id": "uuid-123",
                                "ticker": "NVDA",
                                "signal": "BUY",
                                "price_at_decision": 100.0,
                                "decided_at": datetime.now(timezone.utc) - timedelta(days=10),
                                "horizon_days": 5,
                                "agent_name": "Momentum"
                            }
                            
                            # Realized: $80, SPY Realized: $100 -> negative alpha
                            # realized_pct = -20%, benchmark_pct = 0% -> alpha = -20%
                            with patch.object(service, '_fetch_price', return_value=80.0):
                                with patch.object(service, '_fetch_benchmark_window', return_value=(100.0, 100.0)):
                                    # AgentState.save_general_rules/load_general_rules call
                                    # src.data.database.get_db_engine fresh each time (not
                                    # service.engine) — override it to raise so both calls
                                    # exercise the real STATE.md fallback path this test
                                    # actually verifies, instead of a MagicMock chain from
                                    # the outer blanket patch.
                                    with patch('src.data.database.get_db_engine',
                                               side_effect=Exception("no DB in unit test — exercise the STATE.md fallback path")):
                                        resolved = service._resolve_one(row)

                                        assert resolved is True
                                        # Ensure general rules were NOT saved to STATE.md because status='candidate'
                                        rules = state_mgr.load_general_rules("Momentum")
                                        assert rules == ""


# ──────────────────────────────────────────────────────────────────────
# LLMConfig extra_config & Headers Propagation Tests
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_config_extra_config_propagation():
    candidate = ModelCandidate(
        model_id="model-1",
        provider_code="openrouter",
        model_code="google/gemini",
        gateway_class=MagicMock(),
        max_retries=0,
        extra_config={
            "temperature": 0.1,
            "max_tokens": 150,
            "headers": {"Cache-Control": "ephem"}
        }
    )
    
    pipeline = ResilientLLMPipeline(config_chain=[candidate])
    config = pipeline._build_llm_config(candidate)
    
    assert config.temperature == 0.1
    assert config.max_tokens == 150
    assert config.extra_config["headers"] == {"Cache-Control": "ephem"}
