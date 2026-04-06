"""Hevy App user info endpoint."""

from fitness_tracker.apis.hevy_app.session import HevyAppSession
from fitness_tracker.apis.hevy_app.types import UserInfoResponse


class HevyAppUsers:
    """Retrieve authenticated user profile information."""

    def __init__(self, session: HevyAppSession) -> None:
        """Attach the REST session used for user calls.

        Args:
            session (HevyAppSession): Authenticated API session.
        """
        self._session = session
        self.endpoint = "/user/info"

    def get_info(self) -> UserInfoResponse | None:
        """Fetch the authenticated user's profile.

        Returns:
            UserInfoResponse | None: User info wrapper, or ``None`` when empty.
        """
        data = self._session.make_request(method="GET", endpoint=self.endpoint)
        if data:
            return UserInfoResponse(**data)
        return None
