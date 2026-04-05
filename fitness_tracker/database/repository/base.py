"""Generic SQLAlchemy repository base for ORM models."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from fitness_tracker.database.models.base import BaseModel
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql import func

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):  # noqa: UP046
    """Base repository class to be inherited by all other repositories."""

    def __init__(
        self,
        session: Session,
        model_class: type[T],
    ) -> None:
        """Initialize the repository class.

        Args:
            session (Session): The session to use for the repository.
            model_class (type[T]): The model class to use for the repository.
        """
        self.model_class = model_class
        self.session = session

    def query(self, *entities: Any, **kwargs: Any) -> Query[Any]:
        """Build a SQLAlchemy query for the given entities.

        Args:
            *entities (Any): Entities or columns to query.
            **kwargs (Any): Equality filters passed to ``filter_by``.

        Returns:
            Query[Any]: SQLAlchemy query object.
        """
        q = self.session.query(*entities)
        if kwargs:
            q = q.filter_by(**kwargs)
        return q

    def get(self, **kwargs: Any) -> T | None:
        """Return a single model row matching the given equality filters.

        Args:
            **kwargs (Any): Column name to value filters passed to ``filter_by``.

        Returns:
            T | None: Matching ORM instance, or None if absent.
        """
        return self.query(self.model_class, **kwargs).first()

    def get_all(self, **kwargs: Any) -> list[T]:
        """Return all model rows matching the given equality filters.

        Args:
            **kwargs (Any): Column name to value filters passed to ``filter_by``.

        Returns:
            list[T]: All matching ORM instances.
        """
        return self.query(self.model_class, **kwargs).all()

    def exists(self, **kwargs: Any) -> bool:
        """Return whether any row matches the given equality filters.

        Args:
            **kwargs (Any): Column name to single value, same as :meth:`get`.

        Returns:
            bool: True if :meth:`get` would return a row.
        """
        return self.get(**kwargs) is not None

    def exists_list(self, **kwargs: Any) -> Sequence[bool]:
        """Return existence flags for each value in per-column lists.

        Args:
            **kwargs (Any): Mapping of column name to iterable of values to test
                (each value is checked with :meth:`exists`).

        Returns:
            Sequence[bool]: Parallel booleans for each (column, value) pair expanded
                in key order, then value order.
        """
        return [self.exists(**{key: value}) for key, values in kwargs.items() for value in values]

    def add(self, obj: T) -> None:
        """Add a record to the database.

        Args:
            obj (T): ORM instance to persist on flush/commit.

        Returns:
            None: Nothing is returned.
        """
        self.session.add(obj)

    def merge(self, obj: T) -> None:
        """Merge a detached instance into the current session.

        Args:
            obj (T): ORM instance to merge.

        Returns:
            None: Nothing is returned.
        """
        self.session.merge(obj)

    def insert_ignore(self, obj: T) -> None:
        """Add a row via model-specific insert-ignore SQL if not already present.

        Args:
            obj (T): Instance whose :meth:`insert_ignore` builds the statement.

        Returns:
            None: Nothing is returned; execution is staged on the session.
        """
        if getattr(obj, "date_created", None) is None:
            obj.date_created = func.now()
        if getattr(obj, "date_updated", None) is None:
            obj.date_updated = func.now()
        stmnt = obj.insert_ignore()
        self.session.execute(stmnt)

    def delete(self, obj: T) -> None:
        """Delete a persisted instance from the current session.

        Args:
            obj (T): ORM instance to remove.

        Returns:
            None: Nothing is returned.
        """
        self.session.delete(obj)

    def delete_all(self, **kwargs: Any) -> None:
        """Delete every row matching the given equality filters.

        Args:
            **kwargs (Any): Filters passed to :meth:`get_all`.

        Returns:
            None: Nothing is returned.
        """
        recs = self.get_all(**kwargs)
        for rec in recs:
            self.delete(rec)
