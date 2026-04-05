"""Single application logger configured at import time.

All log output flows through this one ``logger`` instance: structured
JSON to ``logs/fitness_tracker.log`` and a concise human-readable
summary to the console.  Third-party library noise is suppressed here
so every consumer gets a quiet baseline.
"""

import logging
from pathlib import Path

from logs.console_formatter import ConsoleFormatter
from logs.formatters import JsonFileFormatter

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "fitness_tracker.log"


def _configure_logger() -> logging.Logger:
    """Create and configure the single application logger.

    Returns:
        logging.Logger: Logger writing JSON to file and readable text to console.
    """
    log = logging.getLogger("fitness_tracker")

    if log.hasHandlers():
        return log

    log.setLevel(logging.INFO)
    log.propagate = False

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(JsonFileFormatter())
    file_handler.setLevel(logging.INFO)
    log.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ConsoleFormatter())
    console_handler.setLevel(logging.INFO)
    log.addHandler(console_handler)

    for name in ("httpcore", "openai", "sqlalchemy", "urllib3", "httpx", "alembic"):
        logging.getLogger(name).setLevel(logging.WARNING)

    return log


logger = _configure_logger()
