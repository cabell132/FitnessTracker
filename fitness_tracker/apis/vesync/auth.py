"""VeSync two-step login authentication."""

from __future__ import annotations

import hashlib
import logging
import platform
import uuid
from typing import Any

from rnet.blocking import BlockingClient

from fitness_tracker.apis.vesync.exceptions import VeSyncAuthError

logger = logging.getLogger(__name__)

API_BASE_US = "https://smartapi.vesync.com"
API_BASE_EU = "https://smartapi.vesync.eu"
_REGION_API_MAP = {"US": API_BASE_US, "EU": API_BASE_EU}
_AUTH_PATH = "/globalPlatform/api/accountAuth/v1/authByPWDOrOTM"
_LOGIN_PATH = "/user/api/accountManage/v1/loginByAuthorizeCode4Vesync"
_USER_AGENT = "okhttp/3.12.1"
_APP_VERSION = "5.6.60"
_APP_ID = "eldodkfj"
_CLIENT_TYPE = "vesyncApp"
_TERMINAL_ID = (
    "2"
    + uuid.uuid5(
        uuid.NAMESPACE_DNS,
        f"{uuid.getnode():x}-{platform.node() or ''}",
    ).hex
)


def hash_password(password: str) -> str:
    """Hash a password using MD5 for VeSync authentication.

    Args:
        password (str): The plaintext password.

    Returns:
        str: The MD5 hex digest of the password.
    """
    return hashlib.md5(password.encode()).hexdigest()  # noqa: S324  # nosemgrep: md5-used-as-password


def _common_fields() -> dict[str, Any]:
    """Build common request fields shared by both auth steps.

    Returns:
        dict[str, Any]: Common request body fields.
    """
    return {
        "acceptLanguage": "en",
        "accountID": "",
        "clientInfo": "pyvesync",
        "clientType": _CLIENT_TYPE,
        "clientVersion": f"VeSync {_APP_VERSION}",
        "debugMode": False,
        "osInfo": "Android",
        "terminalId": _TERMINAL_ID,
        "timeZone": "America/New_York",
        "token": "",
        "userCountryCode": "US",
        "appID": _APP_ID,
        "traceId": str(int(__import__("time").time())),
    }


def _post(client: BlockingClient, url: str, body: dict[str, Any]) -> dict[str, Any]:
    """Send a POST request and return the parsed JSON body.

    Args:
        client (BlockingClient): HTTP client instance.
        url (str): Request URL.
        body (dict[str, Any]): JSON request body.

    Returns:
        dict[str, Any]: Parsed response body.

    Raises:
        VeSyncAuthError: On HTTP or network errors.
    """
    try:
        response = client.post(
            url,
            json=body,
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "User-Agent": _USER_AGENT,
            },
            timeout=10,
        )
    except Exception as exc:
        msg = f"VeSync auth request failed: {exc}"
        raise VeSyncAuthError(message=msg, error="auth_network_error") from exc

    status = response.status_code.as_int()
    if status >= 400:
        msg = f"VeSync auth rejected (HTTP {status})"
        raise VeSyncAuthError(message=msg, error="auth_rejected")

    return response.json()


def _get_authorize_code(
    client: BlockingClient,
    email: str,
    password_md5: str,
) -> tuple[str, str]:
    """Step 1: Get an authorization code using credentials.

    Args:
        client (BlockingClient): HTTP client instance.
        email (str): VeSync account email.
        password_md5 (str): MD5-hashed password.

    Returns:
        tuple[str, str]: ``(authorize_code, account_id)``.

    Raises:
        VeSyncAuthError: If authentication fails.
    """
    body = {
        **_common_fields(),
        "email": email,
        "password": password_md5,
        "method": "authByPWDOrOTM",
        "authProtocolType": "generic",
        "sourceAppID": _APP_ID,
    }

    resp = _post(client, f"{API_BASE_US}{_AUTH_PATH}", body)

    if resp.get("code") != 0:
        msg = resp.get("msg", "Authentication failed")
        raise VeSyncAuthError(message=str(msg), error="auth_failed")

    result = resp.get("result", {})
    authorize_code = result.get("authorizeCode")

    if not authorize_code:
        msg = "No authorization code in response"
        raise VeSyncAuthError(message=msg, error="auth_failed")

    return authorize_code, result.get("accountID", "")


def _exchange_token(  # noqa: PLR0913 - mirrors VeSync's region redirect state
    client: BlockingClient,
    authorize_code: str,
    base_url: str = API_BASE_US,
    biz_token: str | None = None,
    country_code: str = "US",
) -> dict[str, Any]:
    """Step 2: Exchange an authorization code for a session token.

    Handles cross-region redirects by retrying with the correct
    region when VeSync returns a cross-region error.

    Args:
        client (BlockingClient): HTTP client instance.
        authorize_code (str): Authorization code from step 1.
        base_url (str): API base URL for the current region.
        biz_token (str | None): Business token for region change retry.
        country_code (str): User country code.

    Returns:
        dict[str, Any]: Token result dict including ``token``,
            ``accountID``, and ``currentRegion``.

    Raises:
        VeSyncAuthError: If the token exchange fails.
    """
    body = {
        **_common_fields(),
        "method": "loginByAuthorizeCode4Vesync",
        "authorizeCode": authorize_code,
        "emailSubscriptions": False,
        "userCountryCode": country_code,
    }
    if biz_token is not None:
        body["bizToken"] = biz_token
        body["regionChange"] = "lastRegion"

    resp = _post(client, f"{base_url}{_LOGIN_PATH}", body)
    result = resp.get("result", {})

    if resp.get("code") != 0:
        # Cross-region: retry with the region from the error response
        if result.get("bizToken") and result.get("currentRegion"):
            new_region = result["currentRegion"]
            new_base = _REGION_API_MAP.get(new_region, API_BASE_US)
            logger.debug("Cross-region redirect to %s", new_region)
            return _exchange_token(
                client,
                authorize_code,
                base_url=new_base,
                biz_token=result["bizToken"],
                country_code=result.get("countryCode", country_code),
            )
        msg = resp.get("msg", "Token exchange failed")
        raise VeSyncAuthError(message=str(msg), error="login_failed")

    if not result.get("token"):
        msg = "No token in login response"
        raise VeSyncAuthError(message=msg, error="login_failed")

    return result


def login(email: str, password_md5: str) -> dict[str, Any]:
    """Authenticate with VeSync using the two-step login flow.

    Args:
        email (str): VeSync account email.
        password_md5 (str): MD5-hashed password.

    Returns:
        dict[str, Any]: Token data with ``token``, ``accountID``,
            and ``region``.
    """
    client = BlockingClient()
    authorize_code, account_id = _get_authorize_code(client, email, password_md5)
    result = _exchange_token(client, authorize_code)
    region = result.get("currentRegion", "US")

    logger.debug("VeSync login successful for %s (region=%s)", email, region)

    return {
        "token": result["token"],
        "accountID": result.get("accountID", account_id),
        "region": region,
    }
