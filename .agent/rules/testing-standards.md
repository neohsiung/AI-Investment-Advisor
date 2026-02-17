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

## Rules & Coverage Policy

### 1. Coverage Targets
- 🎯 **Total Coverage Target**: > 75%
- ⚠️ **CI/CD Threshold**: > 70% (`pytest.ini`: `fail_under = 70`)
- **Layer Specifics**:
    - **Services**: > 80% (Core business logic)
    - **Repositories**: > 75% (Persistence reliability)
    - **Domain**: > 85% (Model stability)
    - **Error Handling**: 100% (Mandatory)

### 2. Mandatory Tests
- **New Features**: Every new service, repository, or agent must include happy path, error paths, and edge cases.
- **Error Paths**: Must explicitly test 401, 403, 429, 500 API errors, timeouts, and DB constraints.
- **No External Calls**: All external APIs (Futu, Schwab, OpenAI) MUST be mocked.

### 3. Best Practices
- **Fixture Reuse**: Use `conftest.py` for shared mocks.
- **Clean Teardown**: Ensure `sys.modules` and DBs are cleaned up after each test.
- **Service over UI**: Prioritize testing the service layer; UI tests are optional (aim for > 50% if implemented).

## Debugging Mindset (Troubleshooting Hierarchy)
When a test fails, follow this hierarchy:
1. **Unpack Density**: Is the code-under-test too complex? Refactor if setup is difficult.
2. **Isolation Check**: Is the failure caused by a spilled dependency? Verify mocks in `conftest.py`.
3. **Hierarchy Validation**: If an integration test fails, reproduce it with a faster unit test first.

## Execution
Use the `/test-coverage-check` workflow to verify status before PR submission.
