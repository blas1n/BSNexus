from __future__ import annotations

import pytest

from backend.src.prompts.loader import get_prompt, load_prompts, _cache


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the prompt cache before each test."""
    _cache.clear()
    yield
    _cache.clear()


class TestLoadPrompts:
    """Tests for loading YAML prompt files."""

    def test_load_architect_prompts(self):
        prompts = load_prompts("architect")
        assert "system" in prompts
        assert "finalize" in prompts
        assert "add_task" in prompts

    def test_load_prompts_cached(self):
        prompts1 = load_prompts("architect")
        prompts2 = load_prompts("architect")
        assert prompts1 is prompts2

    def test_load_nonexistent_file(self):
        with pytest.raises(FileNotFoundError, match="Prompt file not found"):
            load_prompts("nonexistent")


class TestGetPrompt:
    """Tests for getting individual prompt strings."""

    def test_get_system_prompt(self):
        prompt = get_prompt("architect", "system")
        assert "AI Architect" in prompt
        assert "BSNexus" in prompt
        assert isinstance(prompt, str)

    def test_get_finalize_prompt(self):
        prompt = get_prompt("architect", "finalize")
        assert "project_name" in prompt
        assert "phases" in prompt
        assert "worker_prompt" in prompt

    def test_get_add_task_prompt(self):
        prompt = get_prompt("architect", "add_task")
        assert "{context}" in prompt
        assert "{phase_name}" in prompt
        assert "{request_text}" in prompt

    def test_get_prompt_strips_whitespace(self):
        prompt = get_prompt("architect", "system")
        assert not prompt.startswith("\n")
        assert not prompt.endswith("\n")

    def test_get_nonexistent_key(self):
        with pytest.raises(KeyError, match="Prompt key 'nonexistent' not found"):
            get_prompt("architect", "nonexistent")

    def test_get_prompt_from_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            get_prompt("nonexistent", "system")

    def test_add_task_prompt_format(self):
        """Verify the add_task prompt can be formatted with expected variables."""
        template = get_prompt("architect", "add_task")
        result = template.format(
            context="Project: Test\nDescription: Test project",
            phase_name="Phase 1",
            request_text="Add authentication",
        )
        assert "Project: Test" in result
        assert "Phase 1" in result
        assert "Add authentication" in result
        # JSON example braces should render as single braces after format
        assert '"title": "..."' in result
