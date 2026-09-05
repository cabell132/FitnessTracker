"""Lossless response models for Hevy's private website API."""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class WebRecord(BaseModel):
    """Preserve undocumented fields returned by the website API."""

    model_config = ConfigDict(extra="allow")


class WebSet(WebRecord):
    """Performed set with its server identity and optional completion time."""

    id: str
    index: int
    completed_at: AwareDatetime | None = None
    indicator: str
    weight_kg: float | None = None
    reps: int | None = None
    duration_seconds: float | None = None
    distance_meters: float | None = None
    custom_metric: float | None = None
    rpe: float | None = None
    prs: Any = None
    personal_records: Any = Field(default=None, alias="personalRecords")
    geospatial_data: Any = None


class WebExercise(WebRecord):
    """Performed exercise block; rest_seconds is configured rest, not measured rest."""

    id: str
    exercise_template_id: str
    title: str
    sets: list[WebSet]
    rest_seconds: int | None = None
    notes: str | None = None
    superset_id: int | None = None
    pinned_notes: list[Any] = Field(default_factory=list)


class WebWorkout(WebRecord):
    """Rich workout; start/end are Unix seconds and completion times are aware datetimes."""

    id: str
    name: str
    start_time: int
    end_time: int
    exercises: list[WebExercise]
    index: int | None = None
    routine_id: str | None = None
    updated_at: AwareDatetime | None = None
    created_at: AwareDatetime | None = None
    description: str | None = None
    biometrics: dict[str, Any] | None = None


class WebRoutine(WebRecord):
    """Saved prescription; its sets do not require performed-set IDs or timestamps."""

    id: str
    title: str
    exercises: list[WebRecord]
    folder_id: int | None = None
    parent_routine_id: str | None = None
    notes: str | None = None


class WebExerciseTemplate(WebRecord):
    """Custom exercise metadata, including archive and priority state."""

    id: str
    title: str
    exercise_type: str
    is_custom: bool
    is_archived: bool = False


class WebFolder(WebRecord):
    """Routine folder with its display order."""

    id: int
    title: str
    index: int
