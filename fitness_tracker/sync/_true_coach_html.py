"""Consolidated True Coach HTML parsing — single source replacing three identical utils.py files.

Every syncer that needs workout order, superset indexing, or notes extraction
imports from here instead of maintaining its own copy.
"""

import re
from typing import cast

import pandas as pd
from bs4 import BeautifulSoup

from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestSet

PRESCRIBED_SETS_PATTERN = re.compile(
    r"(?P<count>\d+)\s*[xX]\s*"
    r"(?P<reps>\d+(?:[ \t]*-[ \t]*\d+)?(?:\s*[+>]\s*\d+(?:[ \t]*-[ \t]*\d+)?)*)"
    r"(?!\s*(?:s|sec|secs|second|seconds)\b)"
    r"(?P<suffix>[^\n]*)",
    re.IGNORECASE,
)
DURATION_SETS_PATTERN = re.compile(
    r"(?P<count>\d+)\s*[xX]\s*"
    r"(?P<seconds>\d+(?:[ \t]*-[ \t]*\d+)?)\s*"
    r"(?:s|sec|secs|second|seconds)\b",
    re.IGNORECASE,
)
LENGTH_SETS_PATTERN = re.compile(
    r"(?P<count>\d+)\s*[xX]\s*(?P<lengths>\d+)\s*L\b",
    re.IGNORECASE,
)
DISTANCE_SETS_PATTERN = re.compile(
    r"(?P<count>\d+)\s*[xX]\s*(?P<distance>\d+)\s*(?:m|meters?)\b",
    re.IGNORECASE,
)
DROPSET_REP_SEPARATOR_PATTERN = re.compile(r"\s*[+>]\s*")
LOAD_PATTERN = re.compile(
    r"@\s*(?P<load>\d+(?:\.\d+)?)(?:\s*kg\b|(?!\s*[A-Za-z]))",
    re.IGNORECASE,
)
BODYWEIGHT_LOAD_PATTERN = re.compile(r"@\s*BW\b", re.IGNORECASE)


def parse_workout_order(description: str) -> dict[int, dict[str, str | int | None]]:
    """Parse exercise order and superset markers from True Coach HTML.

    Args:
        description (str): Raw HTML ``short_description`` from True Coach.

    Returns:
        dict[int, dict[str, str | int | None]]: 1-based step index to exercise metadata.

    Raises:
        ValueError: If the HTML lacks expected workout structure.
    """
    soup = BeautifulSoup(description, "html.parser")

    name_and_info = soup.find("p", class_="name-and-info")
    if name_and_info is None:
        msg = "No workout elements found"
        raise ValueError(msg)

    exercises: list[str] = [
        line.strip() for line in name_and_info.decode_contents().split("<br/>") if line.strip()
    ]

    exercises = [BeautifulSoup(line, "html.parser").get_text().strip() for line in exercises]

    order: dict[int, dict[str, str | int | None]] = {}
    for i, element in enumerate(exercises, start=1):
        key, value = element.split(") ")
        if key[-1].isdigit():
            numbers = int("".join(c for c in key if c.isdigit()))
            letters = "".join(c for c in key if not c.isdigit())
            order[i] = {
                "exercise_name": value.strip(),
                "is_superset": True,
                "superset_group": letters,
                "superset_order": numbers,
                "identifier": key,
            }
        else:
            order[i] = {
                "exercise_name": value.strip(),
                "is_superset": False,
                "superset_group": None,
                "superset_order": None,
                "identifier": key,
            }

    return order


def build_superset_index(order: dict[int, dict[str, str | int | None]]) -> dict[str, int] | None:
    """Build superset group labels to Hevy superset_id indices.

    Args:
        order (dict[int, dict[str, str | int | None]]): Output of :func:`parse_workout_order`.

    Returns:
        dict[str, int] | None: Group label to superset index, or ``None`` when empty.
    """
    df = pd.DataFrame.from_dict(order, orient="index")
    if df.empty:
        return None
    subset = df.loc[df["is_superset"].astype(bool)]
    if subset.empty:
        return None
    grouped = subset.groupby("superset_group", as_index=False)["superset_order"].max()
    grouped = grouped.reset_index(drop=True).assign(row_index=lambda d: d.index)
    out = grouped.set_index("superset_group")["row_index"].to_dict()
    return cast(dict[str, int], out)


