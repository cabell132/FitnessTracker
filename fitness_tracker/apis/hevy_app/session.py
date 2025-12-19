from typing import Any, Optional

import requests

import logs
from dotenv import load_dotenv
import os

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from urllib.parse import urlencode


load_dotenv()

logger = logs.get_logger(__name__)


class HevyAppSession:
    """HevyApp API session class"""

    def __init__(
        self
    ) -> None:
        """Initiate the client and make sure it is correctly authorized
        If token is passed, it is used to make a call to
        /my/account endpoint to check if the token is access_token is valid

        If the token is not passed, or it is invalid, it authorizes the user
        using username and password credentials given in the config
        and uses the token obtained in this way

        :param token:    HevyAppOAuthToken
        """

        self.api_key = os.environ['HEVY_API_KEY']

    def make_url(self, endpoint: str, query: Optional[dict[str, str]] = None) -> str:
        """Get complete URL for a given API endpoint.

        :param endpoint: API endpoint
        :type endpoint: str
        :param query: Query parameters, defaults to None
        :type query: Optional[Dict[str, str]], optional

        :return: Complete URL for the given endpoint
        :rtype: str
        """

        api_version = "v1"

        api_base: str = f"https://api.hevyapp.com/{api_version}"

        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        if query:
            return api_base + endpoint + "?" + urlencode(query)
        return api_base + endpoint


    def _get_request_headers(self):
        """Formats Authorization and User-Agent HTTP client request headers

        :returns: HTTP client request headers
        :rtype: dict
        """

        return {
            "api-key": self.api_key,
        }

    def format_response(self, endpoint: str, response: requests.Response) -> dict[str, Any]:
        """
        Extract the "results" field from a JSON response.

        :param endpoint: The endpoint that was requested.
        :type endpoint: str
        :param response: The response object to extract the results from.
        :type response: requests.Response
        :return: The "results" field from the JSON response, or the entire JSON response
                if "results" is not present.
        :rtype: Dict[str, Any]
        :raises HevyAppAPIError: If the response is empty or if there is an error with
                                  the response.
        """
        if not response:
            raise HevyAppAPIError(
                f"Error {response.status_code} for '{response.request.path_url}",
                status_code=response.status_code,
                url=response.request.path_url,
            )
        data = response.json()
        if response.status_code == 200:
            if isinstance(data, dict):
                data["request_url"] = response.url
            else:
                data = {"results": data, "request_url": response.url}
        return data


    def make_request(self, method: str, endpoint: str, **kwargs: Any) -> Optional[dict[str, Any]]:
        """Make a request to the HevyApp API.

        :param mode:    Mode of the request, either GET or POST
        :param endpoint: API endpoint to request
        :param params:  Parameters to pass to the API
        :type method:   The method to use for the request
        :type enpoint:  str
        :type params:   Dict[str, Any]
        :return:        JSON response from the API
        :rtype:         Dict[str, Any]
        :raises HevyAppAPIError: If there is an error making the request.
        """
        # Define the headers.
        headers = self._get_request_headers()

        # normalise the url

        if endpoint.startswith("https://"):
            endpoint = endpoint.replace("https://", "")

        url = self.make_url(endpoint)

        print(f"Making request to {url}")

        with requests.Session() as session:
            try:
                headers = self._get_request_headers()
                response = session.request(
                    method.upper(),
                    url,
                    headers=headers,
                    timeout=10,
                    verify=False,
                    **kwargs,
                )
                logger.debug(
                    f"HevyApp API Request: status_code={response.status_code}, url={url}"
                )

            except Exception as e:
                raise HevyAppAPIError(
                    f"Error connecting to HevyApp API: {e}",
                    url=url,
                ) from e
            if not response:
                raise HevyAppAPIError(
                    f"Error {response.status_code} for '{response.request.path_url}' {response.text}",
                    status_code=response.status_code,
                    url=response.request.path_url,
                )
        if response.status_code != 204:
            return self.format_response(endpoint, response)
