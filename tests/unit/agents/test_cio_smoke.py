"""
Smoke test: CIOAgent constructs.

This test used to perform module surgery — inside a
`patch.dict('sys.modules', ...)` block it did
`del sys.modules['src.agents.cio']` and re-imported the module, so that:

  * a NEW module object was created inside the block, and
  * on exit `patch.dict` restored the mapping it had SAVED, which (depending on
    whether the module had been imported before the test ran) could leave
    `src.agents.cio` either pointing at a different object or missing from
    sys.modules entirely.

That broke later tests in a way that only appeared in a full-suite run: with the
module absent or rebound, `patch("src.agents.cio.CIOAgent")` in
tests/unit/services/test_factory.py no longer intercepted the class the agent
factory actually constructed, and two factory tests failed while passing in
isolation.

The deletion was never needed. `google`/`openai` are optional imports guarded
inside the module, so it imports fine without them mocked, and mocking
`src.utils.logger` is unnecessary.

本測試原本在 patch.dict 區塊內刪除並重新匯入 src.agents.cio，導致離開區塊後該模組
可能指向不同物件或完全不在 sys.modules 中。這會讓後續測試在「整套執行」時才失敗
（單獨執行則通過）——test_factory 的 patch 因此攔截不到工廠實際建構的類別。
刪除模組從來就不必要。
"""
from unittest.mock import MagicMock, mock_open, patch

from src.agents.cio import CIOAgent


def test_cio_agent_init():
    with patch("builtins.open", mock_open(read_data="Prompt Content")), \
         patch("src.agents.base_agent.BaseAgent._load_config", return_value={"provider": "OpenAI"}), \
         patch("src.agents.cio.CIOAgent._load_config", return_value={"provider": "OpenAI"}):

        agent = CIOAgent(
            settings_repo=MagicMock(),
            transaction_repo=MagicMock(),
        )
        assert agent is not None
        assert agent.name == "CIO"


def test_cio_agent_does_not_disturb_module_state():
    """
    Guard against the surgery coming back: whatever this module does, the import
    system must look the same afterwards.
    確保本模組執行後，import 狀態與執行前一致。
    """
    import sys

    assert "src.agents.cio" in sys.modules
    module = sys.modules["src.agents.cio"]

    # A patch of the class must be visible to a lazy `from ... import` — this is
    # exactly what src/agents/impls.py does when the factory builds a CIO agent.
    with patch("src.agents.cio.CIOAgent") as mocked:
        from src.agents.cio import CIOAgent as seen

        assert seen is mocked

    assert sys.modules["src.agents.cio"] is module
