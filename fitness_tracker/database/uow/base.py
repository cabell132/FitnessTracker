"""Generic CRUD operations shared by all UnitOfWork domain mixins."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy.orm import Query, Session
from sqlalchemy.sql import func, text

from fitness_tracker.database.models.base import BaseModel

T = TypeVar("T", bound=BaseModel)

_SQL_DIR = Path("fitness_tracker/database/SQL")


class CrudMixin:
    """Generic CRUD operations backed by a SQLAlchemy session.

    Subclasses (or the final UnitOfWork) must set ``_session`` before use.
    """

    _session: Session

    def query(self, *entities: Any, **kwargs: Any) -> Query[Any]:
        """Build a SQLAlchemy query, optionally filtered by equality kwargs.

        Args:
            *entities (Any): Entities or columns to query.
            **kwargs (Any): Equality filters passed to ``filter_by``.

        Returns:
            Query[Any]: SQLAlchemy query object.
        """
        q = self._session.query(*entities)
        if kwargs:
            q = q.filter_by(**kwargs)
        return q

    def get(self, model: type[T], **kwargs: Any) -> T | None:
        """Return a single row matching the given equality filters.

        Args:
            model (type[T]): ORM model class to query.
            **kwargs (Any): Column name to value filters.

        Returns:
            T | None: Matching ORM instance, or ``None``.
        """
        return self.query(model, **kwargs).first()

    def get_all(self, model: type[T], **kwargs: Any) -> list[T]:
        """Return all rows matching the given equality filters.

        Args:
            model (type[T]): ORM model class to query.
            **kwargs (Any): Column name to value filters.

        Returns:
            list[T]: All matching ORM instances.
        """
        return self.query(model, **kwargs).all()

    def add(self, obj: BaseModel) -> None:
        """Stage a new instance for insertion on the next flush/commit.

        Args:
            obj (BaseModel): ORM instance to persist.
        """
        self._session.add(obj)

    def merge(self, obj: BaseModel) -> None:
        """Merge a detached instance into the current session.

        Args:
            obj (BaseModel): ORM instance to merge.
        """
        self._session.merge(obj)

    def insert_ignore(self, obj: BaseModel) -> None:
        """Insert a row via ``INSERT OR IGNORE`` if not already present.

        Args:
            obj (BaseModel): Instance whose model builds the statement.
        """
        if getattr(obj, "date_created", None) is None:
            obj.date_created = func.now()
        if getattr(obj, "date_updated", None) is None:
            obj.date_updated = func.now()
        stmnt = obj.insert_ignore()
        self._session.execute(stmnt)

    def delete(self, obj: BaseModel) -> None:
        """Mark a persisted instance for deletion.

        Args:
            obj (BaseModel): ORM instance to remove.
        """
        self._session.delete(obj)

    def delete_all(self, model: type[T], **kwargs: Any) -> None:
        """Delete every row matching the given equality filters.

        Args:
            model (type[T]): ORM model class to query.
            **kwargs (Any): Filters passed to :meth:`get_all`.
        """
        for rec in self.get_all(model, **kwargs):
            self.delete(rec)

    def flush(self) -> None:
        """Flush pending changes to the database without committing."""
        self._session.flush()

    def commit(self) -> None:
        """Commit the current transaction."""
        self._session.commit()

    def rollback(self) -> None:
        """Roll back the current transaction."""
        self._session.rollback()

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        """Execute an arbitrary SQL statement on the session.

        Args:
            statement (Any): SQL text or compiled expression.
            params (dict[str, Any] | None): Bind parameters.

        Returns:
            Any: SQLAlchemy result proxy.
        """
        return self._session.execute(statement, params or {})

    def execute_sql_file(self, relative_path: str, params: dict[str, Any] | None = None) -> Any:
        """Load and execute a SQL template file relative to the SQL directory.

        Args:
            relative_path (str): Path under ``fitness_tracker/database/SQL/``.
            params (dict[str, Any] | None): Bind parameters.

        Returns:
            Any: SQLAlchemy result proxy.
        """
        sql = (_SQL_DIR / relative_path).read_text(encoding="utf-8")
        return self._session.execute(text(sql), params or {})
