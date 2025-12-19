from pydantic import BaseModel,Field

from typing import Optional, Literal

MUSCLE_GROUPS = Literal['abdominals',
 'abductors',
 'adductors',
 'biceps',
 'calves',
 'cardio',
 'chest',
 'forearms',
 'full_body',
 'glutes',
 'hamstrings',
 'lats',
 'lower_back',
 'neck',
 'other',
 'quadriceps',
 'shoulders',
 'traps',
 'triceps',
 'upper_back']

class ExerciseTemplate(BaseModel):
    id: str
    title: str
    type: Literal['bodyweight_assisted', 'bodyweight_weighted', 'distance_duration', 'duration', 'reps_only', 'short_distance_weight', 'weight_duration', 'weight_reps']
    primary_muscle_group: MUSCLE_GROUPS
    secondary_muscle_groups: list[MUSCLE_GROUPS]
    equipment: Literal['barbell', 'dumbbell', 'kettlebell', 'machine', 'none', 'other', 'plate', 'resistance_band', 'suspension']
    is_custom: bool

class ExerciseResponse(BaseModel):
    page: int
    page_count: int
    exercise_templates: list[ExerciseTemplate]

class Set(BaseModel):
    index: int
    type: str
    weight_kg: Optional[float] = None
    reps: Optional[int] = None
    distance_meters: Optional[int] = None
    duration_seconds: Optional[int] = None
    rpe: Optional[int] = None

class Exercise(BaseModel):
    index: int
    title: str
    notes: str
    exercise_template_id: str
    superset_id: Optional[int] = None
    sets: list[Set]

class Workout(BaseModel):
    id: str
    title: str
    description: str
    start_time: str
    end_time: str
    updated_at: str
    created_at: str
    exercises: list[Exercise]

class Routine(BaseModel):
    id: str
    title: str
    updated_at: str
    created_at: str
    exercises: list[Exercise]

class WorkoutResponse(BaseModel):
    page: int
    page_count: int
    workouts: list[Workout]

class UpdatedWorkout(BaseModel):
    type: str
    workout: Workout

class DeletedWorkout(BaseModel):
    type: str
    id: str
    deleted_at: str

class PaginatedWorkoutEvents(BaseModel):
    page: int
    page_count: int
    events: list[UpdatedWorkout | DeletedWorkout] = []

class PostRoutinesRequest(BaseModel):
    title: str
    folder_id: Optional[str] = None
    notes: str
    exercises: list["PostRoutinesRequestExercise"]

class PostRoutinesRequestExercise(BaseModel):
    notes: str
    exercise_template_id: str
    superset_id: Optional[int] = None
    rest_seconds: Optional[int] = None
    sets: list["PostRoutinesRequestSet"]

class PostRoutinesRequestSet(BaseModel):
    type: Literal['normal', 'warmup', 'failure', 'dropset'] = Field(default="normal", description="The type of the set", example="normal")
    weight_kg: Optional[float] = Field(default=None, description="The weight of the set in kg", example=10.0)
    reps: Optional[int] = Field(default=None, description="The number of reps in the set", example=10)
    distance_meters: Optional[int] = Field(default=None, description="The distance in meters", example=100)
    duration_seconds: Optional[int] = Field(default=None, description="The duration in seconds", example=60)

class PostRoutinesRequestBody(BaseModel):
    routine: PostRoutinesRequest

class PostRoutinesResponse(BaseModel):
    routine: list[Routine]

class PostWorkoutsRequestSet(BaseModel):
    type: Literal['normal', 'warmup', 'failure', 'dropset'] = Field(default="normal", description="The type of the set", example="normal")
    weight_kg: Optional[float] = Field(default=None, description="The weight of the set in kg", example=10.0)
    reps: Optional[int] = Field(default=None, description="The number of reps in the set", example=10)
    distance_meters: Optional[int] = Field(default=None, description="The distance in meters", example=100)
    duration_seconds: Optional[int] = Field(default=None, description="The duration in seconds", example=60)
    rpe: Optional[float] = Field(default=None, description="e Rating of Perceived Exertion (RPE)", example=5)

class PostWorkoutsRequestExercise(BaseModel):
    exercise_template_id: str
    notes: Optional[str] = None
    superset_id: Optional[int] = None
    sets: list["PostWorkoutsRequestSet"]

class PostWorkoutsRequest(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: Optional[str] = Field(default=None, description="The time the workout started.", example="2024-08-14T12:00:00Z")
    end_time: Optional[str] = Field(default=None, description="The time the workout ended.", example="2024-08-14T13:00:00Z")
    is_private: bool = Field(default=False, description="A boolean indicating if the workout is private.", example=False)
    exercises: list["PostWorkoutsRequestExercise"]

class PostWorkoutsRequestBody(BaseModel):
    workout: PostWorkoutsRequest

class PostWorkoutsResponse(BaseModel):
    workout: list[Workout]

