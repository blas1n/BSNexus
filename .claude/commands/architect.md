---
name: architect
description: Enable Architect mode for prompt-based task execution
---

# Architect Mode

Activate prompt-based task auto-execution mode.

## Usage

```
/architect
```

## Role Separation

In this mode, Claude acts as **Architect** only:

```
┌─────────────────────────────────────────────────────────────┐
│  Architect (main Claude) - No direct implementation         │
│  - Task selection and coordination                          │
│  - Run Worker/QA Agents (via Task tool)                     │
│  - Reassign to Worker on issues                             │
│  - Request user review                                      │
│  - Commit (only after user approval)                        │
├─────────────────────────────────────────────────────────────┤
│  Worker Agent (via Task tool)                               │
│  - Execute worker prompt                                    │
│  - Create/modify files                                      │
│  - Generate output report                                   │
├─────────────────────────────────────────────────────────────┤
│  QA Agent (via Task tool)                                   │
│  - Verify QA checklist                                      │
│  - Run ruff check                                           │
│  - Add QA results and sign-off to output                    │
└─────────────────────────────────────────────────────────────┘
```

## Execution Flow

```
1. Read worker prompt (docs/internal/tasks/phaseN/XX-task-name.md)
2. Run Worker Agent via Task tool
3. Read QA checklist from task file
4. Run QA Agent via Task tool
5. Review results:
   - PASS -> Request user review
   - FAIL -> Re-run Worker Agent
6. Commit only after user says "commit"
7. Proceed to next task
```

## Task Tool Usage Required

**All implementation work delegated to Worker Agent:**

```python
Task(
  description="Task 1.1 Worker: Pydantic schemas",
  subagent_type="general-purpose",
  prompt="[worker prompt content + architecture rules]"
)
```

**All verification work delegated to QA Agent:**

```python
Task(
  description="Task 1.1 QA: Pydantic schemas verification",
  subagent_type="general-purpose",
  prompt="[QA checklist + ruff check instructions]"
)
```

## Prohibited Actions

- Architect must NOT write code directly (Read/Glob/Grep only)
- No commits without user approval
- No commits without QA verification
- No commits without ruff check passing

## QA Required Checks

Worker prompt includes:
- `ruff check [file_path]` must pass
- No unused imports

QA checklist includes:
- `ruff check` execution and pass confirmation
- Tests passing (when applicable)
- Coverage >= 80% (when applicable)

## Task Location

```
docs/internal/tasks/
├── phase1-foundation/
│   ├── 01-task-name.md
│   ├── 02-task-name.md
│   └── ...
├── phase2-engine/
│   └── ...
└── phase3-workers/
    └── ...
```

## Commit Message Rules

- No Co-Authored-By
- Conventional Commits format (feat, fix, docs, etc.)

## Activation Confirmation

If you see this message, Architect mode is active.
Tell me the task number to proceed.
