"""SQLAlchemy declarative base and shared ORM helpers."""

from collections.abc import Generator, Iterator
from typing import Any, ClassVar, Self

from sqlalchemy import inspect
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class BaseModel(Base):
    """Base SQLAlchemy model with dict-like helpers for inserts and introspection."""

    __abstract__ = True
    __keys__: ClassVar[list[str]] = []

    @classmethod
    def create(cls, **kwargs: Any) -> Self:
        """Create a new in-memory instance of this mapped class.

        Args:
            **kwargs (Any): Column and relationship values accepted by the mapper.

        Returns:
            Self: A new instance (not persisted until added to a session).
        """
        return cls(**kwargs)

    @classmethod
    def columns(cls) -> list[str]:
        """Return mapped column names (excluding relationships).

        Returns:
            list[str]: Column names on the mapped table.
        """
        return [column.name for column in inspect(cls).c]

    @classmethod
    def relationships(cls) -> list[str]:
        """Return relationship attribute names defined on the mapper.

        Returns:
            list[str]: Relationship keys.
        """
        return [column.key for column in inspect(cls).relationships]

    @classmethod
    def __get_keys__(cls) -> list[str]:
        """Return non-callable public attributes defined on the class body.

        Returns:
            list[str]: Attribute names used by :meth:`keys`.
        """
        items = cls.__dict__.items()
        return [k for k, v in items if not callable(v) and not k.startswith("_")]

    @classmethod
    def keys(cls) -> list[str]:
        """Return cached column and relationship keys for iteration helpers.

        Returns:
            list[str]: Cached key list built from :meth:`__get_keys__`.
        """
        if not cls.__keys__:
            cls.__keys__ = cls.__get_keys__()
        return cls.__keys__

    def __iter__(self) -> Iterator[str]:
        """Return an iterator over column and relationship names from :meth:`keys`.

        Returns:
            Iterator[str]: Iterator yielding each key in order.
        """
        return iter(self.keys())

    def __len__(self) -> int:
        """Return the number of keys exposed by :meth:`keys`.

        Returns:
            int: Count of keys.
        """
        return sum(1 for _ in self.__iter__())

    def __getitem__(self, item: str) -> Any:
        """Return an attribute value by name (column or relationship).

        Args:
            item (str): Attribute name.

        Returns:
            Any: The underlying attribute value.
        """
        return self.__getattribute__(item)

    def values(self) -> list[Any]:
        """Return values for every key from :meth:`keys`.

        Returns:
            list[Any]: Values in key order.
        """
        return [self.__getitem__(key) for key in self.keys()]

    def items(self) -> Generator[tuple[str, Any], None, None]:
        """Yield ``(key, value)`` pairs for mapped attributes.

        Yields:
            tuple[str, Any]: Name and value for each key.
        """
        for key in self.__iter__():
            yield key, self.__getitem__(key)

    def to_dict(self) -> dict[str, Any]:
        """Build a dict of column names to values.

        Returns:
            dict[str, Any]: Mapping for columns returned by :meth:`columns`.
        """
        return {key: self.__getitem__(key) for key in self.columns()}

    def insert_values(self) -> dict[str, Any]:
        """Return values for an insert statement.

        Returns:
            dict[str, Any]: Column-value mapping for this row.
        """
        return self.to_dict()

    def pformat(self, indent: str = "   ") -> str:
        """Pretty-print column values aligned in columns.

        Args:
            indent (str, optional): Leading spaces per line. Defaults to three spaces.

        Returns:
            str: Multi-line table string including the table name.
        """
        lines: list[str] = [f"{self.__tablename__}"]
        columns = self.columns()
        w = max(len(col) for col in columns)
        for col in columns:
            lines.append(f"{indent}{col:<{w}} {self.__getitem__(col)}")  # noqa: PERF401
        return "\n".join(lines)
