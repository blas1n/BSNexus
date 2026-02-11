from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator, Optional

import litellm
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def _extract_json(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = raw.strip()
    if not text:
        raise json.JSONDecodeError("Empty response from LLM", text, 0)
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code block
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return json.loads(match.group(1))
    raise json.JSONDecodeError("No valid JSON found in LLM response", text, 0)


class LLMError(Exception):
    """Custom exception wrapping LiteLLM errors."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        self.original_error = original_error
        super().__init__(message)


class LLMConfig(BaseModel):
    """LLM connection config (passed at runtime)."""

    api_key: str
    model: str = "anthropic/claude-sonnet-4-20250514"
    base_url: Optional[str] = None

    def __repr__(self) -> str:
        masked_key = f"***{self.api_key[-4:]}" if len(self.api_key) >= 4 else "***"
        return f"LLMConfig(api_key='{masked_key}', model='{self.model}', base_url={self.base_url!r})"


class LLMClient:
    """LiteLLM-based LLM client (provider-agnostic)."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Non-streaming response."""
        try:
            response = await litellm.acompletion(
                model=self.config.model,
                messages=messages,
                api_key=self.config.api_key,
                api_base=self.config.base_url,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            raise LLMError(f"LLM chat failed: {e}", original_error=e) from e

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Streaming response."""
        try:
            response = await litellm.acompletion(
                model=self.config.model,
                messages=messages,
                api_key=self.config.api_key,
                api_base=self.config.base_url,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"LLM stream_chat failed: {e}", original_error=e) from e

    async def structured_output(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any],
        temperature: float = 0.3,
        timeout: float = 90.0,
    ) -> dict[str, Any]:
        """JSON structured output (for finalize, task decomposition, etc.)."""
        try:
            logger.info("structured_output: model=%s, messages=%d", self.config.model, len(messages))
            response = await litellm.acompletion(
                model=self.config.model,
                messages=messages,
                api_key=self.config.api_key,
                api_base=self.config.base_url,
                temperature=temperature,
                response_format=response_format,
                timeout=timeout,
            )
            raw = response.choices[0].message.content or ""
            return _extract_json(raw)
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse structured output as JSON: {e}", original_error=e) from e
        except LLMError:
            raise
        except Exception as e:
            logger.exception("structured_output failed: %s", e)
            raise LLMError(f"LLM structured_output failed: {e}", original_error=e) from e


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Create client from LLMConfig."""
    return LLMClient(config)


def create_llm_client_from_project(project: Any, role: str = "architect") -> LLMClient:
    """Create client from Project model's llm_config.

    Args:
        project: Project SQLAlchemy model.
        role: "architect" or "pm".

    Returns:
        LLMClient configured for the given role.

    Raises:
        ValueError: if llm_config doesn't have config for the given role.
    """
    llm_config: dict[str, Any] = project.llm_config or {}
    role_config: dict[str, Any] | None = llm_config.get(role)

    if not role_config or not role_config.get("api_key"):
        raise ValueError(f"Project {project.id} has no {role} LLM configuration")

    config = LLMConfig(
        api_key=role_config["api_key"],
        model=role_config.get("model", "anthropic/claude-sonnet-4-20250514"),
        base_url=role_config.get("base_url"),
    )
    return LLMClient(config)
