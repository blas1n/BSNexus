import pytest

from worker.prompts.loader import clear_cache, get_prompt, load_prompts


class TestLoadPrompts:
    def setup_method(self) -> None:
        clear_cache()

    def test_load_prompts_review(self) -> None:
        """load_prompts('review') should load review.yaml successfully."""
        data = load_prompts("review")
        assert "code_review" in data

    def test_load_prompts_caches(self) -> None:
        """Subsequent calls should return cached data."""
        data1 = load_prompts("review")
        data2 = load_prompts("review")
        assert data1 is data2

    def test_load_prompts_missing_file(self) -> None:
        """load_prompts() should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError, match="Prompt file not found"):
            load_prompts("nonexistent")


class TestGetPrompt:
    def setup_method(self) -> None:
        clear_cache()

    def test_get_prompt_returns_string(self) -> None:
        result = get_prompt("review", "code_review")
        assert isinstance(result, str)
        assert "QA reviewer" in result

    def test_get_prompt_missing_key(self) -> None:
        with pytest.raises(KeyError, match="Prompt key 'bogus' not found"):
            get_prompt("review", "bogus")
