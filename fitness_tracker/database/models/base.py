from typing import Any

from sqlalchemy.inspection import inspect # type: ignore
from sqlalchemy.orm import declarative_base  # type: ignore

Base = declarative_base()


class BaseModel(Base):
    """Base class for all SQL models."""

    """Base class used to initialize the declarative base for all tables."""

    __abstract__ = True
    __keys__: list[str] = []

    @classmethod
    def create(cls, **kwargs: Any):
        """Creates a new instance of the table entry."""
        return cls(**kwargs)

    @classmethod
    def columns(cls) -> list[str]:
        """Returns a list of all column names without the relationships."""
        return [column.name for column in inspect(cls).c]  # type: ignore

    @classmethod
    def relationships(cls): # type: ignore
        """Returns a list of all relationship names."""
        return [column.key for column in inspect(cls).relationships]  # type: ignore

    @classmethod
    def __get_keys__(cls):
        """Get all attributes of the table."""
        items = cls.__dict__.items()
        keys = [k for k, v in items if not callable(v) and not k.startswith("_")]
        return keys

    @classmethod
    def keys(cls):
        """Returns a list of all column names including the relationships."""
        if not cls.__keys__:  # Cache the keys
            cls.__keys__ = cls.__get_keys__()
        return cls.__keys__

    def __iter__(self):
        """Iterates over all columns and relationship names."""
        return iter(self.keys())

    def __len__(self):
        """Returns the number of columns and relationships."""
        return sum(1 for _ in self.__iter__())

    def __getitem__(self, item: str):
        """Returns the value of the given column or Relationship."""
        return self.__getattribute__(item)

    def values(self):
        """Returns a list of all column values including the relationships."""
        return [self.__getitem__(key) for key in self.keys()]

    def items(self):
        """Returns a generator of all column names and values."""
        for key in self.__iter__():
            yield key, self.__getitem__(key)

    def to_dict(self):
        """Returns a dictionary of all column names and values."""
        return {key: self.__getitem__(key) for key in self.columns()}

    def insert_ignore(self):
        """Returns an insert statement with the IGNORE keyword."""
        return self.__table__.insert().prefix_with("OR IGNORE").values(**self.to_dict())

    def pformat(self, indent: str = "   "):
        """Pretty formats the table entry.

        Args:
            indent: The indentation string.

        Returns:
        A pretty formatted string of the table entry.
        """
        lines: list[str] = [f"{self.__tablename__}"]
        columns = self.columns()
        w = max(len(col) for col in columns)
        for col in columns:
            lines.append(f"{indent}{col:<{w}} {self.__getitem__(col)}")  # noqa: PERF401
        return "\n".join(lines)
