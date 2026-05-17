"""Shared base types for API clients."""

from typing import Any

from pydantic import BaseModel


def parse_response[T: BaseModel](data: dict[str, Any] | None, model: type[T]) -> T | None:
    """Parse a session response dict into a Pydantic model, or return None.

    Args:
        data (dict[str, Any] | None): Raw response from session.make_request().
        model (type[T]): Pydantic model class to instantiate.

    Returns:
        T | None: Parsed model when data is truthy; otherwise ``None``.
    """
    if data:
        return model(**data)
    return None


class BaseClient:
    """Marker base class for thin API client facades."""
