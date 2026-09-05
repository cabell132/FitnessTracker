"""Rotating credentials for Hevy's private web API."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError

HEVY_WEB_API_BASE_URL = "https://api.hevyapp.com"
HEVY_WEB_CLIENT_API_KEY = "shelobs_hevy_web"
DEFAULT_EXPIRY_SAFETY_WINDOW = timedelta(seconds=60)
DEFAULT_HEVY_WEB_CREDENTIALS_PATH = Path(".hevy-web-auth.json")


def hevy_web_auth_headers(
    access_token: str,
    *,
    legacy: bool = False,
    client_time: datetime | None = None,
) -> dict[str, str]:
    """Build the authentication contract shared by Hevy web requests.

    Args:
        access_token (str): Current access token or legacy web token.
        legacy (bool): Also send the old ``auth-token`` header.
        client_time (datetime | None): Include Hevy's refresh timestamp header.

    Returns:
        dict[str, str]: Required Hevy web request headers.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "hevy-platform": "web",
        "x-api-key": HEVY_WEB_CLIENT_API_KEY,
    }
    if legacy:
        headers["auth-token"] = access_token
    if client_time is not None:
        headers["x-client-time"] = str(client_time.timestamp())
    return headers


def default_hevy_web_credentials_path() -> Path:
    """Return the configured rotating-credential file path.

    Returns:
        Path: ``HEVY_WEB_AUTH_PATH`` when set, otherwise a repository-local default.
    """
    configured = os.environ.get("HEVY_WEB_AUTH_PATH")
    return Path(configured) if configured else DEFAULT_HEVY_WEB_CREDENTIALS_PATH


