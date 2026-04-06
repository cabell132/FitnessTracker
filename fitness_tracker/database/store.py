"""Store: factory and entry-point for all database operations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from fitness_tracker.database.models.base import BaseModel
from fitness_tracker.database.uow import UnitOfWork

T = TypeVar("T", bound=BaseModel)


class Store:
    """Factory that owns a SQLAlchemy Engine and vends UnitOfWork instances.

    Attributes:
        engine: The SQLAlchemy engine backing all database operations.
    """

    def __init__(self, engine: Engine) -> None:
        """Create a store bound to the given engine.

        Args:
            engine (Engine): SQLAlchemy engine for the fitness tracker database.
        """
        self._engine = engine

    # -- lifecycle -----------------------------------------------------------

    def init_db(self) -> None:
        """Create all tables defined in the ORM metadata."""
        BaseModel.metadata.create_all(self._engine)

    def drop_tables(self) -> None:
        """Drop all tables defined in the ORM metadata."""
        BaseModel.metadata.drop_all(self._engine)

    # -- unit of work --------------------------------------------------------

    @contextmanager
    def unit_of_work(self) -> Iterator[UnitOfWork]:
        """Yield a UnitOfWork that commits on clean exit and rolls back on error.

        Yields:
            UnitOfWork: Transaction-scoped context for all database operations.

        Raises:
            Exception: Re-raised after rollback if the worker block fails.
        """
        session = Session(self._engine)
        uow = UnitOfWork(session)
        try:
            yield uow
            uow.commit()
        except Exception:
            uow.rollback()
            raise
        finally:
            session.close()

    # -- read-only convenience -----------------------------------------------

    def query_one(self, model: type[T], **filters: Any) -> T | None:
        """Return one row matching the filters in an auto-closing session.

        Args:
            model (type[T]): ORM model class to query.
            **filters (Any): Equality filters passed to ``filter_by``.

        Returns:
            T | None: Matching row, or ``None``.
        """
        with Session(self._engine) as session:
            q = session.query(model)
            if filters:
                q = q.filter_by(**filters)
            return q.first()

    def query_all(self, model: type[T], **filters: Any) -> list[T]:
        """Return all rows matching the filters in an auto-closing session.

        Args:
            model (type[T]): ORM model class to query.
            **filters (Any): Equality filters passed to ``filter_by``.

        Returns:
            list[T]: All matching ORM instances (possibly empty).
        """
        with Session(self._engine) as session:
            q = session.query(model)
            if filters:
                q = q.filter_by(**filters)
            return q.all()
