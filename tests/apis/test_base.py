from pydantic import BaseModel

from fitness_tracker.apis.base import parse_response


class ExampleResponse(BaseModel):
    id: int
    name: str


def test_parse_response_none() -> None:
    assert parse_response(None, ExampleResponse) is None


def test_parse_response_dict() -> None:
    parsed = parse_response({"id": 1, "name": "example"}, ExampleResponse)

    assert parsed == ExampleResponse(id=1, name="example")


def test_parse_response_empty_dict() -> None:
    assert parse_response({}, ExampleResponse) is None
