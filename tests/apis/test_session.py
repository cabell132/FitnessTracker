# Tests for APISession, API error hierarchy, and session factory functions.

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fitness_tracker.apis.exceptions import APIError
from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.hevy_app.session import hevy_session
from fitness_tracker.apis.hevy_app.web_session import hevy_web_session
from fitness_tracker.apis.session import APISession
from fitness_tracker.apis.true_coach.auth import TrueCoachOAuthToken
from fitness_tracker.apis.true_coach.exceptions import TrueCoachAPIError
from fitness_tracker.apis.true_coach.session import true_coach_session


def test_should_build_url_with_leading_slash_when_given_path() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com/v1",
        headers={"api-key": "k"},
        api_name="test",
    )
    # Act
    url = session.make_url("/items")
    # Assert
    assert url == "https://test.example.com/v1/items"


def test_should_normalize_path_when_endpoint_has_no_leading_slash() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com",
        headers={},
        api_name="test",
    )
    # Act
    url = session.make_url("items")
    # Assert
    assert url == "https://test.example.com/items"


def test_should_strip_https_prefix_from_endpoint() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com",
        headers={},
        api_name="test",
    )
    # Act
    url = session.make_url("https://api.example/foo")
    # Assert
    assert url == "https://test.example.com/api.example/foo"


def test_should_append_query_string_when_query_dict_provided() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com",
        headers={},
        api_name="test",
    )
    # Act
    url = session.make_url("/x", query={"a": "1", "b": "two"})
    # Assert
    assert url.startswith("https://test.example.com/x?")
    assert "a=1" in url
    assert "b=two" in url


def test_should_rstrip_trailing_slash_on_base_url() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com/base/",
        headers={},
        api_name="test",
    )
    # Act
    url = session.make_url("r")
    # Assert
    assert url == "https://test.example.com/base/r"


def _ok_response(  # noqa: PLR0913
    status: int = 200,
    json_data: object | None = None,
    *,
    url: str = "https://test.example.com/v1/a",
    text: str = "",
) -> MagicMock:
    r = MagicMock()
    r.ok = 200 <= status < 300
    r.status_code = status
    r.url = url
    r.text = text
    r.json.return_value = {} if json_data is None else json_data
    return r


def test_should_inject_request_url_on_200_dict_body() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com/v1",
        headers={},
        api_name="test",
        error_class=HevyAppAPIError,
    )
    resp = _ok_response(json_data={"x": 1}, url="https://test.example.com/v1/workouts")
    with patch("fitness_tracker.apis.session.requests.Session") as sess_cls:
        inst = sess_cls.return_value.__enter__.return_value
        inst.request.return_value = resp
        # Act
        out = session.make_request("GET", "/workouts")
    # Assert
    assert out == {"x": 1, "request_url": "https://test.example.com/v1/workouts"}


def test_should_wrap_list_body_in_results_on_200() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com",
        headers={},
        api_name="test",
        error_class=HevyAppAPIError,
    )
    resp = _ok_response(json_data=[1, 2])
    with patch("fitness_tracker.apis.session.requests.Session") as sess_cls:
        inst = sess_cls.return_value.__enter__.return_value
        inst.request.return_value = resp
        # Act
        out = session.make_request("GET", "/list")
    # Assert
    assert out == {"results": [1, 2], "request_url": resp.url}


def test_should_return_none_on_204() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com",
        headers={},
        api_name="test",
        error_class=HevyAppAPIError,
    )
    resp = _ok_response(status=204, json_data=None)
    resp.json.side_effect = ValueError("no json")
    with patch("fitness_tracker.apis.session.requests.Session") as sess_cls:
        inst = sess_cls.return_value.__enter__.return_value
        inst.request.return_value = resp
        # Act
        out = session.make_request("DELETE", "/x")
    # Assert
    assert out is None


def test_should_return_none_on_delete_when_delete_returns_none_enabled() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com",
        headers={},
        api_name="test",
        error_class=HevyAppAPIError,
        delete_returns_none=True,
    )
    resp = _ok_response(status=200, json_data={"done": True})
    with patch("fitness_tracker.apis.session.requests.Session") as sess_cls:
        inst = sess_cls.return_value.__enter__.return_value
        inst.request.return_value = resp
        # Act
        out = session.make_request("DELETE", "/x")
    # Assert
    assert out is None


def test_should_raise_configured_error_with_status_on_http_failure() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com",
        headers={},
        api_name="test",
        error_class=HevyAppAPIError,
    )
    resp = MagicMock()
    resp.ok = False
    resp.status_code = 404
    resp.url = "https://test.example.com/missing"
    resp.text = "nope"
    with patch("fitness_tracker.apis.session.requests.Session") as sess_cls:
        inst = sess_cls.return_value.__enter__.return_value
        inst.request.return_value = resp
        # Act / Assert
        with pytest.raises(HevyAppAPIError) as ei:
            session.make_request("GET", "/missing")
    err = ei.value
    assert err.status_code == 404
    assert err.url == "https://test.example.com/missing"
    assert "nope" in str(err)


def test_should_raise_on_transport_error() -> None:
    # Arrange
    session = APISession(
        base_url="https://test.example.com",
        headers={},
        api_name="test",
        error_class=TrueCoachAPIError,
        error_label="TrueCoach API",
    )
    with patch("fitness_tracker.apis.session.requests.Session") as sess_cls:
        inst = sess_cls.return_value.__enter__.return_value
        inst.request.side_effect = ConnectionError("boom")
        # Act / Assert
        with pytest.raises(TrueCoachAPIError) as ei:
            session.make_request("GET", "/x")
    assert "boom" in str(ei.value)


def test_should_treat_hevy_app_error_as_api_error() -> None:
    # Arrange
    err = HevyAppAPIError("m", url="u", status_code=500)
    # Assert
    assert isinstance(err, APIError)


def test_should_treat_true_coach_error_as_api_error() -> None:
    # Arrange
    err = TrueCoachAPIError("m", url="u", status_code=400)
    # Assert
    assert isinstance(err, APIError)


def test_should_build_hevy_session_with_expected_base_and_header() -> None:
    # Act
    s = hevy_session(api_key="secret")
    # Assert
    assert s.make_url("/workouts") == "https://api.hevyapp.com/v1/workouts"


def test_should_build_hevy_web_session_with_expected_url() -> None:
    # Act
    s = hevy_web_session(api_key="web")
    # Assert
    assert s.make_url("/v2/foo") == "https://api.hevyapp.com/v2/foo"


def test_should_build_true_coach_session_with_bearer_header() -> None:
    # Arrange
    token = TrueCoachOAuthToken(
        {"access_token": "tok", "user_id": 1, "token_type": "Bearer"},
    )
    # Act
    s = true_coach_session(email="test@example.com", password="pass", token=token)  # noqa: S106
    # Assert
    with patch("fitness_tracker.apis.session.requests.Session") as sess_cls:
        inst = sess_cls.return_value.__enter__.return_value
        inst.request.return_value = _ok_response(json_data={})
        s.make_request("GET", "/clients")
        call_kw = inst.request.call_args.kwargs
    assert call_kw["headers"]["Authorization"] == "Bearer tok"
