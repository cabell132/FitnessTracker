"""Parse True Coach HTML for Tracker → Hevy workout posts."""

from typing import cast

import pandas as pd
from bs4 import BeautifulSoup

from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestSet


def get_workout_order(description: str) -> dict[int, dict[str, str | int | None]]:
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


def get_superset_index(order: dict[int, dict[str, str | int | None]]) -> dict[str, int] | None:
    """Build superset group labels to Hevy superset_id indices.

    Args:
        order (dict[int, dict[str, str | int | None]]): Output of :func:`get_workout_order`.

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


def create_notes(description: str) -> str:
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


def parse_sets(description: str) -> list[PostRoutinesRequestSet]:
    """Fallback sets when LLM parsing returns nothing.

    Args:
        description (str): Exercise info (unused placeholder).

    Returns:
        list[PostRoutinesRequestSet]: A single default set row.
    """
    return [
        PostRoutinesRequestSet(
            type="normal",
            duration_seconds=60,
        )
    ]