def extract_notes(description: str) -> str:
    """Extract plain-text notes from True Coach workout HTML.

    Args:
        description (str): Raw HTML description.

    Returns:
        str: Newline-joined text from the name block, or empty string.
    """
    soup = BeautifulSoup(description, "html.parser")

    workout_elements = soup.find("p", class_="name-and-info")
    if workout_elements is None:
        return ""

    return "\n".join(workout_elements.stripped_strings)


def fallback_sets(description: str) -> list[PostRoutinesRequestSet]:
    """Fallback routine sets when LLM parsing returns nothing.

    Args:
        description (str): Exercise info HTML or text.

    Returns:
        list[PostRoutinesRequestSet]: Parsed deterministic rows, or one default set row.
    """
    if sets := parse_prescribed_sets(description):
        return sets

    return [
        PostRoutinesRequestSet(
            type="normal",
            duration_seconds=60,
        )
    ]


def parse_prescribed_sets(description: str) -> list[PostRoutinesRequestSet]:
    """Parse safe deterministic Coach set prescriptions from free text.

    Args:
        description (str): Exercise info HTML or text.

    Returns:
        list[PostRoutinesRequestSet]: Parsed Hevy set rows, or an empty list.
    """
    duration_match = DURATION_SETS_PATTERN.search(description)
    length_match = LENGTH_SETS_PATTERN.search(description)
    distance_match = DISTANCE_SETS_PATTERN.search(description)
    rep_match = PRESCRIBED_SETS_PATTERN.search(description)
    if duration_match and (rep_match is None or duration_match.start() <= rep_match.start()):
        return [
            set_
            for match in DURATION_SETS_PATTERN.finditer(description)
            for set_ in _duration_sets(match)
        ]
    if length_match and (rep_match is None or length_match.start() <= rep_match.start()):
        return _length_sets(length_match)
    if distance_match and (rep_match is None or distance_match.start() <= rep_match.start()):
        return _distance_sets(distance_match)

    match = rep_match
    if not match:
        return []

    set_count = int(match.group("count"))
    rep_parts = DROPSET_REP_SEPARATOR_PATTERN.split(match.group("reps"))
    rep_targets = [_parse_rep_target(part) for part in rep_parts]
    load = _parse_optional_load(match.group("suffix"))

    sets: list[PostRoutinesRequestSet] = []
    for _ in range(set_count):
        for index, rep_target in enumerate(rep_targets):
            set_type = "normal" if index == 0 else "dropset"
            sets.append(PostRoutinesRequestSet(type=set_type, reps=rep_target, weight_kg=load))

    return sets


def _duration_sets(match: re.Match[str]) -> list[PostRoutinesRequestSet]:
    set_count = int(match.group("count"))
    duration_seconds = _parse_rep_target(match.group("seconds"))
    return [
        PostRoutinesRequestSet(type="normal", duration_seconds=duration_seconds)
        for _ in range(set_count)
    ]


def _length_sets(match: re.Match[str]) -> list[PostRoutinesRequestSet]:
    set_count = int(match.group("count"))
    distance_meters = int(match.group("lengths")) * 10
    return [
        PostRoutinesRequestSet(type="normal", distance_meters=distance_meters)
        for _ in range(set_count)
    ]


def _distance_sets(match: re.Match[str]) -> list[PostRoutinesRequestSet]:
    set_count = int(match.group("count"))
    distance_meters = int(match.group("distance"))
    return [
        PostRoutinesRequestSet(type="normal", distance_meters=distance_meters)
        for _ in range(set_count)
    ]


def _parse_rep_target(value: str) -> int:
    bounds = [int(part.strip()) for part in value.split("-")]
    return max(bounds)


def _parse_optional_load(value: str) -> float | None:
    if BODYWEIGHT_LOAD_PATTERN.search(value):
        return 0.0
    match = LOAD_PATTERN.search(value)
    if match is None:
        return None
    return float(match.group("load"))
