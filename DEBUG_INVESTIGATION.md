# Test Failure Investigation: test_run_tool_loop_search

## Task Summary
- **Test File**: `tests/unit/agents/test_base_agent_coverage.py:89-108`
- **Test Name**: `test_run_tool_loop_search`
- **Issue**: Mock called with `('AAPL')` but expected `('AAPL', max_results=3)`
- **Root Cause Investigation**: Trace `BaseAgent.run_tool_loop()` execution path

---

## PHASE 1: PROBLEM IDENTIFICATION & CALL CHAIN ANALYSIS

### 1.1 Test Assertion
```python
# Line 108 in test_base_agent_coverage.py
mock_svc.search_financial_context.assert_called_with("AAPL", max_results=3)
```

### 1.2 Actual Call Stack

The test flow is:
```
test_run_tool_loop_search()
  ↓
agent.run_tool_loop(context)  [BaseAgent.run_tool_loop, line 336]
  ↓
self._agent_loop.execute(messages, call_llm_fn, ...)  [BaseAgent.run_tool_loop, line 353]
  ↓
AgentLoop.execute() → parse_tool_call() → _execute_tool_async(name, args)  [AgentLoop, lines 59-112]
  ↓
_execute_tool_async("SEARCH", {"query": "AAPL"})  [AgentLoop, line 102]
  ↓
_run_tool_logic_async("SEARCH", {"query": "AAPL"})  [AgentLoop, line 128]
  ↓
_execute_search_async(query)  [AgentLoop, lines 166-170]
  ↓
search_financial_context(query, max_results=3)  [AgentLoop, line 188]
```

### 1.3 Key Code Sections

#### Section A: BaseAgent.run_tool_loop (line 336-359)
```python
async def run_tool_loop(self, context, max_turns=3, thought_chain=False):
    # ... setup messages ...
    
    # Lazy-init search service for legacy SEARCH handler
    from src.services.search_service import InternetSearchService
    self._agent_loop._search_service = InternetSearchService(user_id=self.user_id)  # ← Service initialized
    
    response = await self._agent_loop.execute(
        messages=messages,
        call_llm_fn=self.call_llm,
        # ... other params ...
        max_turns=max_turns,
    )
```

#### Section B: AgentLoop._run_tool_logic_async (lines 154-179)
```python
async def _run_tool_logic_async(self, name: str, args: Dict[str, Any]) -> str:
    # T10.2: Handle Legacy SEARCH
    if name == "SEARCH":
        if self._search_service:
            query = args.get("query", "")
            return await self._execute_search_async(query)  # ← Args unpacked
        return "Error: Search service not initialized."
```

#### Section C: AgentLoop._execute_search_async (lines 186-196)
```python
async def _execute_search_async(self, query: str) -> str:
    res_list = await self._search_service.search_financial_context(
        query,  # ← Query parameter
        max_results=3  # ← max_results explicitly passed
    )
```

#### Section D: InternetSearchService.search_financial_context (line 69)
```python
async def search_financial_context(self, query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Search for financial context."""
```

---

## PHASE 2: ROOT CAUSE ANALYSIS

### 2.1 Code Path Verification

✅ **Verified**: The call chain DOES pass `max_results=3` to `search_financial_context()`

**Evidence**:
- AgentLoop._execute_search_async() calls: `await self._search_service.search_financial_context(query, max_results=3)` (line 188)
- This is explicitly in the code

### 2.2 Potential Issue Points

#### Issue Point 1: Mock Setup vs. Actual Service Call
The test mocks `InternetSearchService` class at line 102:
```python
with patch('src.services.search_service.InternetSearchService') as mock_search_cls:
    mock_svc = mock_search_cls.return_value
    mock_svc.search_financial_context = AsyncMock(return_value=[...])
```

But BaseAgent initializes it separately at line 351:
```python
from src.services.search_service import InternetSearchService
self._agent_loop._search_service = InternetSearchService(user_id=self.user_id)
```

**Impact**: The patch happens AFTER BaseAgent.run_tool_loop() already calls line 350-351 (the import and initialization happen inside run_tool_loop).

#### Issue Point 2: Order of Operations in Test
1. Line 102: Patch applied inside `with` block
2. Line 106: `await agent.run_tool_loop(context)` called
3. Line 350-351 in run_tool_loop: **NEW** InternetSearchService instance created

**Critical**: The patch IS applied BEFORE run_tool_loop() is called, so it should intercept the constructor.

### 2.3 Hypothesis Testing

**Hypothesis 1**: Mock might not be capturing the actual call properly
- **Test Status**: ✅ PASSED (mock assertion works correctly)
- **Conclusion**: Mock is working fine

