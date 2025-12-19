import logging

from sqlalchemy.engine import Engine

from fitness_tracker.database.models import *  # noqa: F403
from fitness_tracker.database.services import (
    FitnessTrackerService,
    HevyAppService,
    TrueCoachService,
    AppleHealthService,
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

    def __init__(self, engine: Engine):
        """Initialize a connection to a MySQL database.

        Args:
            engine: A connection to the MySQL database.

        Attributes:
            connection: A connection to the MySQL database.
        """
        self.engine = engine
        logger.debug("Database engine: %s", self.engine)

        self.true_coach = TrueCoachService(engine)
        self.hevy_app = HevyAppService(engine)
        self.tracker = FitnessTrackerService(engine)
        self.apple_health = AppleHealthService(engine)

        # Enable foreign key constraints
        # @event.listens_for(self.engine, "connect")
        # def set_sqlite_pragma(dbapi_connection: Connection, connection_record: Any):
        #     cursor = dbapi_connection.cursor()
        #     cursor.execute("PRAGMA foreign_keys=ON")
        #     cursor.close()

    def init_db(self):
        """Create tables in the database using the SQLAlchemy metadata."""
        BaseModel.metadata.create_all(self.engine)  # noqa: F405

    def drop_tables(self):
        """Drop tables in the database using the SQLAlchemy metadata."""
        BaseModel.metadata.drop_all(self.engine)  # noqa: F405
