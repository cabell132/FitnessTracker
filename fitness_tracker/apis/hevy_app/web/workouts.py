"""Rich workout reads and pagination for completion-time collection."""

from __future__ import annotations

from collections.abc import Iterator
import builtins
from typing import Any

from pydantic import TypeAdapter

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.hevy_app.web._resource import Resource, segment
from fitness_tracker.apis.hevy_app.web.models import WebRecord, WebWorkout


class WebWorkouts(Resource):
    """Read rich workouts without translating them into the public API schema."""

    def get(self, workout_id: str) -> WebWorkout:
        """Fetch one workout including set IDs and completion timestamps.

        Args:
            workout_id (str): Full workout ID.

        Returns:
            WebWorkout: Validated response with undocumented fields preserved.
        """
        return WebWorkout.model_validate(self._get(f"/workout/{segment(workout_id)}"))

    def list(self, username: str, *, limit: int = 20, offset: int = 0) -> builtins.list[WebWorkout]:
        """Fetch one page of a user's workouts, retaining all rich fields.

        Args:
            username (str): Hevy username.
            limit (int): Requested page size; the server may return fewer records.
            offset (int): Number of records to skip.

        Returns:
            builtins.list[WebWorkout]: Validated response with undocumented fields preserved.

        Raises:
            ValueError: If an argument is invalid.
        """
        if not username or limit < 1 or offset < 0:
            message = "Username, positive limit and nonnegative offset are required"
            raise ValueError(message)
        data = self._get("/user_workouts_paged", username=username, limit=limit, offset=offset)
        return TypeAdapter(builtins.list[WebWorkout]).validate_python(data.get("workouts"))

    def iter_all(self, username: str, *, page_size: int = 20) -> Iterator[WebWorkout]:
        """Read until an empty page, deduplicating overlaps and rejecting stalled pagination.

        Args:
            username (str): Hevy username.
            page_size (int): Requested page size while iterating.

        Yields:
            WebWorkout: Next unique workout with rich fields preserved.

        Raises:
            HevyAppAPIError: If pagination stalls or a read has no JSON body.
        """
        offset = 0
        seen: set[str] = set()
        while page := self.list(username, limit=page_size, offset=offset):
            fresh = [workout for workout in page if workout.id not in seen]
            if not fresh:
                message = "Hevy workout pagination made no progress"
                raise HevyAppAPIError(message, url="/user_workouts_paged")
            for workout in fresh:
                if workout.id not in seen:
                    seen.add(workout.id)
                    yield workout
            offset += len(page)

    def batch(self, start_index: int = 0) -> builtins.list[WebWorkout]:
        """Read an export batch; the cursor is a workout index, not a page number.

        Args:
            start_index (int): First workout index to request.

        Returns:
            builtins.list[WebWorkout]: Validated response with undocumented fields preserved.

        Raises:
            ValueError: If an argument is invalid.
        """
        if start_index < 0:
            message = "Start index must be nonnegative"
            raise ValueError(message)
        return self._list(f"/workouts_batch/{start_index}", WebWorkout)

    def calendar(self, year: int, month: int) -> builtins.list[WebRecord]:
        """Read the workout calendar for a month.

        Args:
            year (int): Calendar year.
            month (int): Calendar month, from 1 to 12.

        Returns:
            builtins.list[WebRecord]: Validated response with undocumented fields preserved.

        Raises:
            ValueError: If an argument is invalid.
        """
        if year < 1 or not 1 <= month <= 12:
            message = "A positive year and month between 1 and 12 are required"
            raise ValueError(message)
        return self._list(f"/user_calendar_workouts/{year}/{month}", WebRecord)

    def metrics(self, metric: str, *, after: int, before: int) -> builtins.list[WebRecord]:
        """Read profile metric records between Unix-second boundaries.

        Args:
            metric (str): Website metric name, such as duration.
            after (int): Inclusive lower time boundary.
            before (int): Upper time boundary.

        Returns:
            builtins.list[WebRecord]: Validated response with undocumented fields preserved.

        Raises:
            ValueError: If an argument is invalid.
        """
        if after >= before:
            message = "Metric start must precede its end"
            raise ValueError(message)
        return self._list(f"/user_workout_metrics/{segment(metric)}/{after}/{before}", WebRecord)

    def comments(self, workout_id: str) -> builtins.list[WebRecord]:
        """Read comments visible to the authenticated user.

        Args:
            workout_id (str): Full workout ID.

        Returns:
            builtins.list[WebRecord]: Validated response with undocumented fields preserved.
        """
        return self._list(f"/workout_comments/{segment(workout_id)}", WebRecord)

    def likes(self, workout_id: str) -> builtins.list[WebRecord]:
        """Read likes visible to the authenticated user.

        Args:
            workout_id (str): Full workout ID.

        Returns:
            builtins.list[WebRecord]: Validated response with undocumented fields preserved.
        """
        return self._list(f"/workout_likes/{segment(workout_id)}", WebRecord)

    def comment(self, workout_id: str, comment: str) -> dict[str, Any] | None:
        """Publish a comment when explicitly requested by the caller.

        Args:
            workout_id (str): Full workout ID.
            comment (str): Comment text to publish.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write(
            "POST", "/workout_comment", json={"workoutId": workout_id, "comment": comment}
        )

    def delete_comment(self, comment_id: str) -> dict[str, Any] | None:
        """Delete an existing comment.

        Args:
            comment_id (str): Comment identifier.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("DELETE", f"/workout_comment/{segment(comment_id)}")

    def like(self, workout_id: str) -> dict[str, Any] | None:
        """Like a workout.

        Args:
            workout_id (str): Full workout ID.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("POST", f"/workout/like/{segment(workout_id)}")

    def unlike(self, workout_id: str) -> dict[str, Any] | None:
        """Remove a workout like.

        Args:
            workout_id (str): Full workout ID.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("POST", f"/workout/unlike/{segment(workout_id)}")
