"""VeSync API session — handles authentication and HTTP communication."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from rnet.blocking import BlockingClient

from fitness_tracker.apis.vesync.auth import API_BASE_EU, API_BASE_US, hash_password, login
from fitness_tracker.apis.vesync.cache import (
    CACHE_FILE,
    DEFAULT_TTL_SECONDS,
    CacheHandler,
    FileCacheHandler,
)
from fitness_tracker.apis.vesync.exceptions import VeSyncAPIError

logger = logging.getLogger(__name__)
logging.getLogger("fitness_tracker.apis.vesync").addHandler(logging.NullHandler())

VESYNC_API_URL = API_BASE_US
_REGION_API_MAP = {"US": API_BASE_US, "EU": API_BASE_EU}
_USER_AGENT = "okhttp/3.12.1"


class VeSyncSession:
    """Manages authentication and HTTP requests to the VeSync API."""

    def __init__(
        self,
        email: str,
        password: str,
        cache_handler: CacheHandler | None = None,
    ) -> None:
        """Initialise session with credentials.

        Args:
            email (str): VeSync account email address.
            password (str): VeSync account password (plaintext).
            cache_handler (CacheHandler | None): Pluggable token cache.
                Defaults to :class:`FileCacheHandler`.
        """
        self._email = email
        self._password_md5 = hash_password(password)
        self._client = BlockingClient()
        self._token: str | None = None
        self._account_id: str | None = None
        self._region: str = "US"
        self._cache_handler: CacheHandler | None = cache_handler
        if self._cache_handler is None:
            self._cache_handler = FileCacheHandler(cache_path=CACHE_FILE)

    @property
    def account_id(self) -> str | None:
        """The authenticated VeSync account ID."""
        return self._account_id

    def _login(self, ctx: dict[str, Any] | None = None) -> None:
        """Authenticate via cached token or fresh login.

        Args:
            ctx (dict[str, Any] | None): Wide event context to annotate.
        """
        if self._cache_handler is not None:
            cached = self._cache_handler.get_token()
            if cached is not None and time.time() < cached.get("expiresAt", 0):
                self._token = cached["token"]
                self._account_id = cached["accountID"]
                self._region = cached.get("region", "US")
                if ctx is not None:
                    ctx["auth"] = "cache"
                return

        token_data = login(self._email, self._password_md5)
        self._apply_token_data(token_data)
        if self._cache_handler is not None:
            cache_entry: dict[str, Any] = {
                "token": token_data["token"],
                "accountID": token_data["accountID"],
                "region": token_data.get("region", "US"),
                "expiresAt": time.time() + DEFAULT_TTL_SECONDS,
            }
            self._cache_handler.save_token(cache_entry)
        if ctx is not None:
            ctx["auth"] = "login"

    def _apply_token_data(self, data: dict[str, Any]) -> None:
        """Set session fields from a token data dict.

        Args:
            data (dict[str, Any]): Token data with ``token`` key.
        """
        self._token = data["token"]
        self._account_id = data["accountID"]
        self._region = data.get("region", "US")

    def _ensure_authenticated(self, ctx: dict[str, Any] | None = None) -> None:
        """Log in if no token exists.

        Args:
            ctx (dict[str, Any] | None): Wide event context to annotate.
        """
        if self._token is None:
            self._login(ctx)
        elif ctx is not None:
            ctx["auth"] = "existing"

    def _get_common_body(self) -> dict[str, Any]:
        """Build common VeSync request body parameters.

        Returns:
            dict[str, Any]: Common body fields for VeSync API requests.
        """
        return {
            "token": self._token,
            "accountID": self._account_id,
            "timeZone": "America/New_York",
            "acceptLanguage": "en",
            "appVersion": "5.6.60",
            "phoneBrand": "pyvesync",
            "phoneOS": "Android",
            "traceId": str(uuid.uuid4()),
        }

    def _build_body(self, extra: dict[str, Any] | None) -> dict[str, Any]:
        """Merge common params with endpoint-specific body fields.

        Args:
            extra (dict[str, Any] | None): Endpoint-specific fields.

        Returns:
            dict[str, Any]: Merged request body.
        """
        merged = self._get_common_body()
        if extra:
            merged.update(extra)
        return merged

    def make_request(
        self,
        endpoint: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an authenticated POST request.

        All VeSync API requests are POST with JSON body that
        includes auth credentials.

        Args:
            endpoint (str): Relative API endpoint path.
            body (dict[str, Any] | None): Endpoint-specific body
                fields to merge with common parameters.

        Returns:
            dict[str, Any]: Parsed JSON response body.
        """
        t0 = time.monotonic()
        ctx: dict[str, Any] = {
            "request_id": str(uuid.uuid4()),
            "method": "POST",
            "endpoint": endpoint,
        }

        self._ensure_authenticated(ctx)

        base = _REGION_API_MAP.get(self._region, API_BASE_US)
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        url = f"{base}{path}"

        response = self._do_request(url, self._build_body(body))

        if response.status_code.as_int() == 401:
            ctx["auth"] = "retry_401"
            self._token = None
            self._login(ctx)
            response = self._do_request(url, self._build_body(body))

        self._emit_wide_event(ctx, t0, response)
        return response.json()

    def _emit_wide_event(self, ctx: dict[str, Any], t0: float, response: Any) -> None:
        """Finalise and emit the wide event log line.

        Args:
            ctx (dict[str, Any]): Mutable wide event context dict.
            t0 (float): Monotonic start time of the request.
            response (Any): Raw HTTP response object.

        Raises:
            VeSyncAPIError: If the HTTP request failed.

        """
        status = response.status_code.as_int()
        ctx["status"] = status
        ctx["duration_ms"] = int((time.monotonic() - t0) * 1000)
        ctx["outcome"] = "error" if status >= 400 else "success"
        logger.info("VeSync request completed", extra=ctx)
        if status >= 400:
            raise VeSyncAPIError.from_response(response)

    def _do_request(self, url: str, body: dict[str, Any]) -> Any:
        """Send a single POST request with JSON body.

        Args:
            url (str): Fully-qualified URL.
            body (dict[str, Any]): JSON request body.

        Returns:
            Any: The raw HTTP response object.
        """
        return self._client.post(
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
            timeout=10,
        )
