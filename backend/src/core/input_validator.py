"""Input validation and sanitization for preventing injection attacks."""

import re
from typing import Any

from fastapi import HTTPException, status


# Patterns that indicate potential injection attacks
SQL_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|EXECUTE)\b\s)", re.IGNORECASE),
    re.compile(r"(--|;|/\*|\*/|xp_|sp_)", re.IGNORECASE),
    re.compile(r"(\b(OR|AND)\b\s+\d+\s*=\s*\d+)", re.IGNORECASE),
]

XSS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<script\b[^>]*>", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=\s*[\"'][^\"']*[\"']", re.IGNORECASE),
    re.compile(r"<\s*iframe\b", re.IGNORECASE),
    re.compile(r"<\s*object\b", re.IGNORECASE),
    re.compile(r"<\s*embed\b", re.IGNORECASE),
]

PATH_TRAVERSAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"%2e%2e[/\\]", re.IGNORECASE),
    re.compile(r"%252e%252e[/\\]", re.IGNORECASE),
]

COMMAND_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[;&|`$]"),
    re.compile(r"\$\("),
    re.compile(r"\$\{"),
]


class InputValidator:
    """Validates and sanitizes user inputs to prevent injection attacks."""

    @staticmethod
    def check_sql_injection(value: str) -> bool:
        """Check if a string contains potential SQL injection patterns."""
        for pattern in SQL_INJECTION_PATTERNS:
            if pattern.search(value):
                return True
        return False

    @staticmethod
    def check_xss(value: str) -> bool:
        """Check if a string contains potential XSS patterns."""
        for pattern in XSS_PATTERNS:
            if pattern.search(value):
                return True
        return False

    @staticmethod
    def check_path_traversal(value: str) -> bool:
        """Check if a string contains path traversal attempts."""
        for pattern in PATH_TRAVERSAL_PATTERNS:
            if pattern.search(value):
                return True
        return False

    @staticmethod
    def check_command_injection(value: str) -> bool:
        """Check if a string contains command injection attempts."""
        for pattern in COMMAND_INJECTION_PATTERNS:
            if pattern.search(value):
                return True
        return False

    @staticmethod
    def sanitize_html(value: str) -> str:
        """Remove HTML tags from a string."""
        return re.sub(r"<[^>]+>", "", value)

    @staticmethod
    def sanitize_string(value: str, max_length: int = 10000) -> str:
        """Basic string sanitization: trim whitespace and enforce length."""
        value = value.strip()
        if len(value) > max_length:
            value = value[:max_length]
        return value

    @classmethod
    def validate_user_input(cls, value: str, *, field_name: str = "input", allow_code: bool = False) -> str:
        """Validate user input for common injection patterns.

        Args:
            value: The string to validate.
            field_name: Name of the field (for error messages).
            allow_code: If True, skip XSS and command injection checks
                       (for fields like worker_prompt that contain code).
        """
        if cls.check_path_traversal(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid characters detected in {field_name}",
            )

        if not allow_code:
            if cls.check_xss(value):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid content detected in {field_name}",
                )

        return cls.sanitize_string(value)

    @classmethod
    def validate_path(cls, path: str, *, field_name: str = "path") -> str:
        """Validate a file path input."""
        if cls.check_path_traversal(path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid path in {field_name}",
            )
        return cls.sanitize_string(path, max_length=500)

    @classmethod
    def validate_dict_values(cls, data: dict[str, Any], *, allow_code_fields: set[str] | None = None) -> None:
        """Recursively validate all string values in a dictionary."""
        allow_code_fields = allow_code_fields or set()
        for key, value in data.items():
            if isinstance(value, str):
                allow_code = key in allow_code_fields
                cls.validate_user_input(value, field_name=key, allow_code=allow_code)
            elif isinstance(value, dict):
                cls.validate_dict_values(value, allow_code_fields=allow_code_fields)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        cls.validate_user_input(item, field_name=key, allow_code=key in allow_code_fields)
                    elif isinstance(item, dict):
                        cls.validate_dict_values(item, allow_code_fields=allow_code_fields)
