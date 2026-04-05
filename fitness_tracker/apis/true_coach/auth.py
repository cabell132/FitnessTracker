"""True Coach OAuth password grant and token file helpers."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

log = logging.getLogger("api.true_coach")

load_dotenv()

TOKEN_PATH = Path("true_coach_token.json")


def make_url(endpoint: str, query: dict[str, str] | None = None) -> str:
    """Build an absolute URL for a True Coach API path.

    Args:
        endpoint (str): API path, with or without a leading slash.
        query (dict[str, str] | None, optional): Query string parameters. Defaults to None.

    Returns:
        str: Full URL, including optional query string.
    """
    api_base = "https://app.truecoach.co/proxy/api"
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    if query:
        return api_base + endpoint + "?" + urlencode(query)
    return api_base + endpoint


class TrueCoachOAuthToken:
    """In-memory OAuth token returned by the password grant."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Populate fields from the token JSON payload.

        Args:
            data (dict[str, Any]): Raw token dictionary from the API or token file.
        """
        self.access_token = cast(str, data.get("access_token"))
        self.user_id = cast(int, data.get("user_id"))
        self.token_type = cast(str, data.get("token_type"))

    def encode(self) -> dict[str, str]:
        """Serialize the access token for JSON storage.

        Returns:
            dict[str, str]: Minimal dict suitable for ``json.dump``.
        """
        return {
            "access_token": self.access_token,
        }


def _authorize_with_true_coach_api(s: requests.Session) -> TrueCoachOAuthToken:
    """Exchange email and True Coach password for an access token.

    Args:
        s (requests.Session): Session used for the token POST (TLS verify disabled).

    Returns:
        TrueCoachOAuthToken: Parsed token including expiry metadata.

    Note:
        Uses ``response.raise_for_status()`` which may raise ``requests.HTTPError``.
    """
    response = s.post(
        url=make_url("/oauth/token/"),
        json={
            "username": os.environ["EMAIL"],
            "password": os.environ["TRUECOACH_PASSWORD"],
            "grant_type": "password",
        },
        verify=False,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    log.debug("Retrieved access token from the True Coach API: %s", json.dumps(data))
    data["expires_at"] = time.time() + 36000
    TOKEN_PATH.write_text(json.dumps(data), encoding="utf-8")
    return TrueCoachOAuthToken(data)


def check_token_file() -> TrueCoachOAuthToken | None:
    """Load a token from disk when the cache file is present.

    Returns:
        TrueCoachOAuthToken | None: Parsed token, or ``None`` if no file exists.
    """
    if not TOKEN_PATH.is_file():
        return None
    data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    return TrueCoachOAuthToken(data)


def authorize() -> TrueCoachOAuthToken:
    """Return a valid token, refreshing via password grant when needed.

    Returns:
        TrueCoachOAuthToken: Token from cache or freshly obtained from the API.
    """
    log.debug('Started authorizing to the API using "username and password"')
    token = check_token_file()
    if token:
        return token
    with requests.Session() as s:
        return _authorize_with_true_coach_api(s)
