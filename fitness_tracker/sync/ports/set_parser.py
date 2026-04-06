"""Port for parsing free-text exercise prescriptions into structured set rows."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fitness_tracker.llm.prompt_models import PostRoutinesRequestSets


@runtime_checkable
class SetParser(Protocol):
    """Parse free-text exercise prescriptions into structured set rows."""

    def parse_the_sets(self, info: str) -> PostRoutinesRequestSets:
        """Parse free-text prescription into structured set rows.

        Args:
            info (str): Free-form exercise prescription text.

        Returns:
            PostRoutinesRequestSets: Parsed normal/warmup/failure/dropset rows.
        """
        ...
