"""Structured logging with wide events for the fitness tracker."""

from logs.log import logger
from logs.wide_event import WideEvent

__all__ = [
    "WideEvent",
    "logger",
]
