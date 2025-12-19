import json
import logging
import os
import time
from typing import Any, Dict, Optional, cast
from urllib.parse import urlencode
from dotenv import load_dotenv
import certifi

import requests

log = logging.getLogger("api.true_coach")

load_dotenv()


def make_url(endpoint: str, query: Optional[Dict[str, str]] = None) -> str:
    """Get complete URL for a given API endpoint.

    :param endpoint: API endpoint
    :type endpoint: str
    :param query: Query parameters, defaults to None
    :type query: Optional[Dict[str, str]], optional

    :return: Complete URL for the given endpoint
    :rtype: str
    """

    api_base: str = f"https://app.truecoach.co/proxy/api"

    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    if query:
        return api_base + endpoint + "?" + urlencode(query)
    return api_base + endpoint


class TrueCoachOAuthToken:
    """TrueCoach OAuth token class"""

    def __init__(self, data: Dict[str, Any]) -> None:
        """Initiate the token class

        :param cfg: The true_coach configuration
        :type cfg: TrueCoachConfig
        :param data: The token data
        :type data: Dict[str, Any]
        """
        self.access_token = cast(str, data.get("access_token"))
        self.user_id = cast(int, data.get("user_id"))
        self.token_type = cast(str, data.get("token_type"))

    def encode(self):
        """Encodes the class into json serializable object"""
        return {
            "access_token": self.access_token,
        }


def _authorize_with_true_coach_api(
 s: requests.Session
) -> TrueCoachOAuthToken:
    """
    Authorize the user with the TrueCoach API.

    :param cfg: The true_coach configuration
    :type cfg: TrueCoachConfig
    :param s: The requests session to use for the authorization.
    :type s: requests.Session
    :return: The TrueCoachOAuthToken object containing the access token
             and refresh token.
    :rtype: TrueCoachOAuthToken
    :raises TrueCoachAPIError: If there is an error with the authorization process.
    """
    # Login to get session id and csrf token cookies

    response = s.post(
        url=make_url("/oauth/token/"),
        json={"username": os.environ['EMAIL'], "password": os.environ['TRUECOACH_PASSWORD'], "grant_type": "password"},
        verify=False
    )
    
    data = response.json()
    log.debug(
        'Retrieved access token from the True Coach API',
        json.dumps(data),
    )

    data["expires_at"] = time.time() + 36000

    # Save token to file
    with open("true_coach_token.json", "w", encoding="utf-8") as f:
        json.dump(data, f)

    return TrueCoachOAuthToken(data)


def check_token_file():
    """
    Check if the token file exists
    if it does, check if the token is valid
    if it is, return the token
    """
    file = "true_coach_token.json"
    if os.path.isfile(file):
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            token = TrueCoachOAuthToken(data)
            # if not token.is_expired():
            return token


def authorize() -> TrueCoachOAuthToken:
    """Authorize client and fetch access token.
    Uses username and password provided by the user in the config.
    Uses authorization_code grant type in TrueCoach OAuth flow.

    :param cfg: The true_coach configuration
    :type cfg: TrueCoachConfig
    :returns:               TrueCoach OAuth token
    :rtype:                 :py:class:`TrueCoachOAuthToken`
    """
    log.debug('Started authorizing to the API using "username and password"')

    # Check if token file exists
    token = check_token_file()
    if token:
        return token

    with requests.Session() as s:
        return _authorize_with_true_coach_api(s)
