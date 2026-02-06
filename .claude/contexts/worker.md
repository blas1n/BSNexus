---
context: worker
description: Implementation mode - building features
---

# Worker Context

You are implementing BSNexus backend features. Focus on clean, tested code.

## Current Phase

Phase 1: Foundation (Monolithic FastAPI backend)

**Reference**: [docs/internal/tasks/](../../docs/internal/tasks/)

## Your Role

1. **Implement tasks** from the task list
2. **Write tests** alongside code (80%+ coverage)
3. **Follow standards** in `.claude/rules/`
4. **Ask questions** when requirements are unclear

## Before You Start

Read:
- Task definition
- Relevant architecture docs
- `.claude/rules/architecture.md`

## Implementation Pattern

1. **Define Pydantic schemas** for request/response
2. **Implement business logic** in service layer
3. **Create FastAPI router** with dependency injection
4. **Write unit tests**
5. **Add integration tests** if cross-module
6. **Verify with** `/deploy`

## Critical Rules

Always follow `.claude/rules/`:
- **FastAPI** with async/await throughout
- **Redis Streams** for messaging (not Pub/Sub)
- **LiteLLM** for LLM calls (not direct provider SDKs)
- **Type hints** required on all functions
- **Tests required** (80%+ coverage)
- **Decimal for money**
- **Pydantic** for all request/response schemas

## Code Quality

Before committing:
- [ ] Type hints on all functions
- [ ] Tests written and passing
- [ ] External APIs mocked
- [ ] Errors handled with proper HTTP status codes
- [ ] No hardcoded secrets
- [ ] Structured logging used

## Reference Documents

- `.claude/rules/architecture.md`: Architectural guidelines
- `.claude/rules/testing.md`: Testing patterns
- `.claude/rules/security.md`: Security requirements

## Communication

- **Progress**: Update todos
- **Blockers**: Ask questions immediately
- **Decisions**: Document in code comments
- **Completion**: Run `/deploy` checklist
