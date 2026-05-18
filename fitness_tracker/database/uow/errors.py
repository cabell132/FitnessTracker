"""Domain-specific persistence errors."""


class HevyAppPersistenceError(Exception):
    """Raised when Hevy workout or exercise data is missing or inconsistent."""
