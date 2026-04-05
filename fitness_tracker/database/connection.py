"""Database facade wiring SQLAlchemy engine to domain services."""

import logging

from sqlalchemy.engine import Engine

from fitness_tracker.database.models.base import BaseModel
from fitness_tracker.database.services import (
    AppleHealthService,
    FitnessTrackerService,
    HevyAppService,
    TrueCoachService,
)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Database:
    """A class representing a connection to a MySQL database.

    This class provides methods for creating and dropping triggers, fetching rows from
    the database, and getting parameters for a Songstats creator query.

    Attributes:
        connection: A connection to the MySQL database.
    """

    def __init__(self, engine: Engine) -> None:
        """Initialize a connection to a MySQL database.

        Args:
            engine (Engine): SQLAlchemy engine for the fitness tracker database.
        """
        self.engine = engine
        logger.debug("Database engine: %s", self.engine)

        self.true_coach = TrueCoachService(engine)
        self.hevy_app = HevyAppService(engine)
        self.tracker = FitnessTrackerService(engine)
        self.apple_health = AppleHealthService(engine)

    def init_db(self) -> None:
        """Create tables in the database using the SQLAlchemy metadata."""
        BaseModel.metadata.create_all(self.engine)

    def drop_tables(self) -> None:
        """Drop tables in the database using the SQLAlchemy metadata."""
        BaseModel.metadata.drop_all(self.engine)
