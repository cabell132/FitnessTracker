"""Store: factory and entry-point for all database operations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from fitness_tracker.apis import HevyAppClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from fitness_tracker.database.models.base import BaseModel
from fitness_tracker.database.tx import Tx

T = TypeVar("T", bound=BaseModel)


class Store:
    """Factory that owns a SQLAlchemy Engine and vends transaction containers.

    Attributes:
        engine: The SQLAlchemy engine backing all database operations.
    """

    def __init__(self, engine: Engine, hevy_client: HevyAppClient | None = None) -> None:
        """Create a store bound to the given engine.

        Args:
            engine (Engine): SQLAlchemy engine for the fitness tracker database.
            hevy_client (HevyAppClient | None): Optional Hevy API client used by
                the Hevy repository to backfill missing exercise templates.
        """
        self._engine = engine
        self._hevy_client = hevy_client

    # -- lifecycle -----------------------------------------------------------

    def init_db(self) -> None:
        """Create all tables defined in the ORM metadata."""
        BaseModel.metadata.create_all(self._engine)

    def drop_tables(self) -> None:
        """Drop all tables defined in the ORM metadata."""
        BaseModel.metadata.drop_all(self._engine)

    # -- unit of work --------------------------------------------------------

    @contextmanager
    def unit_of_work(self) -> Iterator[Tx]:
        """Yield a Tx that commits on clean exit and rolls back on error.

        Yields:
            Tx: Transaction-scoped repository container.

        Raises:
            Exception: Re-raised after rollback if the worker block fails.
        """
        session = Session(self._engine, expire_on_commit=False)
        fetch_template = (
            self._hevy_client.exercises.get_template if self._hevy_client is not None else None
        )
        tx = Tx(session, fetch_template=fetch_template)
        try:
            yield tx
            session.commit()
        except Exception:
            session.rollback()
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
