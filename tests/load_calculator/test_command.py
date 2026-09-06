"""JSON command behavior through the local experimental entry point."""

import json
from pathlib import Path

import pytest

from scripts.load_calculator.__main__ import main

EXAMPLE = Path("docs/research/load-calculator-example.json")


def test_example_emits_a_self_contained_review_artifact(capsys):
    assert main([str(EXAMPLE)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["experimental"] is True
    assert result["reason"] == "progress"
    assert [e["weight_kg"] for e in result["efforts"]] == [15] * 3
    assert result["request"]["history"][0]["evidence_id"] == "workout-1/item-1"


def test_output_can_be_written_to_local_artifact(tmp_path, capsys):
    path = tmp_path / "review.json"
    assert main([str(EXAMPLE), "--output", str(path)]) == 0
    assert json.loads(path.read_text())["reason"] == "progress"
    assert capsys.readouterr().out == ""


def test_schema_command_describes_the_input_contract(capsys):
    assert main(["--schema"]) == 0
    assert "equipment" in json.loads(capsys.readouterr().out)["properties"]


def test_invalid_input_exits_without_echoing_private_input(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text('{"private_note": "do-not-echo-this"}')
    with pytest.raises(SystemExit) as caught:
        main([str(path)])
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Invalid request fields" in captured.err
    assert "do-not-echo-this" not in captured.err
