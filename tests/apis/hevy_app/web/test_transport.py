"""Client wiring and real HTTP response normalization without network calls."""

import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from fitness_tracker.apis.hevy_app.client import HevyAppClient
from fitness_tracker.apis.hevy_app.web import HevyWebClient
from fitness_tracker.apis.hevy_app.web_auth import HevyWebAuth
from fitness_tracker.apis.hevy_app.web_session import HevyWebSession


def web_session():
    token = "fake-web-token"
    return HevyWebSession(auth=HevyWebAuth(store=None, legacy_token=token))


@pytest.mark.parametrize("status", [200, 201, 204])
def test_successful_empty_web_mutation_is_not_a_json_error(status):
    response = requests.Response()
    response.status_code = status
    response._content = b""
    response.url = "https://api.hevyapp.com/user_preferences"
    with patch("requests.Session.request", return_value=response) as request:
        result = HevyWebClient(web_session()).preferences.update({"rpe_enabled": True})
    assert result in ({}, None)
    assert request.call_count == 1
    assert request.call_args.kwargs["json"] == {"rpe_enabled": True}


def test_http_list_response_is_normalized_into_typed_folder_records():
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps([{"id": 1, "title": "Block", "index": 0}]).encode()
    response.url = "https://api.hevyapp.com/routine_folders"
    with patch("requests.Session.request", return_value=response):
        result = HevyWebClient(web_session()).folders.list()
    assert result[0].title == "Block"


@pytest.mark.parametrize(
    ("resource", "method", "args"),
    [
        ("routines", "create", ({"title": "Block"},)),
        ("routines", "update", ("routine-id", {"title": "Block"})),
        ("routines", "delete", ("routine-id",)),
        ("routines", "copy", ({"routine_id": "routine-id"},)),
        ("routines", "move", ([],)),
        ("folders", "create", ({"title": "Block"},)),
        ("folders", "update", ({"id": 1, "title": "Block"},)),
        ("folders", "delete", (1,)),
        ("folders", "reorder", ([],)),
    ],
)
def test_management_requests_serialize_lowercase_mobile_sync_flag(resource, method, args):
    response = requests.Response()
    response.status_code = 204
    response._content = b""
    client = HevyWebClient(web_session())
    with patch("requests.Session.send", return_value=response) as send:
        getattr(getattr(client, resource), method)(*args)
    prepared = send.call_args.args[0]
    assert parse_qs(urlsplit(prepared.url).query) == {"sendSyncEventToMobileApp": ["true"]}


def test_composite_client_uses_existing_web_auth_separately_from_public_api(tmp_path):
    api_key = "fake-public-key"
    web_key = "fake-web-key"
    client = HevyAppClient(
        api_key=api_key, web_api_key=web_key, web_credentials_path=tmp_path / "absent.json"
    )
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"rpe_enabled":true}'
    response.url = "https://api.hevyapp.com/v2/user_preferences"
    with patch("requests.Session.request", return_value=response) as request:
        result = client.web.preferences.get()
    assert result.model_dump() == {"rpe_enabled": True}
    assert request.call_args.args == ("GET", "https://api.hevyapp.com/v2/user_preferences")
    assert request.call_args.kwargs["headers"]["auth-token"] == web_key
    assert request.call_args.kwargs["headers"].get("api-key") is None
