---
description: Testing Standards & Pyramid
---
# Testing Standards

## Core Philosophy: The Testing Pyramid
All development must adhere to the **Testing Pyramid** strategy to ensure a robust, maintainable, and fast feedback loop.

### 1. Unit Tests (Base Layer - 70%)
- **Scope**: Single function, class, or method.
- **Dependencies**: STRICTLY mocked. No DB, no Network, no File I/O.
- **Goal**: Verify logic correctness in isolation.
- **Speed**: < 0.1s per test.
- **Location**: `tests/` matching source structure.

### 2. Integration Tests (Middle Layer - 20%)
- **Scope**: Interaction between 2+ modules (e.g., Service + Repository).
- **Dependencies**: Use in-memory DB (sqlite) or strictly controlled local mocks.
- **Goal**: Verify component contracts and data flow.
- **Speed**: < 1s per test.

### 3. E2E / Endpoint Tests (Top Layer - 10%)
- **Scope**: Full user flows (CLI commands, API endpoints).
- **Dependencies**: Minimal mocking (e.g., only external 3rd party APIs).
- **Goal**: Verify system integrity.
- **Critical**: These are expensive; keep them focused on critical paths (Smoke Tests).

## Rules
1. **No External Calls**: All external APIs (Futu, Schwab, OpenAI) MUST be mocked.
2. **Fixture Reuse**: Use `conftest.py` for shared mocks (MockServices).
3. **Clean Teardown**: Ensure `sys.modules` and DBs are cleaned up.
4. **Coverage**: Minimum 75% overall.

## Debugging Mindset (Troubleshooting Hierarchy)
When a test fails, DO NOT immediately try to fix the test logic or mock. Follow this thought process:
1. **Unpack Density**: Is the code-under-test doing too much? If the setup is complex, refactor the code into smaller, pure unit-testable components.
2. **Isolation Check**: Is the failure caused by a spilled dependency? Verify mocks in `conftest.py`.
3. **Hierarchy Validation**: If an Integration test fails, can it be reproduced by a faster Unit test? Always prioritize Unit test fixes.
