"""Website routine and folder management contracts."""

from __future__ import annotations

import builtins
from typing import Any

from fitness_tracker.apis.hevy_app.web._resource import Resource, segment
from fitness_tracker.apis.hevy_app.web.models import WebFolder, WebRecord, WebRoutine

_SYNC = {"sendSyncEventToMobileApp": "true"}


class WebRoutines(Resource):
    """Read rich prescriptions and manage website routine operations."""

    def get(self, routine_id: str) -> WebRoutine:
        """Fetch a routine using its full ID.

        Args:
            routine_id (str): Full routine ID.

        Returns:
            WebRoutine: Validated response with undocumented fields preserved.
        """
        return WebRoutine.model_validate(
            self._get(f"/routine/{segment(routine_id)}").get("routine")
        )

    def get_shared(self, short_id: str) -> WebRoutine:
        """Fetch a routine by its sharing ID.

        Args:
            short_id (str): Sharing identifier.

        Returns:
            WebRoutine: Validated response with undocumented fields preserved.
        """
        return WebRoutine.model_validate(
            self._get(f"/routine_with_short_id/{segment(short_id)}").get("routine")
        )

    def create(self, routine: dict[str, Any]) -> dict[str, Any] | None:
        """Create using a web-format prescription and notify the mobile app.

        Args:
            routine (dict[str, Any]): Website-format prescription, not a public API response model.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("POST", "/routine", json={"routine": routine}, params=_SYNC)

    def update(self, routine_id: str, routine: dict[str, Any]) -> dict[str, Any] | None:
        """Replace a web-format prescription and notify the mobile app.

        Args:
            routine_id (str): Full routine ID.
            routine (dict[str, Any]): Website-format prescription, not a public API response model.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write(
            "PUT", f"/routine/{segment(routine_id)}", json={"routine": routine}, params=_SYNC
        )

    def delete(self, routine_id: str) -> dict[str, Any] | None:
        """Delete a routine and notify the mobile app.

        Args:
            routine_id (str): Full routine ID.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("DELETE", f"/routine/{segment(routine_id)}", params=_SYNC)

    def copy(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Submit the website's routine-copy body without adding a routine envelope.

        Args:
            request (dict[str, Any]): Website-format request body.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("POST", "/routine_copy", json=request, params=_SYNC)

    def move(self, locations: builtins.list[dict[str, Any]]) -> dict[str, Any] | None:
        """Update routine placement/order using web-format location records.

        Args:
            locations (builtins.list[dict[str, Any]]): Website-format routine location records.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("PUT", "/routine_locations", json={"locations": locations}, params=_SYNC)


class WebFolders(Resource):
    """Read, create, update, delete and reorder routine folders."""

    def list(self) -> builtins.list[WebFolder]:
        """Read all folders in the website response.

        Returns:
            builtins.list[WebFolder]: Validated response with undocumented fields preserved.
        """
        return self._list("/routine_folders", WebFolder)

    def get_shared(self, folder_id: str) -> WebRecord:
        """Read the server's shareable-folder response.

        Args:
            folder_id (str): Folder identifier.

        Returns:
            WebRecord: Validated response with undocumented fields preserved.
        """
        return WebRecord.model_validate(self._get(f"/shareable_folder/{segment(folder_id)}"))

    def create(self, folder: dict[str, Any]) -> dict[str, Any] | None:
        """Create a folder using the website's folder envelope.

        Args:
            folder (dict[str, Any]): Website-format folder properties.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("POST", "/routine_folder", json={"folder": folder}, params=_SYNC)

    def update(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Update a folder using the website's unwrapped request body.

        Args:
            request (dict[str, Any]): Website-format request body.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("PUT", "/routine_folder", json=request, params=_SYNC)

    def delete(self, folder_id: int) -> dict[str, Any] | None:
        """Delete a folder and notify the mobile app.

        Args:
            folder_id (int): Folder identifier.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write("DELETE", f"/routine_folder/{segment(folder_id)}", params=_SYNC)

    def reorder(self, reorders: builtins.list[dict[str, Any]]) -> dict[str, Any] | None:
        """Submit ordered folder records and notify the mobile app.

        Args:
            reorders (builtins.list[dict[str, Any]]): Website-format folder ordering records.

        Returns:
            dict[str, Any] | None: Server response, or None for a bodyless success.
        """
        return self._write(
            "PUT", "/routine_folder_order", json={"reorders": reorders}, params=_SYNC
        )
