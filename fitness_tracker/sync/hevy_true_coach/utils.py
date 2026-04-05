"""Format Hevy set logs into True Coach workout item result text."""

from collections.abc import Callable

from fitness_tracker.apis.hevy_app.types import Set

SetFormatter = Callable[[list[Set]], str]


def format_duration(seconds: int) -> str:
    """Format a duration in seconds as hours, minutes, and seconds.

    Args:
        seconds (int): Elapsed seconds (non-negative).

    Returns:
        str: Human-readable duration pieces joined by spaces.
    """
    hours = seconds // 3600
    remaining_seconds = seconds % 3600
    minutes = remaining_seconds // 60
    remaining_seconds = remaining_seconds % 60

    formatted_duration: list[str] = []
    if hours > 0:
        formatted_duration.append(f"{hours} hr")
    if minutes > 0:
        formatted_duration.append(f"{minutes} min")
    if remaining_seconds > 0 or not formatted_duration:
        formatted_duration.append(f"{remaining_seconds} sec")

    return " ".join(formatted_duration)


def format_reps_only_result(sets: list[Set]) -> str:
    """Format rep-only sets as newline-separated lines.

    Args:
        sets (list[Set]): Hevy sets containing rep counts.

    Returns:
        str: Lines suitable for True Coach ``result`` text.
    """
    result = ""
    for set_ in sets:
        if set_.type == "dropset":
            result = result[:-1]
            result += f" > {set_.reps}\n"
        else:
            result += f"{set_.reps} reps\n"
    return result


def format_distance_duration_result(sets: list[Set]) -> str:
    """Format distance and duration sets with pace per line.

    Args:
        sets (list[Set]): Sets with distance and duration populated.

    Returns:
        str: One line per set with meters, duration, and pace.
    """
    result = ""
    for set_ in sets:
        dist = set_.distance_meters or 0
        dur = set_.duration_seconds or 0
        pace = calculate_pace(dist, dur)
        result += f"{dist}m in {format_duration(dur)} @{pace}\n"
    return result


def calculate_pace(distance_meters: int, duration_seconds: int) -> str:
    """Compute pace in minutes per kilometer.

    Args:
        distance_meters (int): Distance in meters.
        duration_seconds (int): Elapsed seconds.

    Returns:
        str: Pace as ``m:ss.s min/km`` or ``0.00 min/km`` when distance is zero.
    """
    if distance_meters == 0:
        return "0.00 min/km"
    distance_km = distance_meters / 1000
    pace_seconds = duration_seconds / distance_km

    minutes = int(pace_seconds // 60)
    seconds = round(pace_seconds % 60, 1)

    return f"{minutes}:{seconds:04.1f} min/km"


def format_weight_reps_result(sets: list[Set]) -> str:
    """Format weight and rep sets, including dropsets and warmups.

    Args:
        sets (list[Set]): Hevy strength sets.

    Returns:
        str: Human-readable lines per set.
    """
    result = ""
    for set_ in sets:
        if set_.type == "dropset":
            result = result[:-1]
            result += f" > {set_.reps} x {set_.weight_kg} kg\n"
        elif set_.type == "warmup":
            result += f"Warmup Set: {set_.reps} x {set_.weight_kg} kg\n"
        else:
            result += f"{set_.reps} x {set_.weight_kg} kg\n"
    return result


def format_bodyweight_assisted_result(sets: list[Set]) -> str:
    """Format bodyweight-assisted sets using the weight/rep formatter.

    Args:
        sets (list[Set]): Hevy sets for assisted movements.

    Returns:
        str: Formatted lines per set.
    """
    return format_weight_reps_result(sets)


def format_bodyweight_weighted_result(sets: list[Set]) -> str:
    """Format bodyweight and added-weight sets.

    Args:
        sets (list[Set]): Hevy sets that may omit weight.

    Returns:
        str: Reps-only or weight x reps lines.
    """
    result = ""
    for set_ in sets:
        w = set_.weight_kg or 0
        if w > 0:
            result += f"{set_.reps} x {set_.weight_kg} kg\n"
        else:
            result += f"{set_.reps} reps\n"
    return result


def format_duration_result(sets: list[Set]) -> str:
    """Format duration-only sets.

    Args:
        sets (list[Set]): Sets with ``duration_seconds`` set.

    Returns:
        str: One formatted duration per line.
    """
    result = ""
    for set_ in sets:
        sec = set_.duration_seconds or 0
        result += f"{format_duration(sec)}\n"
    return result


def format_weight_duration_result(sets: list[Set]) -> str:
    """Format combined weight and duration sets.

    Args:
        sets (list[Set]): Sets with weight and duration.

    Returns:
        str: One line per set describing load and time held.
    """
    result = ""
    for set_ in sets:
        sec = set_.duration_seconds or 0
        kg = set_.weight_kg or 0
        result += f"{kg} kg for {format_duration(sec)}\n"
    return result


def format_short_distance_weight_result(sets: list[Set]) -> str:
    """Format short carries or sled pushes with weight and distance.

    Args:
        sets (list[Set]): Sets with both distance and weight.

    Returns:
        str: One line per set.
    """
    result = ""
    for set_ in sets:
        result += f"{set_.weight_kg} kg for {set_.distance_meters}m\n"
    return result


mapping: dict[str, SetFormatter] = {
    "reps_only": format_reps_only_result,
    "bodyweight_assisted": format_bodyweight_assisted_result,
    "short_distance_weight": format_short_distance_weight_result,
    "bodyweight_weighted": format_bodyweight_weighted_result,
    "duration": format_duration_result,
    "weight_duration": format_weight_duration_result,
    "distance_duration": format_distance_duration_result,
    "weight_reps": format_weight_reps_result,
}
