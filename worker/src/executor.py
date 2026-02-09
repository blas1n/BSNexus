from worker.src.executors.base import BaseExecutor
from worker.src.executors.claude_code import ClaudeCodeExecutor

EXECUTORS: dict[str, type[BaseExecutor]] = {
    "claude-code": ClaudeCodeExecutor,
}


def create_executor(executor_type: str, **kwargs: str) -> BaseExecutor:
    """Executor factory"""
    if executor_type not in EXECUTORS:
        raise ValueError(f"Unknown executor: {executor_type}. Available: {list(EXECUTORS.keys())}")
    return EXECUTORS[executor_type](**kwargs)
