---
name: deploy
description: Deployment verification checklist
---

# Deploy Command

Verify the application is ready for deployment.

## Usage

```
/deploy
```

## What This Does

Run comprehensive deployment readiness checks:

1. **Implementation verification**
2. **Test coverage**
3. **Configuration validation**
4. **Security audit**
5. **Performance checks**

## Verification Checklist

### 1. Implementation Complete

- [ ] FastAPI routes implemented
- [ ] Health/Ready endpoints implemented (`/health`, `/health/deps`)
- [ ] Graceful shutdown implemented (lifespan)
- [ ] Logging configured (structured JSON)
- [ ] Error handling for all endpoints

**Check:**
```bash
# Verify health endpoints
grep -r "/health" backend/src/main.py

# Verify lifespan
grep -r "lifespan" backend/src/main.py
```

### 2. Testing

- [ ] Unit tests (>= 80% coverage)
- [ ] Integration tests written
- [ ] External APIs mocked
- [ ] Error cases tested
- [ ] All tests passing

**Check:**
```bash
cd backend && pytest tests/ --cov=src --cov-fail-under=80
```

### 3. Configuration

- [ ] .env.example provided
- [ ] Environment variables validated (Pydantic Settings)
- [ ] No hardcoded secrets
- [ ] pyproject.toml dependencies complete

**Check:**
```bash
# Verify .env.example exists
ls .env.example

# Check for hardcoded secrets
grep -r "sk-" backend/src/ | grep -v ".env"  # Should be empty
```

### 4. Security

- [ ] API keys loaded from environment
- [ ] SQL queries parameterized (no f-strings in queries)
- [ ] Input validation implemented (Pydantic models)
- [ ] No secrets in logs
- [ ] Decimal used for money

**Check:**
```bash
# Check for float money calculations
grep -r "float.*price\|float.*amount" backend/src/  # Should be empty

# Verify Decimal usage
grep -r "from decimal import Decimal" backend/src/
```

### 5. Performance

- [ ] Connection pooling configured (SQLAlchemy)
- [ ] Redis connection reuse
- [ ] Async operations parallelized
- [ ] No blocking operations

**Check:**
```bash
# Verify async usage
grep -r "async def" backend/src/ | wc -l

# Check for blocking operations
grep -r "time.sleep\|requests\." backend/src/ | grep -v test
```

### 6. Docker Integration

- [ ] Added to docker-compose.yml
- [ ] Service port exposed
- [ ] Environment variables mapped
- [ ] Dependencies declared (postgres, redis)

**Check:**
```bash
# Verify service in docker-compose
grep -A 10 "backend:" docker-compose.yml
```

### 7. Monitoring

- [ ] Structured logging implemented
- [ ] Metrics exposed (if needed)
- [ ] Error tracking configured

## Example Output

```bash
$ /deploy

Verifying deployment readiness...

OK Implementation
  OK FastAPI routes implemented
  OK Health endpoints present
  OK Graceful shutdown implemented

OK Testing
  OK Coverage: 93% (threshold: 80%)
  OK All tests passing (24 passed)
  OK External APIs mocked

OK Configuration
  OK .env.example present
  OK No hardcoded secrets
  OK pyproject.toml complete

OK Security
  OK Environment variables validated
  OK Decimal used for money
  FAIL Missing input validation for symbol field

FAIL Performance
  FAIL Missing connection pooling for database

Summary: 5/7 categories passed
Action required before deployment.
```

## Manual Verification

After automated checks, manually verify:

1. **Test locally**
   ```bash
   docker-compose up backend
   curl http://localhost:8000/health
   ```

2. **Check logs**
   ```bash
   docker-compose logs -f backend
   ```

3. **Test API endpoint**
   ```bash
   curl http://localhost:8000/api/v1/tasks
   ```

## Deployment

Once all checks pass:

```bash
# Build image
docker-compose build backend

# Deploy
docker-compose up -d backend

# Verify health
curl http://localhost:8000/health
```
