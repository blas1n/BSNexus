# Claude Code Configuration

BSNexus Claude Code setup for development workflow.

## Structure

```
.claude/
├── README.md           # This file
├── skills/             # Reusable patterns and standards
├── rules/              # Always-follow guidelines (enforced)
├── commands/           # Slash commands for quick actions
└── contexts/           # Mode-specific prompts
```

## Skills

**Reusable implementation patterns** that can be referenced when needed.

- **project-structure.md**: Folder hierarchy, naming conventions
- **testing-standards.md**: Test requirements and patterns
- **langgraph-patterns.md**: Multi-agent workflow patterns

**Usage**: Reference in implementation (e.g., "See `.claude/skills/testing-standards.md`")

## Rules

**Always-enforced guidelines** that must be followed in all code.

- **architecture.md**: Core architectural decisions (FastAPI monolith, Redis Streams, LiteLLM, etc.)
- **testing.md**: All code MUST have tests (≥80% coverage)
- **security.md**: Security requirements (no hardcoded secrets, Decimal for money, etc.)

**Enforcement**: Claude will check these before proceeding with implementation.

## Commands

**Slash commands** for common operations.

- `/test [module]`: Run tests with coverage
- `/module <name>`: Scaffold a new backend module (router + service + schema + test)
- `/deploy`: Verify deployment readiness
- `/architect`: Enable Architect mode for prompt-based task execution

**Usage**: Type `/test` in Claude Code to run tests.

## Contexts

**Mode-specific prompts** for different work types.

- **worker.md**: Implementation mode (building features)
- **review.md**: Code review mode (verifying quality)
- **debug.md**: Debugging mode (diagnosing issues)

**Usage**: Activated automatically based on task context.

## Quick Reference

### Starting Implementation

1. Check current task in [docs/internal/tasks/](../../docs/internal/tasks/)
2. Review relevant architecture docs
3. Reference `.claude/rules/` strictly
4. Use `/module` to scaffold new modules if needed
5. Implement with tests
6. Verify with `/deploy`

### Code Review

1. Run automated checks (`.claude/contexts/review.md`)
2. Verify against `.claude/rules/`
3. Check test coverage (`/test`)
4. Approve or request changes

### Debugging

1. Collect logs and error messages
2. Follow `.claude/contexts/debug.md`
3. Use debugging tools (pdb, docker logs, httpx)
4. Add test to prevent regression

## Integration with Development

### Worker Session

When implementing:
```bash
# 1. Read task
cat docs/internal/tasks/

# 2. Implement
# (Follow .claude/skills/ patterns)

# 3. Test
/test

# 4. Verify
/deploy
```

### QA Session

When reviewing:
```bash
# 1. Check compliance
# (Follow .claude/contexts/review.md)

# 2. Run tests
/test

# 3. Security audit
grep -r "sk-\|api_key.*=" backend/src/

# 4. Approve or reject
```

## Customization

This configuration is tailored for BSNexus. Modify as needed:

- Add new skills for emerging patterns
- Update rules if architecture changes
- Create new commands for frequent operations
- Add contexts for new work modes

## Philosophy

1. **Consistency**: Follow established patterns
2. **Quality**: Never skip tests or security checks
3. **Speed**: Use commands to avoid repetitive work
4. **Documentation**: Skills are living documentation

---

**For detailed implementation guide**, see:
- [docs/internal/](../../docs/internal/) - Architecture and task documentation
