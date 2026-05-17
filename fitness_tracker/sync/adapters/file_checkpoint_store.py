"""File-backed and in-memory :class:`CheckpointStore` implementations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

HEVY_CHECKPOINT_KEY = "hevy"
_LEGACY_HEVY_FILENAME = "hevy_last_sync.txt"


@dataclass
class FileCheckpointStore:
    """Production store: one JSON file holding all checkpoints.

    Missing files yield the supplied default instead of raising. Replaces
    ``hevy_last_sync.txt`` when the JSON path is absent by reading the legacy
    file for the ``hevy`` key once.
    """

    path: Path = field(default_factory=lambda: Path("sync_checkpoints.json"))

    def read(self, key: str, default: datetime) -> datetime:
        """Load ``key`` from disk, migrate legacy Hevy file when applicable.

        Args:
            key (str): Checkpoint name.
            default (datetime): Fallback when missing or invalid.

        Returns:
            datetime: Parsed checkpoint or ``default``.
        """
        if self.path.exists():
            raw_text = self.path.read_text(encoding="utf-8").strip()
            if raw_text:
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    return default
                if isinstance(data, dict):
                    raw = data.get(key)
                    if isinstance(raw, str) and raw:
                        return datetime.fromisoformat(raw)
            return default

        legacy_path = self.path.parent / _LEGACY_HEVY_FILENAME
        if key == HEVY_CHECKPOINT_KEY and legacy_path.exists():
            try:
                return datetime.fromisoformat(legacy_path.read_text(encoding="utf-8").strip())
            except ValueError:
                pass
        return default

    def write(self, key: str, value: datetime) -> None:
        """Merge ``key`` into the JSON file and write atomically.

        Args:
            key (str): Checkpoint name.
            value (datetime): Timestamp to persist.
        """
        data: dict[str, str] = {}
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8").strip()
            if raw:
                try:
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        data = {k: str(v) for k, v in loaded.items() if isinstance(k, str)}
                except json.JSONDecodeError:
                    data = {}
        data[key] = value.isoformat()
        self.path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


@dataclass
class InMemoryCheckpointStore:
    """Test double that keeps checkpoints in a dict."""

    _data: dict[str, datetime] = field(default_factory=dict)

    def read(self, key: str, default: datetime) -> datetime:
        """Return the in-memory value or ``default``.

        Args:
            key (str): Checkpoint name.
            default (datetime): Fallback when absent.

        Returns:
            datetime: Stored value or ``default``.
        """
        return self._data.get(key, default)

    def write(self, key: str, value: datetime) -> None:
        """Store ``value`` under ``key``.

        Args:
            key (str): Checkpoint name.
            value (datetime): Timestamp.
        """
        self._data[key] = value