@dataclass(frozen=True)
class HevyWebCredentials:
    """Access and refresh tokens issued by Hevy web authentication."""

    access_token: str
    refresh_token: str
    expires_at: datetime

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HevyWebCredentials:
        """Validate a decoded Hevy credential payload.

        Args:
            value (dict[str, Any]): Mapping containing the three credential fields.

        Returns:
            HevyWebCredentials: Validated credentials with a UTC expiry.

        Raises:
            ValueError: When fields are missing or malformed.
        """
        try:
            access_token = value["access_token"]
            refresh_token = value["refresh_token"]
            raw_expiry = value["expires_at"]
        except KeyError as exc:
            message = (
                "Invalid Hevy web credentials: expected access_token, refresh_token, expires_at"
            )
            raise ValueError(message) from exc
        if not all(
            isinstance(field, str) and field for field in (access_token, refresh_token, raw_expiry)
        ):
            message = (
                "Invalid Hevy web credentials: expected access_token, refresh_token, expires_at"
            )
            raise ValueError(message)
        try:
            expires_at = datetime.fromisoformat(raw_expiry)
        except ValueError as exc:
            message = "Invalid Hevy web credentials: expires_at must be ISO-8601"
            raise ValueError(message) from exc
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at.astimezone(UTC),
        )

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable credential mapping.

        Returns:
            dict[str, str]: Credential fields, including an ISO-8601 UTC expiry.
        """
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.astimezone(UTC).isoformat(),
        }

    def expires_soon(
        self,
        *,
        now: datetime,
        safety_window: timedelta = DEFAULT_EXPIRY_SAFETY_WINDOW,
    ) -> bool:
        """Return whether the access token should be refreshed.

        Args:
            now (datetime): Current aware timestamp.
            safety_window (timedelta): How early to refresh before expiry.

        Returns:
            bool: True when expiry is within the safety window.
        """
        return self.expires_at <= now.astimezone(UTC) + safety_window


class HevyWebCredentialStore:
    """Atomically persist rotating credentials in a mode-0600 JSON file."""

    def __init__(self, path: Path) -> None:
        """Create a store at ``path``.

        Args:
            path (Path): Credential JSON path.
        """
        self.path = path

    def load(self) -> HevyWebCredentials | None:
        """Read the current credential pair.

        Returns:
            HevyWebCredentials | None: Stored credentials, or None when not bootstrapped.
        """
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            message = f"Could not read Hevy web credentials from {self.path}"
            raise ValueError(message) from exc
        if not isinstance(value, dict):
            message = f"Invalid Hevy web credential document at {self.path}"
            raise TypeError(message)
        return HevyWebCredentials.from_dict(value)

    def save(self, credentials: HevyWebCredentials) -> None:
        """Atomically replace the credential file.

        Args:
            credentials (HevyWebCredentials): Newly issued rotating credentials.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                json.dump(credentials.to_dict(), handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.chmod(0o600)
            temporary_path.replace(self.path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Hold a cross-process refresh lock.

        Yields:
            None: Control while the exclusive file lock is held.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(f"{self.path.name}.lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def import_cookie_payload(self, raw_payload: str) -> HevyWebCredentials:
        """Validate and save Hevy's ``auth2.0-token`` cookie value.

        Args:
            raw_payload (str): JSON, URL-encoded JSON, or a complete cookie assignment.

        Returns:
            HevyWebCredentials: Imported credentials.
        """
        payload = raw_payload.strip()
        if payload.startswith("auth2.0-token="):
            payload = payload.partition("=")[2]
        try:
            decoded = json.loads(unquote(payload))
        except json.JSONDecodeError as exc:
            message = "Invalid Hevy auth2.0-token cookie payload"
            raise ValueError(message) from exc
        if not isinstance(decoded, dict):
            message = "Invalid Hevy auth2.0-token cookie payload"
            raise TypeError(message)
        credentials = HevyWebCredentials.from_dict(decoded)
        self.save(credentials)
        return credentials


class HevyWebAuth:
    """Supply valid access tokens and rotate expired credential pairs."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        store: HevyWebCredentialStore | None,
        legacy_token: str,
        transport: Callable[..., requests.Response] | None = None,
        clock: Callable[[], datetime] | None = None,
        safety_window: timedelta = DEFAULT_EXPIRY_SAFETY_WINDOW,
    ) -> None:
        """Configure token loading and refresh transport.

        Args:
            store (HevyWebCredentialStore | None): Rotating credential store.
            legacy_token (str): Old single-token fallback during migration.
            transport (Callable[..., requests.Response] | None): Injectable HTTP transport.
            clock (Callable[[], datetime] | None): Injectable aware clock.
            safety_window (timedelta): How early to refresh.
        """
        self._store = store
        self._legacy_token = legacy_token
        self._transport = transport or requests.request
        self._clock = clock or (lambda: datetime.now(UTC))
        self._safety_window = safety_window

    @property
    def has_rotating_credentials(self) -> bool:
        """Return whether a rotating credential pair has been imported.

        Returns:
            bool: True when the credential store contains a refresh token.
        """
        return self._store is not None and self._store.load() is not None

    def access_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid access token, refreshing when required.

        Args:
            force_refresh (bool): Refresh even if the current expiry is in the future.

        Returns:
            str: Access token for the next web request.
        """
        credentials = self._store.load() if self._store is not None else None
        if credentials is None:
            if not self._legacy_token:
                message = "Hevy web credentials are not configured; import an auth2.0-token cookie"
                raise ValueError(message)
            return self._legacy_token
        if not force_refresh and not credentials.expires_soon(
            now=self._clock(), safety_window=self._safety_window
        ):
            return credentials.access_token
        return self.refresh(force=force_refresh).access_token

    def refresh(self, *, force: bool = True) -> HevyWebCredentials:
        """Rotate and persist the current credential pair.

        Args:
            force (bool): Refresh even if another process has already renewed the token.

        Returns:
            HevyWebCredentials: Newly persisted credentials.

        Raises:
            ValueError: When no rotating credentials have been imported.
            HevyAppAPIError: When Hevy rejects the refresh request.
        """
        if self._store is None:
            message = "Hevy web refresh credentials have not been imported"
            raise ValueError(message)
        with self._store.locked():
            credentials = self._store.load()
            if credentials is None:
                message = "Hevy web refresh credentials have not been imported"
                raise ValueError(message)
            if not force and not credentials.expires_soon(
                now=self._clock(), safety_window=self._safety_window
            ):
                return credentials
            return self._request_refresh(credentials)

    def _request_refresh(self, credentials: HevyWebCredentials) -> HevyWebCredentials:
        store = self._store
        if store is None:
            message = "Hevy web refresh credentials have not been imported"
            raise ValueError(message)
        now = self._clock()
        url = f"{HEVY_WEB_API_BASE_URL}/auth/refresh_token"
        response = self._transport(
            "POST",
            url,
            headers={
                **hevy_web_auth_headers(credentials.access_token, client_time=now),
                "Content-Type": "application/json",
            },
            json={"refresh_token": credentials.refresh_token},
            timeout=10,
            verify=False,
        )
        if not response.ok:
            message = (
                f"Hevy web token refresh failed with status {response.status_code}. "
                "Reauthenticate in the Hevy browser and import a new auth2.0-token cookie."
            )
            raise HevyAppAPIError(
                message, status_code=response.status_code, url=response.url or url
            )
        refreshed = self._parse_refresh_response(response, url=url)
        store.save(refreshed)
        return refreshed

    @staticmethod
    def _parse_refresh_response(
        response: requests.Response,
        *,
        url: str,
    ) -> HevyWebCredentials:
        try:
            value = response.json()
        except ValueError as exc:
            message = "Hevy web token refresh returned invalid JSON"
            raise HevyAppAPIError(message, status_code=response.status_code, url=url) from exc
        if not isinstance(value, dict):
            message = "Hevy web token refresh returned an invalid credential document"
            raise HevyAppAPIError(message, status_code=response.status_code, url=url)
        try:
            refreshed = HevyWebCredentials.from_dict(value)
        except ValueError as exc:
            message = "Hevy web token refresh returned incomplete credentials"
            raise HevyAppAPIError(message, status_code=response.status_code, url=url) from exc
        return refreshed
