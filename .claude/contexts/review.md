---
context: review
description: Code review mode - verifying quality and compliance
---

# Review Context

You are reviewing code for BSNexus. Ensure adherence to standards and architecture.

## Review Checklist

### 1. Architecture Compliance

Verify against `.claude/rules/architecture.md`:

- [ ] FastAPI used with async/await throughout
- [ ] Redis Streams used for messaging (not Pub/Sub)
- [ ] LiteLLM used for LLM calls (not direct provider SDKs)
- [ ] Python 3.11+ (no other languages)
- [ ] Type hints on all public functions
- [ ] Decimal used for money (not float)
- [ ] Pydantic models for all request/response schemas

**Check:**
```bash
# Verify no blocking HTTP clients in production code
grep -r "import requests" backend/src/ | grep -v test

# Verify Redis Streams (not Pub/Sub)
grep -r "redis.*publish\b" backend/src/

# Verify type hints
grep -r "^async def.*->" backend/src/
```

### 2. Code Quality

Check `.claude/rules/`:

- [ ] Async/await used consistently
- [ ] Error handling with proper HTTP status codes
- [ ] Structured logging (JSON format)
- [ ] Environment variables (no hardcoded secrets)
- [ ] Input validation (Pydantic)
- [ ] Connection pooling (DB, Redis)

**Check:**
```python
# Good
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)) -> TaskResponse:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)

# Bad
def get_task(task_id):  # Missing async, type hints, DI
    task = db.query(Task).get(task_id)  # Blocking, no DI
    return task
```

### 3. Testing

Verify `.claude/rules/testing.md`:

- [ ] Unit tests present
- [ ] Coverage >= 80%
- [ ] External APIs mocked
- [ ] Integration tests (if cross-module)
- [ ] Error cases tested

**Run:**
```bash
cd backend && pytest tests/ --cov=src --cov-fail-under=80
```

### 4. Security

Check `.claude/rules/security.md`:

- [ ] No hardcoded API keys
- [ ] .env.example provided
- [ ] No secrets in logs
- [ ] Parameterized SQL queries (no f-strings)
- [ ] Input validation implemented
- [ ] Decimal for financial calculations

**Check:**
```bash
# Search for hardcoded secrets
grep -r "sk-\|api_key\s*=\s*\"" backend/src/ | grep -v ".env"

# Verify Decimal usage
grep -r "float.*price\|float.*amount" backend/src/
```

### 5. FastAPI Implementation

Verify `.claude/rules/architecture.md`:

- [ ] Routers organized by module
- [ ] Dependency injection for DB/Redis
- [ ] Lifespan for startup/shutdown
- [ ] Pydantic response models defined
- [ ] Proper HTTP status codes

**Check:**
```python
# Required pattern
router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)) -> TaskResponse:
    ...
```

### 6. Performance

- [ ] Async operations parallelized
- [ ] Database connection pooling
- [ ] Redis connection reuse
- [ ] No blocking operations

**Check:**
```python
# Good - parallel
regime, sectors, symbols = await asyncio.gather(
    get_regime(),
    get_sectors(),
    get_symbols()
)

# Bad - sequential
regime = await get_regime()
sectors = await get_sectors()
symbols = await get_symbols()
```

## Review Response Format

### Approve

```
APPROVED

All checks passed:
- Architecture compliance
- Code quality standards
- Test coverage (85%)
- Security requirements
- Performance optimized

No issues found.
```

### Request Changes

```
CHANGES REQUESTED

Issues found:

1. Architecture violation (HIGH)
   - Using blocking HTTP client
   - Location: src/services/ai.py:45
   - Fix: Use httpx.AsyncClient instead

2. Missing tests (HIGH)
   - Coverage: 65% (threshold: 80%)
   - Missing: src/api/tasks.py lines 78-95
   - Fix: Add unit tests for error cases

3. Security issue (CRITICAL)
   - Hardcoded API key
   - Location: src/config.py:12
   - Fix: Load from environment variable

Cannot approve until resolved.
```

## Common Issues

### Anti-patterns to Catch

1. **Blocking operations**
   ```python
   # Bad
   response = requests.get('http://example.com')

   # Good
   async with httpx.AsyncClient() as client:
       response = await client.get('http://example.com')
   ```

2. **Float for money**
   ```python
   # Bad
   total = 150.25 * 10

   # Good
   from decimal import Decimal
   total = Decimal('150.25') * Decimal('10')
   ```

3. **Missing type hints**
   ```python
   # Bad
   async def get_task(task_id):
       pass

   # Good
   async def get_task(task_id: int) -> TaskResponse:
       pass
   ```

4. **Direct LLM provider calls**
   ```python
   # Bad
   from openai import AsyncOpenAI
   client = AsyncOpenAI()

   # Good
   from litellm import acompletion
   response = await acompletion(model=settings.default_llm_model, ...)
   ```

## Final Verification

Before approving:
- [ ] Run `/deploy` checklist
- [ ] All automated checks pass
- [ ] No critical or high severity issues
- [ ] Code follows BSNexus patterns
