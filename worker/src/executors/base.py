from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionResult:
    success: bool
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    stdout: str = ""
    stderr: str = ""


@dataclass
class ReviewResult:
    passed: bool
    feedback: str = ""
    error_message: Optional[str] = None


class BaseExecutor(ABC):
    """Agent Coder executor interface"""

    @abstractmethod
    async def execute(self, prompt: str, context: dict) -> ExecutionResult:
        """Execute a coding task"""
        pass

    @abstractmethod
    async def review(self, prompt: str, context: dict) -> ReviewResult:
        """Execute a code review"""
        pass
