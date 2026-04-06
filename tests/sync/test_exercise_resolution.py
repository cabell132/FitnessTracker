"""Unit tests for the shared exercise resolution function."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fitness_tracker.database.models import HevyAppExercise
from fitness_tracker.sync._exercise_resolution import resolve_hevy_exercise


def _make_hevy_exercise(id_: str = "ex1", name: str = "Bench Press") -> HevyAppExercise:
    """Create a HevyAppExercise stub with the given id and name."""
    ex = HevyAppExercise()
    ex.id = id_
    ex.name = name
    return ex


def _make_placeholder(id_: str = "ph1") -> HevyAppExercise:
    """Create a placeholder exercise."""
    return _make_hevy_exercise(id_=id_, name="#####PLACEHOLDER#####")


class TestResolveHevyExercise:
    """Tests for the 6-step exercise resolution chain."""

    def test_direct_tc_link_returns_exercise(self) -> None:
        """Step 1: When TC exercise has a direct Hevy link, use it."""
        uow = MagicMock()
        linked = _make_hevy_exercise("linked-1", "Squat")
        placeholders: list[HevyAppExercise] = [_make_placeholder()]
        used: list[HevyAppExercise] = []

        exercise, note = resolve_hevy_exercise(
            uow=uow,
            item_name="Squat",
            tc_exercise_hevy_app=linked,
            placeholders=placeholders,
            used=used,
        )

        assert exercise is linked
        assert note is None
        assert len(placeholders) == 1  # not consumed

    def test_name_lookup_finds_hevy_app(self) -> None:
        """Step 2: When tracker exercise has a Hevy link via name lookup."""
        uow = MagicMock()
        hevy_link = _make_hevy_exercise("tracker-hevy", "Deadlift")
        tracker_exercise = MagicMock()
        tracker_exercise.hevy_app = hevy_link
        uow.tracker_get_exercise.return_value = tracker_exercise
        placeholders: list[HevyAppExercise] = [_make_placeholder()]
        used: list[HevyAppExercise] = []

        exercise, note = resolve_hevy_exercise(
            uow=uow,
            item_name="Deadlift",
            tc_exercise_hevy_app=None,
            placeholders=placeholders,
            used=used,
        )

        assert exercise is hevy_link
        assert note is None
        uow.tracker_get_exercise.assert_called_once_with(name="Deadlift")

    def test_name_lookup_no_hevy_uses_placeholder(self) -> None:
        """Step 2 fallback: tracker exercise exists but has no Hevy link."""
        uow = MagicMock()
        tracker_exercise = MagicMock()
        tracker_exercise.hevy_app = None
        uow.tracker_get_exercise.return_value = tracker_exercise
        ph = _make_placeholder("ph-1")
        placeholders: list[HevyAppExercise] = [ph]
        used: list[HevyAppExercise] = []

        exercise, note = resolve_hevy_exercise(
            uow=uow,
            item_name="Unknown Exercise",
            tc_exercise_hevy_app=None,
            placeholders=placeholders,
            used=used,
        )

        assert exercise is ph
        assert note == "Unknown Exercise"
        assert len(placeholders) == 0

    def test_no_match_inserts_and_uses_placeholder(self) -> None:
        """Step 3: No match anywhere — insert exercise and use placeholder."""
        uow = MagicMock()
        uow.tracker_get_exercise.return_value = None
        ph = _make_placeholder("ph-2")
        placeholders: list[HevyAppExercise] = [ph]
        used: list[HevyAppExercise] = []

        exercise, note = resolve_hevy_exercise(
            uow=uow,
            item_name="New Exercise",
            tc_exercise_hevy_app=None,
            placeholders=placeholders,
            used=used,
        )

        assert exercise is ph
        assert note == "New Exercise"
        uow.insert_ignore.assert_called_once()

    def test_dedup_swaps_to_placeholder(self) -> None:
        """Step 4: If exercise already used, swap to placeholder."""
        uow = MagicMock()
        linked = _make_hevy_exercise("dup-1", "Bench Press")
        ph = _make_placeholder("ph-dedup")
        placeholders: list[HevyAppExercise] = [ph]
        used: list[HevyAppExercise] = [linked]  # already used

        exercise, note = resolve_hevy_exercise(
            uow=uow,
            item_name="Bench Press",
            tc_exercise_hevy_app=linked,
            placeholders=placeholders,
            used=used,
        )

        assert exercise is ph
        assert note == "Bench Press"

    def test_exhausted_placeholders_raises_index_error(self) -> None:
        """Step 5: Guard for exhausted placeholders."""
        uow = MagicMock()
        uow.tracker_get_exercise.return_value = None
        placeholders: list[HevyAppExercise] = []  # empty!
        used: list[HevyAppExercise] = []

        with pytest.raises(IndexError):
            resolve_hevy_exercise(
                uow=uow,
                item_name="Exercise",
                tc_exercise_hevy_app=None,
                placeholders=placeholders,
                used=used,
            )

    def test_none_item_name_uses_placeholder(self) -> None:
        """When item_name is None, skip lookup and use placeholder."""
        uow = MagicMock()
        ph = _make_placeholder("ph-none")
        placeholders: list[HevyAppExercise] = [ph]
        used: list[HevyAppExercise] = []

        exercise, note = resolve_hevy_exercise(
            uow=uow,
            item_name=None,
            tc_exercise_hevy_app=None,
            placeholders=placeholders,
            used=used,
        )

        assert exercise is ph
        assert note is None
        uow.tracker_get_exercise.assert_not_called()
