from contextlib import contextmanager
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

class BaseService:

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
    
    @contextmanager
    def get_session(self):
        """
        Returns a new session for database operations.

        This session is automatically closed after operations due to the context manager.
        """
        session = Session(self.engine)
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()