**Hypothesis 2**: Service might be None
- **Evidence**: Code checks `if self._search_service:` before calling
- **Status**: ✅ Would return "Error: Search service not initialized" if None

**Hypothesis 3**: Different code path taken
- **Analysis**: SEARCH parsing happens at line 210 in parse_tool_call()
- **Verified**: Line 210 creates tuple `("SEARCH", {"query": query})`

---

## PHASE 2B: DETAILED EXECUTION TRACE

### Execution Flow Trace:

1. **test_run_tool_loop_search** (test_base_agent_coverage.py:89)
   - Mock created: `mock_svc.search_financial_context = AsyncMock(...)`
   - Mock assertion: `mock_svc.search_financial_context.assert_called_with("AAPL", max_results=3)`

2. **agent.run_tool_loop({})** (base_agent.py:336)
   - Lines 350-351: Creates NEW InternetSearchService(user_id=self.user_id)
   - ✅ Patch intercepts this → Creates mocked instance
   - Assigns to: `self._agent_loop._search_service = InternetSearchService(...)`

3. **self._agent_loop.execute()** (base_agent.py:353)
   - Calls AgentLoop.execute() with mocked service attached

4. **AgentLoop.execute()** (agent_loop.py:59)
   - Line 92: Calls LLM (mocked to return 'SEARCH: "AAPL"')
   - Line 95: Parses tool call
   - Line 102: Calls _execute_tool_async("SEARCH", {"query": "AAPL"})

5. **_execute_tool_async("SEARCH", {"query": "AAPL"})** (agent_loop.py:114)
   - Line 128: Calls _run_tool_logic_async("SEARCH", {"query": "AAPL"})

6. **_run_tool_logic_async("SEARCH", {"query": "AAPL"})** (agent_loop.py:154)
   - Line 167: Checks if name == "SEARCH" → ✅ TRUE
   - Line 168: Checks if self._search_service → ✅ TRUE (mocked instance)
   - Line 169: Extracts query = "AAPL"
   - Line 169: Calls _execute_search_async("AAPL")

7. **_execute_search_async("AAPL")** (agent_loop.py:186)
   - ✅ Line 188: Calls `await self._search_service.search_financial_context("AAPL", max_results=3)`
   - This is where max_results=3 IS passed

8. **Mock Assertion** (test_base_agent_coverage.py:108)
   - Mock call recorded: `search_financial_context("AAPL", max_results=3)`
   - ✅ PASSES

---

## PHASE 2C: FINDINGS

### ✅ TEST STATUS: **PASSING**

The test currently **PASSES** because:

1. **Code Path is Correct**: The `_execute_search_async()` method explicitly passes `max_results=3` to `search_financial_context()`

2. **Mock Captures It Correctly**: The AsyncMock in the test properly captures both positional and keyword arguments

3. **No Issues Found in Flow**: The entire call chain from `run_tool_loop()` through `AgentLoop.execute()` down to `_execute_search_async()` works as designed

### Code Correctness Summary:

| Component | Responsibility | Status | Evidence |
|-----------|-----------------|--------|----------|
| test_base_agent_coverage.py | Verify mock calls | ✅ PASS | Test passes |
| BaseAgent.run_tool_loop() | Initialize search service | ✅ CORRECT | Line 351 |
| AgentLoop.execute() | Parse and dispatch tools | ✅ CORRECT | Lines 95-102 |
| AgentLoop._run_tool_logic_async() | Route to SEARCH handler | ✅ CORRECT | Lines 166-170 |
| AgentLoop._execute_search_async() | **Call with max_results=3** | ✅ CORRECT | **Line 188** |
| InternetSearchService.search_financial_context() | Accept max_results parameter | ✅ CORRECT | Line 69 |

---

## CONCLUSION

### Root Cause Analysis Result:
**NO ISSUE FOUND** - The test is passing and the implementation is correct.

### Key Implementation Details:
- `AgentLoop._execute_search_async()` (line 188) **ALWAYS** passes `max_results=3` to the search service
- This is the intended behavior for financial searches - limiting results to 3 for quality and performance
- The parameter is correctly passed through the entire call chain

### Recommendations:
1. ✅ No code changes needed - current implementation is working correctly
2. If test was previously failing, the recent commit (ba01644) may have fixed the async/await handling
3. All integration points properly cascade the `max_results` parameter

---

## Test Execution Verification

```
tests/unit/agents/test_base_agent_coverage.py::TestBaseAgentCoverage::test_run_tool_loop_search PASSED [100%]

Execution time: 3.26s
Status: ✅ PASSING
```

**Date**: April 13, 2026
**Investigation**: Phase 1-2 Complete
