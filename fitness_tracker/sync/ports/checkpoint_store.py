"""Checkpoint persistence port for incremental sync boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class CheckpointStore(Protocol):
    """Read and write named datetime checkpoints.

    Production uses ``FileCheckpointStore``; tests use ``InMemoryCheckpointStore``
    (see ``fitness_tracker.sync.adapters.file_checkpoint_store``).
    """

    def read(self, key: str, default: datetime) -> datetime:
        """Return the checkpoint for ``key``, or ``default`` if absent.

        Args:
            key (str): Logical checkpoint name.
            default (datetime): Value when no checkpoint exists.

        Returns:
            datetime: Stored checkpoint or ``default``.
        """
        ...

    def write(self, key: str, value: datetime) -> None:
        """Persist a checkpoint timestamp for ``key``.

        Args:
            key (str): Logical checkpoint name.
            value (datetime): Timestamp to store.

        Returns:
            None
        """
        ...
