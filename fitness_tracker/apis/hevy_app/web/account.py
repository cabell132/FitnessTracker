"""Profile, preference and webhook interfaces used by Hevy's website."""

from __future__ import annotations

from typing import Any

from fitness_tracker.apis.hevy_app.web._resource import Resource, segment
from fitness_tracker.apis.hevy_app.web.models import WebRecord


class WebUsers(Resource):
    """Read visible profiles and social data and explicitly manage follow relationships."""

    def profile(self, username: str) -> WebRecord:
        """Read a visible profile, including routine references and weekly durations.

        Args:
            username (str): Hevy username.

        Returns:
            WebRecord: Validated response with undocumented fields preserved.
        """
        return WebRecord.model_validate(self._get(f"/user_profile/{segment(username)}"))

    def search(self, query: str) -> WebRecord:
        """Read the website's user-search response without assuming its envelope.

        Args:
            query (str): User search text.

        Returns:
            WebRecord: Validated response with undocumented fields preserved.
        """
        return WebRecord.model_validate(self._get(f"/users/{segment(query)}"))

    def following(self, username: str) -> WebRecord:
        """Read the website's following response.

        Args:
            username (str): Hevy username.

        Returns:
            WebRecord: Validated response with undocumented fields preserved.
        """
        return WebRecord.model_validate(self._get(f"/following/{segment(username)}"))

    def follow_counts(self) -> WebRecord:
        """Read follow counts for the authenticated account.

        Returns:
            WebRecord: Validated response with undocumented fields preserved.
        """
        return WebRecord.model_validate(self._get("/follow_counts"))

    def feed(self, cursor: str | None = None) -> WebRecord:
        """Read one feed page, preserving the server's envelope.

        Args:
            cursor (str | None): Feed cursor, or None for the first page.

        Returns:
            WebRecord: Validated response with undocumented fields preserved.
        """
        path = (
            "/feed_workouts_paged" if cursor is None else f"/feed_workouts_paged/{segment(cursor)}"
        )
        return WebRecord.model_validate(self._get(path))

    def follow(self, username: str) -> dict[str, Any] | None:
        """Follow a user when explicitly requested by the caller.

        Args:
            username (str): Hevy username.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("POST", "/follow", json={"username": username})

    def unfollow(self, username: str) -> dict[str, Any] | None:
        """Remove a follow relationship.

        Args:
            username (str): Hevy username.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("POST", "/unfollow", json={"username": username})


class WebPreferences(Resource):
    """Read and update the website's preference body."""

    def get(self) -> WebRecord:
        """Read current preferences without discarding unknown settings.

        Returns:
            WebRecord: Validated response with undocumented fields preserved.
        """
        return WebRecord.model_validate(self._get("/v2/user_preferences"))

    def update(self, preferences: dict[str, Any]) -> dict[str, Any] | None:
        """Submit preferences using the website's unwrapped request body.

        Args:
            preferences (dict[str, Any]): Website-format preference fields.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("PUT", "/user_preferences", json=preferences)


class WebWebhooks(Resource):
    """Webhook configuration; server errors propagate because 404 semantics are unverified."""

    def get(self) -> dict[str, Any]:
        """Read subscription configuration; the response may contain an auth token.

        Returns:
            dict[str, Any]: Result of the requested operation.
        """
        return self._get("/webhook-subscription")

    def subscribe(self, url: str, *, auth_token: str) -> dict[str, Any] | None:
        """Submit an explicit webhook destination and authentication token.

        Args:
            url (str): Webhook receiver URL.
            auth_token (str): Secret sent to authenticate webhook deliveries.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write(
            "POST", "/webhook-subscription", json={"url": url, "authToken": auth_token}
        )
