"""Composable set-parsing chain replacing scattered LLM / fallback logic.

The :class:`FallbackSetParser` tries each delegate in order and returns the
first non-empty result, giving callers a single ``SetParser``-compatible object
instead of inline ``if not sets: …`` branches.
"""

from __future__ import annotations

from fitness_tracker.llm.prompt_models import PostRoutinesRequestSets
from fitness_tracker.sync.ports.set_parser import SetParser


class FallbackSetParser:
    """Chain parsers: first non-empty result wins.

    Implements :class:`~fitness_tracker.sync.ports.SetParser` so it can be
    injected wherever a ``SetParser`` is expected.
    """

    def __init__(self, *parsers: SetParser) -> None:
        """Build a chain from one or more ``SetParser`` delegates.

        Args:
            *parsers (SetParser): Ordered delegates to try.

        Raises:
            ValueError: If no parsers are provided.
        """
        if not parsers:
            msg = "FallbackSetParser requires at least one delegate"
            raise ValueError(msg)
        self._parsers = parsers

    def parse_the_sets(self, info: str) -> PostRoutinesRequestSets:
        """Try each delegate until one returns a non-empty set list.

        Args:
            info (str): Free-form exercise prescription text.

        Returns:
            PostRoutinesRequestSets: First non-empty result, or the last result if all empty.
        """
        for parser in self._parsers:
            result = parser.parse_the_sets(info)
            if result.sets:
                return result
        # All parsers returned empty — return the last (empty) result
        return result  # type: ignore[possibly-undefined]
