"""Unit tests for the composable FallbackSetParser chain."""

import pytest

from fitness_tracker.llm.prompt_models import PostRoutinesRequestSets
from fitness_tracker.sync._fallback_set_parser import FallbackSetParser
from fitness_tracker.sync.ports.set_parser import SetParser


# ---------------------------------------------------------------------------
# Tiny fakes
# ---------------------------------------------------------------------------


def _make_fake(sets_to_return: list[dict]) -> SetParser:
    """Build a fake SetParser returning a fixed result.

    Args:
        sets_to_return: List of set dicts (empty list → empty result).
    """

    class _Fake:
        def parse_the_sets(self, info: str) -> PostRoutinesRequestSets:
            return PostRoutinesRequestSets(sets=sets_to_return)

    return _Fake()


EMPTY: list[dict] = []
ONE_SET = [{"type": "normal", "duration_seconds": 60}]
TWO_SETS = [
    {"type": "normal", "weight_kg": 100, "reps": 5},
    {"type": "normal", "weight_kg": 100, "reps": 5},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_first_non_empty_result() -> None:
    chain = FallbackSetParser(_make_fake(EMPTY), _make_fake(ONE_SET))
    result = chain.parse_the_sets("anything")
    assert len(result.sets) == 1


def test_skips_to_second_when_first_empty() -> None:
    chain = FallbackSetParser(_make_fake(EMPTY), _make_fake(TWO_SETS))
    result = chain.parse_the_sets("anything")
    assert len(result.sets) == 2


def test_uses_first_parser_when_it_succeeds() -> None:
    chain = FallbackSetParser(_make_fake(ONE_SET), _make_fake(TWO_SETS))
    result = chain.parse_the_sets("anything")
    assert len(result.sets) == 1


def test_returns_empty_when_all_parsers_empty() -> None:
    chain = FallbackSetParser(_make_fake(EMPTY), _make_fake(EMPTY))
    result = chain.parse_the_sets("anything")
    assert len(result.sets) == 0


def test_single_parser_chain() -> None:
    chain = FallbackSetParser(_make_fake(ONE_SET))
    result = chain.parse_the_sets("anything")
    assert len(result.sets) == 1


def test_raises_on_no_parsers() -> None:
    with pytest.raises(ValueError, match="at least one delegate"):
        FallbackSetParser()
