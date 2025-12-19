from typing import Optional
from pydantic import BaseModel


class WorkoutItem(BaseModel):
    id: int
    workout_id: int
    name: str
    info: str
    result: str
    is_circuit: bool
    state: str
    selected_exercises: list["SelectedExercise"] = []
    linked: bool
    position: int
    assessment_id: Optional[int]
    created_at: str
    attachments: list["Attachment"] = []
    exercise_id: Optional[int]
    request_video: bool


class PutWorkoutItemRequest(BaseModel):
    id: int
    workout_id: int
    name: str
    info: str
    result: str
    is_circuit: bool
    state: str
    state_event: Optional[str] = None
    position: int
    assessment_id: Optional[int]
    # created_at: str
    exercise_id: Optional[int]


class PutWorkoutItemResponse(BaseModel):
    workout_item: WorkoutItem


class SelectedExercise(BaseModel):
    id: str
    name: str


class Attachment(BaseModel):
    name: str
    attachmentUrl: str
    type: str
    size: int


class Workout(BaseModel):
    id: int
    due: str
    short_description: str
    created_at: str
    updated_at: str
    title: Optional[str] = None
    state: str
    rest_day: bool
    rest_day_instructions: str
    warmup: Optional[str]
    warmup_selected_exercises: list[int]
    cooldown_selected_exercises: list[int]
    cooldown: Optional[str]
    position: Optional[int]
    order: int
    uuid: str
    program_name: Optional[str]
    hidden: bool
    edit_client_workout: bool
    client_id: int
    comment_ids: list[int]
    note_id: Optional[int]
    program_id: Optional[int]
    workout_item_ids: list[int]


class PutWorkout(BaseModel):
    due: str
    short_description: str
    created_at: str
    updated_at: str
    title: Optional[str] = None
    state: str
    rest_day: bool
    rest_day_instructions: str
    warmup: Optional[str]
    warmup_selected_exercises: list[int]
    cooldown_selected_exercises: list[int]
    cooldown: Optional[str]
    position: Optional[int]
    order: int
    uuid: str
    program_name: Optional[str]
    hidden: bool
    edit_client_workout: bool
    client_id: int
    comment_ids: list[int]
    note_id: Optional[int]
    program_id: Optional[int]
    workout_item: list[int]


class WorkoutResponse(BaseModel):
    comments: list["Comment"] = []
    workout_items: list[WorkoutItem] = []
    workouts: list[Workout]
    meta: "Meta"


class Meta(BaseModel):
    page: int
    total_pages: int
    per_page: int
    total_count: int


class Comment(BaseModel):
    id: int
    body: str
    workout_id: int
    created_at: str
    attachments: list[Attachment]
    commenter: "Commenter"


class Commenter(BaseModel):
    id: int
    type: str


class ExerciseTags(BaseModel):
    pattern: list[str] = []  # Default to an empty list
    plane: list[str] = []
    level: Optional[list[str]] = None
    type: list[str] = []
    primary_muscles: list[str] = []
    secondary_muscles: Optional[list[str]] = None


class Exercise(BaseModel):
    id: int
    default: bool
    exercise_name: str
    description: Optional[str]
    attachments: list[Attachment]
    trainer_id: Optional[int]
    organization_id: Optional[int]
    tags: ExerciseTags
    url: Optional[str] = None
    video_partner_name: Optional[str] = None


class ExerciseResponse(BaseModel):
    exercises: list[Exercise]
    request_url: str


class AssessmentItem(BaseModel):
    id: int
    assessment_id: int
    value: str
    attachments: list[Attachment]
    note: Optional[str] = None
    created_at: str
    updated_at: str
    date: str
    completed_date: str


class Assessment(BaseModel):
    id: int
    assessment_group_id: int
    name: str
    units: str
    order: int
    target: Optional[str] = None
    target_percentage: Optional[str] = None
    linked_assessment_id: Optional[int] = None
    updated_at: str
    created_at: str
    created_by: str
    assessment_item_ids: list[int]


class AssessmentResponse(BaseModel):
    assessment_items: list[AssessmentItem]
    assessment: Assessment


class PostAssessment(BaseModel):
    assessment_id: str
    value: str
    attachments: list[Attachment]
    note: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    date: str


class PostAssessmentItem(BaseModel):
    assessment_item: PostAssessment
