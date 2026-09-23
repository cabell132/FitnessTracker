"""Token caching for VeSync sessions."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol


class CacheHandler(Protocol):
    """Storage contract for VeSync session tokens."""

    def get_token(self) -> dict[str, Any] | None:
        """Return the cached token, if present.

        Returns:
            dict[str, Any] | None: Cached token or None.
        """

    def save_token(self, token_data: dict[str, Any]) -> None:
        """Store the token data.

        Args:
            token_data (dict[str, Any]): VeSync session token data.
        """


class MemoryCacheHandler:
    """Store a token in process memory."""

    def __init__(self) -> None:
        """Start with an empty token store."""
        self._token: dict[str, Any] | None = None

    def get_token(self) -> dict[str, Any] | None:
        """Return the cached token, if present.

        Returns:
            dict[str, Any] | None: Cached token or None.
        """
        return self._token

    def save_token(self, token_data: dict[str, Any]) -> None:
        """Store the token data.

        Args:
            token_data (dict[str, Any]): VeSync session token data.
        """
        self._token = token_data


class FileCacheHandler:
    """Store a token in a private JSON file."""

    def __init__(self, cache_path: Path) -> None:
        """Set the token file path.

        Args:
            cache_path (Path): Path to the private JSON token file.
        """
        self._cache_path = cache_path

    def get_token(self) -> dict[str, Any] | None:
        """Read a token from disk, if one exists.

        Returns:
            dict[str, Any] | None: Cached token or None.
        """
        try:
            data = json.loads(self._cache_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def save_token(self, token_data: dict[str, Any]) -> None:
        """Write a token atomically with owner-only permissions.

        Args:
            token_data (dict[str, Any]): VeSync session token data.
        """
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(
            dir=self._cache_path.parent, prefix=f".{self._cache_path.name}."
        )
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(token_data, stream)
            Path(name).replace(self._cache_path)
        finally:
            Path(name).unlink(missing_ok=True)
