"""Centralised response unwrapping for VeSync API patterns."""

from __future__ import annotations

from typing import Any


def unwrap_response(body: dict[str, Any]) -> tuple[Any, Any]:
    """Unwrap a VeSync API response into (result, code).

    VeSync pattern: ``{"code": 0, "msg": "...", "result": {...}}``

    Args:
        body (dict[str, Any]): Parsed JSON response body.

    Returns:
        tuple[Any, Any]: A ``(result, code)`` pair where *code* is
            the VeSync status code (0 = success).
    """
    return body.get("result"), body.get("code")
