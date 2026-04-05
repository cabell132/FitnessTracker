"""Pydantic models for True Coach API request and response payloads."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SelectedExercise(BaseModel):
    """Exercise option selected for a circuit or multi-exercise item."""

    id: str
    name: str


class Attachment(BaseModel):
    """File metadata attached to a comment or assessment item."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    attachment_url: str = Field(
        validation_alias="attachmentUrl",
        serialization_alias="attachmentUrl",
    )
    file_type: str = Field(validation_alias="type", serialization_alias="type")
    size: int


class Commenter(BaseModel):
    """Minimal author record for a comment."""

    id: int
    type: str


class Meta(BaseModel):
    """Pagination metadata for list endpoints."""

    page: int
    total_pages: int
    per_page: int
    total_count: int


class WorkoutItem(BaseModel):
    """Single exercise block within a client workout."""

    id: int
    workout_id: int
    name: str
    info: str
    result: str
    is_circuit: bool
    state: str
    selected_exercises: list[SelectedExercise] = Field(default_factory=list)
    linked: bool
    position: int
    assessment_id: int | None
    created_at: str
    attachments: list[Attachment] = Field(default_factory=list)
    exercise_id: int | None
    request_video: bool


class PutWorkoutItemRequest(BaseModel):
    """Payload for updating a workout item via PUT."""

    id: int
    workout_id: int
    name: str
    info: str
    result: str
    is_circuit: bool
    state: str
    state_event: str | None = None
    position: int
    assessment_id: int | None
    exercise_id: int | None


class PutWorkoutItemResponse(BaseModel):
    """API response wrapping an updated workout item."""

    workout_item: WorkoutItem


class Workout(BaseModel):
    """Client workout summary from the True Coach API."""

    id: int
    due: str
    short_description: str
    created_at: str
    updated_at: str
    title: str | None = None
    state: str
    rest_day: bool
    rest_day_instructions: str
    warmup: str | None
    warmup_selected_exercises: list[int]
    cooldown_selected_exercises: list[int]
    cooldown: str | None
    position: int | None
    order: int
    uuid: str
    program_name: str | None
    hidden: bool
    edit_client_workout: bool
    client_id: int
    comment_ids: list[int]
    note_id: int | None
    program_id: int | None
    workout_item_ids: list[int]


class PutWorkout(BaseModel):
    """Payload for creating or replacing a workout."""

    due: str
    short_description: str
    created_at: str
    updated_at: str
    title: str | None = None
    state: str
    rest_day: bool
    rest_day_instructions: str
    warmup: str | None
    warmup_selected_exercises: list[int]
    cooldown_selected_exercises: list[int]
    cooldown: str | None
    position: int | None
    order: int
    uuid: str
    program_name: str | None
    hidden: bool
    edit_client_workout: bool
    client_id: int
    comment_ids: list[int]
    note_id: int | None
    program_id: int | None
    workout_item: list[int]


class Comment(BaseModel):
    """Comment left on a workout."""

    id: int
    body: str
    workout_id: int
    created_at: str
    attachments: list[Attachment]
    commenter: Commenter


class WorkoutResponse(BaseModel):
    """Paginated list payload for workouts, items, and comments."""

    comments: list[Comment] = Field(default_factory=list)
    workout_items: list[WorkoutItem] = Field(default_factory=list)
    workouts: list[Workout]
    meta: Meta


class ExerciseTags(BaseModel):
    """Tag dimensions returned with a True Coach exercise."""

    pattern: list[str] = Field(default_factory=list)
    plane: list[str] = Field(default_factory=list)
    level: list[str] | None = None
    type: list[str] = Field(default_factory=list)
    primary_muscles: list[str] = Field(default_factory=list)
    secondary_muscles: list[str] | None = None


class Exercise(BaseModel):
    """Trainer or library exercise definition."""

    id: int
    default: bool
    exercise_name: str
    description: str | None
    attachments: list[Attachment]
    trainer_id: int | None
    organization_id: int | None
    tags: ExerciseTags
    url: str | None = None
    video_partner_name: str | None = None


class ExerciseResponse(BaseModel):
    """List response for exercises."""

    exercises: list[Exercise]
    request_url: str


class AssessmentItem(BaseModel):
    """Single logged value for an assessment."""

    id: int
    assessment_id: int
    value: str
    attachments: list[Attachment]
    note: str | None = None
    created_at: str
    updated_at: str
    date: str
    completed_date: str


class Assessment(BaseModel):
    """Assessment definition and configuration."""

    id: int
    assessment_group_id: int
    name: str
    units: str
    order: int
    target: str | None = None
    target_percentage: str | None = None
    linked_assessment_id: int | None = None
    updated_at: str
    created_at: str
    created_by: str
    assessment_item_ids: list[int]


class AssessmentResponse(BaseModel):
    """Response containing one assessment and its item history."""

    assessment_items: list[AssessmentItem]
    assessment: Assessment


class PostAssessment(BaseModel):
    """Payload for submitting a new assessment measurement."""

    assessment_id: str
    value: str
    attachments: list[Attachment]
    note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    date: str


class PostAssessmentItem(BaseModel):
    """Wrapper used when posting assessment data."""

    assessment_item: PostAssessment
