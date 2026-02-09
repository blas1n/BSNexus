---
name: test
description: Run tests with coverage verification
---

# Test Command

Run tests for the backend with coverage requirements.

## Usage

```
/test [module]
```

## What This Does

1. **Run tests** for specified module or the entire backend
2. **Check coverage** (minimum 80%)
3. **Report failures** with actionable feedback
4. **Verify mocks** for external APIs

## Implementation

### Full Backend

```bash
# Run all tests
cd backend && pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80
```

### Specific Module

```bash
# Run tests for a specific module
cd backend && pytest tests/test_tasks.py --cov=src --cov-report=term-missing --cov-fail-under=80
```

### Integration Tests

```bash
# Cross-module integration
cd backend && pytest tests/integration/
```

### E2E Tests

```bash
# Full workflow tests
cd backend && pytest tests/e2e/
```

## Coverage Requirements

- **Unit tests**: >= 80%
- **Core modules** (tasks, workers, AI): >= 80%
- **Utilities** (utils/): >= 90%

## Mock Verification

Ensure all external APIs are mocked:

```python
# Check for unmocked API calls
grep -r "httpx\." backend/src/ | grep -v test    # Should be empty
grep -r "litellm\." backend/src/ | grep -v test  # Should use mocks in tests
```

## Output

The command should report:
- Tests passed/failed
- Coverage percentage
- Uncovered lines
- Missing mocks

## Example

```bash
$ /test

Running tests for backend...

============================= test session starts ==============================
backend/tests/test_tasks.py ........                                     [100%]

---------- coverage: platform linux, python 3.11.6 -----------
Name                            Stmts   Miss  Cover   Missing
-------------------------------------------------------------
src/__init__.py                     0      0   100%
src/main.py                        45      3    93%   78-80
src/api/tasks.py                   67      5    93%   125-129
src/models.py                      34      2    94%   45-46
-------------------------------------------------------------
TOTAL                             146      10    93%

============================== 10 passed in 2.45s ==============================

Coverage: 93% (threshold: 80%)
All tests passed
```
