"""Set model for Hevy API payloads."""

from __future__ import annotations

from fitness_tracker.apis.hevy_app.types.common import _BaseSetMeasurements


class Set(_BaseSetMeasurements):
    """One logged set inside a workout or routine block."""

    index: int
    type: str
    rpe: int | None = None
