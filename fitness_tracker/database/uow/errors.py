"""Domain-specific errors for UnitOfWork operations."""


class HevyAppPersistenceError(Exception):
    """Raised when Hevy workout or exercise data is missing or inconsistent."""
