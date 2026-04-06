"""Port for the Store -- a factory for transactional units of work."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol, runtime_checkable

from fitness_tracker.database.uow import UnitOfWork


@runtime_checkable
class StoreLike(Protocol):
    """Factory for transactional units of work.

    The concrete ``Store`` already satisfies this protocol when backed by
    an in-memory SQLite engine for tests.  This protocol exists so that
    syncer type hints do not import the concrete class.
    """

    @contextmanager
    def unit_of_work(self) -> Iterator[UnitOfWork]:
        """Yield a UnitOfWork that commits on clean exit and rolls back on error.

        Returns:
            Iterator[UnitOfWork]: Transaction-scoped context for all database operations.
        """
        ...
