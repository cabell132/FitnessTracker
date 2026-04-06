"""UnitOfWork: transaction-scoped facade composing all domain mixins."""

from __future__ import annotations

from sqlalchemy.orm import Session

from fitness_tracker.database.uow.apple_health import AppleHealthMixin
from fitness_tracker.database.uow.hevy import HevyMixin
from fitness_tracker.database.uow.sql_ops import SqlOpsMixin
from fitness_tracker.database.uow.tracker import TrackerMixin
from fitness_tracker.database.uow.true_coach import TrueCoachMixin


class UnitOfWork(
    HevyMixin,
    TrueCoachMixin,
    TrackerMixin,
    AppleHealthMixin,
    SqlOpsMixin,
):
    """Transaction-scoped context with generic CRUD and domain helpers.

    Composes domain mixins for Hevy, True Coach, Tracker, Apple Health,
    and cross-schema SQL operations.  Callers interact with domain methods;
    the session is never exposed directly.
    """

    def __init__(self, session: Session) -> None:
        """Bind to an active SQLAlchemy session.

        Args:
            session (Session): Active ORM session managed by :class:`Store`.
        """
        self._session = session
