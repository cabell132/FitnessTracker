"""Base service with a scoped SQLAlchemy session context manager."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


class BaseService:
    """Holds a SQLAlchemy engine and exposes session lifecycle helpers."""

    def __init__(self, engine: Engine) -> None:
        """Store the engine used for all operations in this service.

        Args:
            engine (Engine): Bound SQLAlchemy engine.
        """
        self.engine = engine

    @contextmanager
    def get_session(self) -> Iterator[Session]:
        """Yield a session that commits on success and rolls back on error.

        The session is always closed when the context exits.

        Yields:
            Session: Active ORM session tied to :attr:`engine`.

        Raises:
            Exception: Re-raised after rollback if the worker block fails.
        """
        session = Session(self.engine)
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
