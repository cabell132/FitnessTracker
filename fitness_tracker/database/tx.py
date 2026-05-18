"""Transaction-scoped repository container."""

# ruff: noqa: D102,PLR0913

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from pandas import DataFrame
from sqlalchemy.orm import Query, Session

from fitness_tracker.apis.hevy_app.types import (
    Exercise as HevyExercise,
    ExerciseTemplate,
    ExerciseResponse as HevyExerciseResponse,
    Set as HevySet,
    Workout as HevyWorkout,
    WorkoutResponse as HevyWorkoutResponse,
)
from fitness_tracker.apis.true_coach.types import (
    AssessmentItem,
    AssessmentResponse,
    Exercise as TrueCoachExercisePayload,
    ExerciseResponse as TrueCoachExerciseResponse,
    ExerciseTags,
    PutWorkoutItemRequest,
    Workout as TrueCoachWorkoutPayload,
    WorkoutItem as TrueCoachWorkoutItemPayload,
)
from fitness_tracker.database.models.base import BaseModel
from fitness_tracker.database.models.hevy_app import HevyAppExercise, HevyAppWorkout
from fitness_tracker.database.models.tracker import (
    Exercise as TrackerExercise,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import (
    TrueCoachWorkout,
    TrueCoachWorkoutItem,
)
from fitness_tracker.database.uow.apple_health import AppleHealthMixin
from fitness_tracker.database.uow.base import CrudMixin
from fitness_tracker.database.uow.hevy import HevyExerciseTemplateSource, HevyMixin
from fitness_tracker.database.uow.sql_ops import SqlOpsMixin
from fitness_tracker.database.uow.tracker import TrackerMixin
from fitness_tracker.database.uow.true_coach import TrueCoachMixin

ExerciseTemplateFetcher = Callable[[str], ExerciseTemplate | None]


@runtime_checkable
class HevyRepo(Protocol):
    """Hevy persistence operations exposed to sync callers."""

    def add_exercises(self, exercises: HevyExerciseResponse) -> None: ...
    def add_exercise(self, exercise: ExerciseTemplate) -> None: ...
    def add_set(self, workout_item_id: int, workout_set: HevySet) -> None: ...
    def add_workout_item(self, workout_id: str, exercise: HevyExercise) -> None: ...
    def add_workout(self, workout: HevyWorkout) -> None: ...
    def add_workouts(self, workouts: HevyWorkoutResponse) -> None: ...
    def get_workout(self, **kwargs: Any) -> HevyAppWorkout | None: ...
    def get_placeholders(self) -> list[HevyAppExercise]: ...
    def delete_workout(self, **kwargs: Any) -> None: ...


@runtime_checkable
class TrueCoachRepo(Protocol):
    """True Coach persistence operations exposed to sync callers."""

    def add_exercises(self, exercises: TrueCoachExerciseResponse) -> None: ...
    def add_exercise(self, exercise: TrueCoachExercisePayload) -> None: ...
    def add_exercise_tags(
        self,
        exercise_id: int,
        tag: ExerciseTags | None = None,
        *,
        tags: list[str] | None = None,
        category: str | None = None,
    ) -> None: ...
    def add_workout(self, workout: TrueCoachWorkoutPayload) -> None: ...
    def add_workout_item(self, workout_item: TrueCoachWorkoutItemPayload) -> None: ...
    def update_workout_item(self, workout_item: PutWorkoutItemRequest) -> None: ...
    def get_workout(self, **kwargs: Any) -> TrueCoachWorkout | None: ...
    def get_workouts(self, **kwargs: Any) -> list[TrueCoachWorkout]: ...
    def get_workout_item(self, **kwargs: Any) -> TrueCoachWorkoutItem | None: ...
    def get_workout_items(self, **kwargs: Any) -> list[TrueCoachWorkoutItem]: ...
    def add_assessment_item(self, assessment: AssessmentItem) -> None: ...
    def add_assessment(self, assessment: AssessmentResponse) -> None: ...
    def delete_workout(self, workout: TrueCoachWorkout) -> None: ...


@runtime_checkable
class TrackerRepo(Protocol):
    """Canonical tracker persistence operations exposed to sync callers."""

    def add_workout(self, workout: TrueCoachWorkout) -> None: ...
    def get_workout(self, **kwargs: Any) -> TrackerWorkout | None: ...
    def add_exercise(self, exercise: Any) -> None: ...
    def get_exercise(self, **kwargs: Any) -> TrackerExercise | None: ...
    def get_workout_item_by_index(
        self, workout_id: int, index: int
    ) -> TrackerWorkoutItem | None: ...

    def link_workout_item_hevy_id(self, true_coach_id: int, hevy_app_id: int) -> None: ...
    def link_metric_item_to_true_coach(self, metric_item_id: int, true_coach_id: int) -> None: ...


@runtime_checkable
class AppleHealthRepo(Protocol):
    """Apple Health persistence operations exposed to sync callers."""

    def add_data_records(self, df: DataFrame) -> None: ...
    def add_workouts(self, df: DataFrame) -> None: ...


@runtime_checkable
class CrossDomainOps(Protocol):
    """Cross-domain SQL operations exposed to sync callers."""

    def link_hevy_tracker_workout_items(self, true_coach_id: int) -> None: ...
    def get_unlinked_tc_workout_items(self, true_coach_id: int) -> list[dict[str, Any]]: ...
    def get_unlinked_hevy_workout_items(self, true_coach_id: int) -> list[dict[str, Any]]: ...
    def update_workout_exercise_ids_from_hevy(self, true_coach_id: int) -> None: ...
    def update_hevy_tracker_exercises(self, true_coach_id: int) -> None: ...
    def update_hevy_tracker_sets(self, true_coach_id: int) -> None: ...
    def insert_hevy_tracker_sets(self, true_coach_id: int) -> None: ...
    def insert_tc_tracker_workout_items(self) -> None: ...
    def insert_apple_health_metrics(self) -> None: ...
    def insert_hevy_calories_burned_metrics(self) -> None: ...
    def select_tracker_tc_assessments(self) -> list[Any]: ...


@runtime_checkable
class SessionOps(Protocol):
    """Narrow session operations needed outside a domain repository."""

    def query(self, *entities: Any, **kwargs: Any) -> Query[Any]: ...
    def get(self, model: type[BaseModel], **kwargs: Any) -> BaseModel | None: ...
    def get_all(self, model: type[BaseModel], **kwargs: Any) -> list[BaseModel]: ...
    def add(self, obj: BaseModel) -> None: ...
    def merge(self, obj: BaseModel) -> None: ...
    def insert_ignore(self, obj: BaseModel) -> None: ...
    def delete(self, obj: BaseModel) -> None: ...
    def flush(self) -> None: ...
    def expire_all(self) -> None: ...


class _RepoBase(CrudMixin):
    """Bind existing persistence helpers to one SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the active transaction session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        self._session = session


class _CallableTemplateSource:
    """Adapter from the Tx callback to the legacy Hevy helper shape."""

    def __init__(self, fetch_template: ExerciseTemplateFetcher) -> None:
        """Store the template fetch callback.

        Args:
            fetch_template (ExerciseTemplateFetcher): Callback for loading a
                missing Hevy exercise template.
        """
        self._fetch_template = fetch_template

    def get_template(self, template_id: str) -> ExerciseTemplate | None:
        return self._fetch_template(template_id)


class HevyRepoImpl(_RepoBase, HevyMixin):
    """Hevy repository implementation."""

    def __init__(
        self,
        session: Session,
        fetch_template: ExerciseTemplateFetcher | None = None,
    ) -> None:
        """Create a Hevy repository bound to the active transaction.

        Args:
            session (Session): Active SQLAlchemy session.
            fetch_template (ExerciseTemplateFetcher | None): Optional callback
                for loading missing Hevy exercise templates.
        """
        super().__init__(session)
        self._exercise_template_source: HevyExerciseTemplateSource | None = (
            _CallableTemplateSource(fetch_template) if fetch_template is not None else None
        )

    def add_exercises(self, exercises: HevyExerciseResponse) -> None:
        self.hevy_add_exercises(exercises)

    def add_exercise(self, exercise: ExerciseTemplate) -> None:
        self.hevy_add_exercise(exercise)

    def add_set(self, workout_item_id: int, workout_set: HevySet) -> None:
        self.hevy_add_set(workout_item_id, workout_set)

    def add_workout_item(self, workout_id: str, exercise: HevyExercise) -> None:
        self.hevy_add_workout_item(
            workout_id,
            exercise,
            exercise_template_source=self._exercise_template_source,
        )

    def add_workout(self, workout: HevyWorkout) -> None:
        self.hevy_add_workout(
            workout,
            exercise_template_source=self._exercise_template_source,
        )

    def add_workouts(self, workouts: HevyWorkoutResponse) -> None:
        self.hevy_add_workouts(
            workouts,
            exercise_template_source=self._exercise_template_source,
        )

    def get_workout(self, **kwargs: Any) -> HevyAppWorkout | None:
        return self.hevy_get_workout(**kwargs)

    def get_placeholders(self) -> list[HevyAppExercise]:
        return self.hevy_get_placeholders()

    def delete_workout(self, **kwargs: Any) -> None:
        self.hevy_delete_workout(**kwargs)


class TrueCoachRepoImpl(_RepoBase, TrueCoachMixin):
    """True Coach repository implementation."""

    def add_exercises(self, exercises: TrueCoachExerciseResponse) -> None:
        self.tc_add_exercises(exercises)

    def add_exercise(self, exercise: TrueCoachExercisePayload) -> None:
        self.tc_add_exercise(exercise)

    def add_exercise_tags(
        self,
        exercise_id: int,
        tag: ExerciseTags | None = None,
        *,
        tags: list[str] | None = None,
        category: str | None = None,
    ) -> None:
        if tag is not None:
            self.tc_add_exercise_tags(exercise_id, tag)
            return
        if tags is None or category is None:
            msg = "Provide either tag or both tags and category"
            raise TypeError(msg)
        self._tc_ensure_tags(exercise_id, tags, category)

    def add_workout(self, workout: TrueCoachWorkoutPayload) -> None:
        self.tc_add_workout(workout)

    def add_workout_item(self, workout_item: TrueCoachWorkoutItemPayload) -> None:
        self.tc_add_workout_item(workout_item)

    def update_workout_item(self, workout_item: PutWorkoutItemRequest) -> None:
        self.tc_update_workout_item(workout_item)

    def get_workout(self, **kwargs: Any) -> TrueCoachWorkout | None:
        return self.tc_get_workout(**kwargs)

    def get_workouts(self, **kwargs: Any) -> list[TrueCoachWorkout]:
        return self.tc_get_workouts(**kwargs)

    def get_workout_item(self, **kwargs: Any) -> TrueCoachWorkoutItem | None:
        return self.tc_get_workout_item(**kwargs)

    def get_workout_items(self, **kwargs: Any) -> list[TrueCoachWorkoutItem]:
        return self.tc_get_workout_items(**kwargs)

    def add_assessment_item(self, assessment: AssessmentItem) -> None:
        self.tc_add_assessment_item(assessment)

    def add_assessment(self, assessment: AssessmentResponse) -> None:
        self.tc_add_assessment(assessment)

    def delete_workout(self, workout: TrueCoachWorkout) -> None:
        self.tc_delete_workout(workout)


class TrackerRepoImpl(_RepoBase, TrackerMixin):
    """Tracker repository implementation."""

    def add_workout(self, workout: TrueCoachWorkout) -> None:
        self.tracker_add_workout(workout)

    def get_workout(self, **kwargs: Any) -> TrackerWorkout | None:
        return self.tracker_get_workout(**kwargs)

    def add_exercise(self, exercise: Any) -> None:
        self.tracker_add_exercise(exercise)

    def get_exercise(self, **kwargs: Any) -> TrackerExercise | None:
        return self.tracker_get_exercise(**kwargs)

    def get_workout_item_by_index(self, workout_id: int, index: int) -> TrackerWorkoutItem | None:
        return self.tracker_get_workout_item_by_index(workout_id, index)


class AppleHealthRepoImpl(_RepoBase, AppleHealthMixin):
    """Apple Health repository implementation."""

    def add_data_records(self, df: DataFrame) -> None:
        self.ah_add_data_records(df)

    def add_workouts(self, df: DataFrame) -> None:
        self.ah_add_workouts(df)


class CrossDomainOpsImpl(_RepoBase, SqlOpsMixin):
    """Cross-domain SQL repository implementation."""


class SessionOpsImpl(_RepoBase):
    """Generic session operations kept out of domain repositories."""

    def query(self, *entities: Any, **kwargs: Any) -> Query[Any]:
        return super().query(*entities, **kwargs)

    def get(self, model: type[BaseModel], **kwargs: Any) -> BaseModel | None:
        return super().get(model, **kwargs)

    def get_all(self, model: type[BaseModel], **kwargs: Any) -> list[BaseModel]:
        return super().get_all(model, **kwargs)

    def add(self, obj: BaseModel) -> None:
        super().add(obj)

    def delete(self, obj: BaseModel) -> None:
        super().delete(obj)


class Tx:
    """Transaction-scoped container that vends domain repositories."""

    def __init__(
        self,
        session: Session,
        fetch_template: ExerciseTemplateFetcher | None = None,
    ) -> None:
        """Create domain repositories bound to the same transaction session.

        Args:
            session (Session): Active SQLAlchemy session.
            fetch_template (ExerciseTemplateFetcher | None): Optional callback
                for loading missing Hevy exercise templates.
        """
        self.hevy: HevyRepo = HevyRepoImpl(session, fetch_template)
        self.true_coach: TrueCoachRepo = TrueCoachRepoImpl(session)
        self.tracker: TrackerRepo = TrackerRepoImpl(session)
        self.apple_health: AppleHealthRepo = AppleHealthRepoImpl(session)
        self.cross_domain: CrossDomainOps = CrossDomainOpsImpl(session)
        self.session = SessionOpsImpl(session)

    def add(self, obj: BaseModel) -> None:
        self.session.add(obj)

    def hevy_add_workout_item(self, workout_id: str, exercise: HevyExercise) -> None:
        self.hevy.add_workout_item(workout_id, exercise)

    def hevy_add_workout(self, workout: HevyWorkout) -> None:
        self.hevy.add_workout(workout)
