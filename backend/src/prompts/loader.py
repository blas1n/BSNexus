from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PROMPTS_DIR = Path(__file__).parent
_cache: dict[str, dict[str, Any]] = {}


def load_prompts(name: str) -> dict[str, Any]:
    """Load a YAML prompt file by name (without extension). Results are cached."""
    if name in _cache:
        return _cache[name]

    path = _PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    _cache[name] = data
    return data


def get_prompt(name: str, key: str) -> str:
    """Get a specific prompt string from a YAML file.

    Args:
        name: The prompt file name (e.g., "architect").
        key: The key within the YAML file (e.g., "system", "finalize").

    Returns:
        The prompt string with leading/trailing whitespace stripped.
    """
    prompts = load_prompts(name)
    if key not in prompts:
        raise KeyError(f"Prompt key '{key}' not found in '{name}.yaml'")
    return str(prompts[key]).strip()
