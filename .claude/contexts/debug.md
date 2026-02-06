---
context: debug
description: Debugging mode - diagnosing and fixing issues
---

# Debug Context

You are debugging issues in BSNexus. Systematic diagnosis is key.

## Debugging Workflow

### 1. Gather Information

**What to collect**:
- Error message (full traceback)
- Service logs
- Input that caused error
- Expected vs actual behavior

**Commands**:
```bash
# Service logs
docker-compose logs -f backend

# Specific time range
docker-compose logs --since 30m backend

# Follow logs with filter
docker-compose logs -f backend | grep ERROR
```

### 2. Reproduce Locally

**Steps**:
1. Isolate the failing component
2. Create minimal reproduction case
3. Run in debugger

**Example**:
```python
# Reproduce in test
@pytest.mark.asyncio
async def test_failing_case():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/tasks/999")
        assert response.status_code == 404
```

### 3. Common Issue Categories

#### FastAPI Errors

**422 Unprocessable Entity** (Validation error):
```python
# Check Pydantic model validation
from pydantic import ValidationError

try:
    TaskCreate(**data)
except ValidationError as e:
    print(e.errors())
```

**500 Internal Server Error** (Unhandled exception):
```bash
# Check full traceback in logs
docker-compose logs backend | grep -A 20 "Traceback"
```

**Dependency Injection Issues**:
```python
# Verify dependency is properly configured
from src.storage.database import get_db

# Check lifespan initialized resources
grep -r "lifespan" backend/src/main.py
```

#### Redis Streams Issues

**Connection refused**:
```bash
# Check Redis status
docker-compose ps redis

# Check logs
docker-compose logs redis

# Test connection
docker-compose exec redis redis-cli ping
```

**Consumer not receiving messages**:
```python
# Verify stream and consumer group exist
import redis.asyncio as aioredis

r = aioredis.from_url("redis://localhost:6379")

# Check stream info
await r.xinfo_stream("tasks:queue")

# Check consumer groups
await r.xinfo_groups("tasks:queue")

# Check pending messages
await r.xpending("tasks:queue", "workers")
```

**Messages not acknowledged**:
```python
# Check pending messages for a consumer
await r.xpending_range("tasks:queue", "workers", "-", "+", 10)

# Manually acknowledge
await r.xack("tasks:queue", "workers", message_id)
```

#### Database Issues

**Connection pool exhausted**:
```python
# Increase pool size
engine = create_async_engine(
    DATABASE_URL,
    pool_size=50,  # Increase from default
    max_overflow=10
)
```

**Slow queries**:
```python
# Enable query logging
engine = create_async_engine(
    DATABASE_URL,
    echo=True  # Log all queries
)
```

**Migration issues**:
```bash
# Check migration status
cd backend && alembic current

# Show migration history
cd backend && alembic history

# Downgrade if needed
cd backend && alembic downgrade -1
```

#### Redis Cache Issues

**Cache not working**:
```python
# Verify TTL
await redis.ttl('market:regime:current')  # Should return seconds remaining

# Check key exists
await redis.exists('market:regime:current')  # Should return 1 if exists
```

### 4. Debugging Tools

#### Python Debugger

```python
import pdb; pdb.set_trace()  # Breakpoint

# Or async version
import ipdb; await ipdb.set_trace()
```

#### Logging

```python
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add debug logs
logger.debug("Request received", extra={
    'task_id': task_id,
    'payload': payload
})
```

#### HTTP API Testing

```bash
# Test FastAPI endpoint
curl -X GET http://localhost:8000/api/v1/tasks

# Test with POST data
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "test", "description": "test task"}'

# Health check
curl http://localhost:8000/health

# Dependency health
curl http://localhost:8000/health/deps
```

#### Docker Debugging

```bash
# Enter container
docker-compose exec backend /bin/bash

# Check environment variables
docker-compose exec backend env

# Check file system
docker-compose exec backend ls -la /app
```

### 5. Performance Debugging

#### Find Slow Operations

```python
import time

async def timed_operation():
    start = time.time()
    result = await expensive_operation()
    duration = (time.time() - start) * 1000
    logger.warning(f"Slow operation: {duration}ms")
    return result
```

#### Profile Code

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Run code
await service.analyze()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumtime')
stats.print_stats(20)  # Top 20 slowest
```

### 6. Memory Debugging

```python
import tracemalloc

# Start tracking
tracemalloc.start()

# Run code
await service.analyze()

# Get stats
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)
```

## Issue Resolution Pattern

### 1. Identify Root Cause

- [ ] Read full error traceback
- [ ] Check service logs
- [ ] Verify configuration
- [ ] Test in isolation

### 2. Fix

- [ ] Implement fix
- [ ] Add test to prevent regression
- [ ] Verify fix locally
- [ ] Check for similar issues elsewhere

### 3. Prevent Recurrence

- [ ] Add validation
- [ ] Improve error messages
- [ ] Add monitoring
- [ ] Document solution

## Example Debugging Session

```
Issue: Task API returning stale data

1. Gather info:
   - Expected: Fresh task status
   - Actual: 2 hour old status
   - Error: None

2. Hypothesis: Redis cache not expiring

3. Investigation:
   docker-compose exec redis redis-cli
   > TTL tasks:cache:123
   (integer) -1  # Never expires!

4. Root cause: Missing TTL in cache set

5. Fix:
   # Before (bug)
   await redis.set('tasks:cache:123', data)

   # After (fixed)
   await redis.setex('tasks:cache:123', 21600, data)  # 6 hours

6. Test:
   @pytest.mark.asyncio
   async def test_cache_expiration():
       await service.cache_task(data)
       ttl = await redis.ttl('tasks:cache:123')
       assert ttl > 0  # Has expiration
       assert ttl <= 21600  # Within 6 hours

7. Deploy and verify
```

## When Stuck

1. **Review architecture docs** - Am I following the design?
2. **Check similar code** - How do other modules handle this?
3. **Read logs carefully** - Error message might be misleading
4. **Ask for help** - Describe what you've tried
