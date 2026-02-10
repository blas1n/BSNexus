import time
from unittest.mock import patch

import pytest

from backend.src.core.prompt_security import PromptSigner

SECRET_KEY = "test-secret-key-for-testing"


@pytest.fixture
def signer() -> PromptSigner:
    return PromptSigner(SECRET_KEY)


def test_sign_returns_required_fields(signer: PromptSigner) -> None:
    """sign() returns dict with prompt, signature, nonce, timestamp."""
    result = signer.sign("Hello, world!")
    assert "prompt" in result
    assert "signature" in result
    assert "nonce" in result
    assert "timestamp" in result


def test_sign_preserves_prompt(signer: PromptSigner) -> None:
    """The returned prompt matches the input."""
    prompt_text = "Build a REST API for task management"
    result = signer.sign(prompt_text)
    assert result["prompt"] == prompt_text


def test_verify_valid_signature(signer: PromptSigner) -> None:
    """A signed prompt passes verification."""
    signed = signer.sign("Test prompt")
    assert signer.verify(signed) is True


def test_verify_tampered_prompt(signer: PromptSigner) -> None:
    """Changing prompt text after signing fails verification."""
    signed = signer.sign("Original prompt")
    signed["prompt"] = "Tampered prompt"
    assert signer.verify(signed) is False


def test_verify_tampered_signature(signer: PromptSigner) -> None:
    """Changing signature fails verification."""
    signed = signer.sign("Test prompt")
    signed["signature"] = "tampered" + signed["signature"][8:]
    assert signer.verify(signed) is False


def test_verify_expired_timestamp(signer: PromptSigner) -> None:
    """Old timestamp (> max_age) fails verification."""
    signed = signer.sign("Test prompt")
    # Patch time.time to return a value far in the future so the prompt appears expired
    with patch("backend.src.core.prompt_security.time.time", return_value=time.time() + 7200):
        assert signer.verify(signed) is False


def test_verify_future_timestamp(signer: PromptSigner) -> None:
    """Negative age (timestamp in far future) fails verification."""
    signed = signer.sign("Test prompt")
    signed["timestamp"] = int(time.time()) + 9999
    assert signer.verify(signed) is False


def test_verify_missing_fields(signer: PromptSigner) -> None:
    """Missing required fields fails verification."""
    # Missing signature
    assert signer.verify({"prompt": "test", "nonce": "abc", "timestamp": 123}) is False
    # Missing prompt
    assert signer.verify({"signature": "test", "nonce": "abc", "timestamp": 123}) is False
    # Missing nonce
    assert signer.verify({"prompt": "test", "signature": "abc", "timestamp": 123}) is False
    # Missing timestamp
    assert signer.verify({"prompt": "test", "signature": "abc", "nonce": "123"}) is False
    # Empty dict
    assert signer.verify({}) is False


def test_extract_prompt_valid(signer: PromptSigner) -> None:
    """extract_prompt returns the prompt for valid signed data."""
    signed = signer.sign("Extract me")
    result = signer.extract_prompt(signed)
    assert result == "Extract me"


def test_extract_prompt_invalid(signer: PromptSigner) -> None:
    """extract_prompt returns None for tampered data."""
    signed = signer.sign("Original")
    signed["prompt"] = "Tampered"
    result = signer.extract_prompt(signed)
    assert result is None


def test_nonce_uniqueness(signer: PromptSigner) -> None:
    """Two consecutive sign() calls produce different nonces."""
    signed1 = signer.sign("Same prompt")
    signed2 = signer.sign("Same prompt")
    assert signed1["nonce"] != signed2["nonce"]


def test_hmac_compare_digest_used(signer: PromptSigner) -> None:
    """Verify uses hmac.compare_digest (not ==) — tested by ensuring correct behavior."""
    # We verify this works correctly with valid and invalid signatures
    # The implementation uses hmac.compare_digest which is constant-time
    signed = signer.sign("Test prompt")
    assert signer.verify(signed) is True

    # Slightly different signature should fail
    signed_copy = dict(signed)
    original_sig = signed_copy["signature"]
    # Flip last character
    last_char = original_sig[-1]
    flipped = "0" if last_char != "0" else "1"
    signed_copy["signature"] = original_sig[:-1] + flipped
    assert signer.verify(signed_copy) is False


def test_different_keys_fail() -> None:
    """Signing with one key and verifying with another fails."""
    signer1 = PromptSigner("key-one")
    signer2 = PromptSigner("key-two")

    signed = signer1.sign("Cross-key test")
    assert signer2.verify(signed) is False
