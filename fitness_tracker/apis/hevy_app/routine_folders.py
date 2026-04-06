"""Hevy App routine folder endpoints."""

from fitness_tracker.apis.hevy_app.session import HevyAppSession
from fitness_tracker.apis.hevy_app.types import (
    PostRoutineFolderRequestBody,
    RoutineFolder,
    RoutineFolderResponse,
)


class HevyAppRoutineFolders:
    """List, fetch, and create routine folders."""

    def __init__(self, session: HevyAppSession) -> None:
        """Attach the REST session used for routine folder calls.

        Args:
            session (HevyAppSession): Authenticated API session.
        """
        self._session = session
        self.endpoint = "/routine_folders"

    def get(self, page: int = 1, per_page: int = 10) -> RoutineFolderResponse | None:
        """List routine folders with pagination.

        Args:
            page (int): Page index (1-based).
            per_page (int): Page size (max 10).

        Returns:
            RoutineFolderResponse | None: Parsed list payload, or ``None`` when empty.
        """
        query = {"page": page, "pageSize": per_page}
        data = self._session.make_request(method="GET", endpoint=self.endpoint, params=query)
        if data:
            return RoutineFolderResponse(**data)
        return None

    def get_folder(self, folder_id: int) -> RoutineFolder | None:
        """Fetch a single routine folder by id.

        Args:
            folder_id (int): Routine folder id.

        Returns:
            RoutineFolder | None: Parsed folder, or ``None`` when empty.
        """
        endpoint = f"{self.endpoint}/{folder_id}"
        data = self._session.make_request(method="GET", endpoint=endpoint)
        if data:
            return RoutineFolder(**data)
        return None

    def create(self, folder: PostRoutineFolderRequestBody) -> RoutineFolder | None:
        """Create a new routine folder (inserted at index 0).

        Args:
            folder (PostRoutineFolderRequestBody): Wrapper accepted by the API.

        Returns:
            RoutineFolder | None: Created folder, or ``None`` when empty.
        """
        data = self._session.make_request(
            method="POST", endpoint=self.endpoint, json=folder.model_dump()
        )
        if data:
            return RoutineFolder(**data)
        return None
