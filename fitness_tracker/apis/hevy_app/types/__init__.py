"""Hevy App API type models — re-exported for backward compatibility."""

from fitness_tracker.apis.hevy_app.types.common import (
    CUSTOM_EXERCISE_TYPES,
    EQUIPMENT_CATEGORIES,
    MUSCLE_GROUPS,
)
from fitness_tracker.apis.hevy_app.types.exercise import Exercise
from fitness_tracker.apis.hevy_app.types.exercise_history import (
    ExerciseHistoryEntry,
    ExerciseHistoryResponse,
)
from fitness_tracker.apis.hevy_app.types.exercise_template import (
    ExerciseResponse,
    ExerciseTemplate,
)
from fitness_tracker.apis.hevy_app.types.exercise_template_requests import (
    CreateCustomExercise,
    CreateCustomExerciseRequestBody,
    CreateCustomExerciseResponse,
)
from fitness_tracker.apis.hevy_app.types.routine import Routine, RoutineResponse
from fitness_tracker.apis.hevy_app.types.routine_folders import (
    PostRoutineFolderRequest,
    PostRoutineFolderRequestBody,
    RoutineFolder,
    RoutineFolderResponse,
)
from fitness_tracker.apis.hevy_app.types.routine_post_requests import (
    PostRoutinesRequest,
    PostRoutinesRequestBody,
    PostRoutinesRequestExercise,
    PostRoutinesRequestSet,
    PostRoutinesResponse,
)
from fitness_tracker.apis.hevy_app.types.routine_put_requests import (
    PutRoutinesRepRange,
    PutRoutinesRequest,
    PutRoutinesRequestBody,
    PutRoutinesRequestExercise,
    PutRoutinesRequestSet,
)
from fitness_tracker.apis.hevy_app.types.set import Set
from fitness_tracker.apis.hevy_app.types.user import UserInfo, UserInfoResponse
from fitness_tracker.apis.hevy_app.types.workout import Workout, WorkoutResponse
from fitness_tracker.apis.hevy_app.types.workout_events import (
    DeletedWorkout,
    PaginatedWorkoutEvents,
    UpdatedWorkout,
)
from fitness_tracker.apis.hevy_app.types.workout_request_body import (
    PostWorkoutsRequestBody,
    PostWorkoutsResponse,
)
from fitness_tracker.apis.hevy_app.types.workout_requests import (
    PostWorkoutsRequest,
    PostWorkoutsRequestExercise,
    PostWorkoutsRequestSet,
)

__all__ = [
    "CUSTOM_EXERCISE_TYPES",
    "EQUIPMENT_CATEGORIES",
    "MUSCLE_GROUPS",
    "CreateCustomExercise",
    "CreateCustomExerciseRequestBody",
    "CreateCustomExerciseResponse",
    "DeletedWorkout",
    "Exercise",
    "ExerciseHistoryEntry",
    "ExerciseHistoryResponse",
    "ExerciseResponse",
    "ExerciseTemplate",
    "PaginatedWorkoutEvents",
    "PostRoutineFolderRequest",
    "PostRoutineFolderRequestBody",
    "PostRoutinesRequest",
    "PostRoutinesRequestBody",
    "PostRoutinesRequestExercise",
    "PostRoutinesRequestSet",
    "PostRoutinesResponse",
    "PostWorkoutsRequest",
    "PostWorkoutsRequestBody",
    "PostWorkoutsRequestExercise",
    "PostWorkoutsRequestSet",
    "PostWorkoutsResponse",
    "PutRoutinesRepRange",
    "PutRoutinesRequest",
    "PutRoutinesRequestBody",
    "PutRoutinesRequestExercise",
    "PutRoutinesRequestSet",
    "Routine",
    "RoutineFolder",
    "RoutineFolderResponse",
    "RoutineResponse",
    "Set",
    "UpdatedWorkout",
    "UserInfo",
    "UserInfoResponse",
    "Workout",
    "WorkoutResponse",
]
