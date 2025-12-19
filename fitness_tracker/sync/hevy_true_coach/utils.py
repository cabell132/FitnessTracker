from fitness_tracker.apis.hevy_app.types import Set


def format_duration(seconds: int):
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
    result = ""
    for set_ in sets:
        if set_.type == "dropset":
            # remove the newline character from the previous line
            result = result[:-1]
            result += f" > {set_.reps}\n"
        else:
            result += f"{set_.reps} reps\n"
    return result


def format_distance_duration_result(sets: list[Set]) -> str:
    """Formats a list of sets into a string that details the distance, duration, and pace for each set.

    Args:
        sets (list[Set]): A list of Set objects, where each Set contains distance in meters and duration in seconds.

    Returns:
        str: A formatted string where each line represents a set with its distance, duration, and pace.
    """  # noqa: W505
    result = ""
    for set_ in sets:
        pace = calculate_pace(set_.distance_meters, set_.duration_seconds)
        result += (
            f"{set_.distance_meters}m in {format_duration(seconds=set_.duration_seconds)} @{pace}\n"
        )
    return result


def calculate_pace(distance_meters: int, duration_seconds: int) -> str:
    """Calculate the pace in minutes per kilometer.

    Args:
        distance_meters (int): The distance in meters.
        duration_seconds (int): The duration in seconds.

    Returns:
        str: The pace in minutes per kilometer.
    """
    if distance_meters == 0:
        return "0.00 min/km"
    distance_km = distance_meters / 1000
    pace_seconds = duration_seconds / distance_km  # Total pace in seconds per km

    minutes = int(pace_seconds // 60)
    seconds = round(pace_seconds % 60, 1)

    return f"{minutes}:{seconds:04.1f} min/km"


def format_weight_reps_result(sets: list[Set]) -> str:
    """Formats a list of sets into a string representation of weight and reps.

    Args:
        sets (list[Set]): A list of Set objects, where each Set contains information
                          about the type of set (e.g., "dropset", "warmup"), the number
                          of reps, and the weight in kilograms.

    Returns:
        str: A formatted string representing the weight and reps for each set.
             Dropsets are indicated with a ">" symbol, warmup sets are prefixed with
             "Warmup Set:", and regular sets are formatted as "reps x weight kg".
    """
    result = ""
    for set_ in sets:
        if set_.type == "dropset":
            # remove the newline character from the previous line
            result = result[:-1]
            result += f" > {set_.reps} x {set_.weight_kg} kg\n"
        elif set_.type == "warmup":
            result += f"Warmup Set: {set_.reps} x {set_.weight_kg} kg\n"
        else:
            result += f"{set_.reps} x {set_.weight_kg} kg\n"
    return result


def format_bodyweight_assisted_result(sets: list[Set]) -> str:
    """Formats a list of sets into a string representation of bodyweight-assisted exercises.

    Args:
        sets (list[Set]): A list of Set objects, where each Set contains information
                          about the number of reps and the weight in kilograms.

    Returns:
        str: A formatted string representing the weight and reps for each set.
             The weight is formatted as a percentage of bodyweight.
    """
    return format_weight_reps_result(sets)


def format_bodyweight_weighted_result(sets: list[Set]) -> str:
    """Formats a list of sets into a string representation of bodyweight and weighted exercises.

    Args:
        sets (list[Set]): A list of Set objects, where each Set contains information
                          about the number of reps, the weight in kilograms, and the
                          weight as a percentage of bodyweight.

    Returns:
        str: A formatted string representing the weight and reps for each set.
             The weight is formatted as a percentage of bodyweight.
    """
    result = ""
    for set_ in sets:
        if set_.weight_kg > 0:  # type: ignore
            result += f"{set_.reps} x {set_.weight_kg} kg\n"
        else:
            result += f"{set_.reps} reps\n"
    return result


def format_duration_result(sets: list[Set]) -> str:
    """Formats a list of sets into a string representation of duration exercises.

    Args:
        sets (list[Set]): A list of Set objects, where each Set contains information
                          about the number of reps and the duration in seconds.

    Returns:
        str: A formatted string representing the duration for each set.
    """
    result = ""
    for set_ in sets:
        result += f"{format_duration(seconds=set_.duration_seconds)}\n"
    return result


def format_weight_duration_result(sets: list[Set]) -> str:
    """Formats a list of sets into a string representation of weight and duration exercises.

    Args:
        sets (list[Set]): A list of Set objects, where each Set contains information
                          about the number of reps, the weight in kilograms, and the
                          duration in seconds.

    Returns:
        str: A formatted string representing the weight and duration for each set.
    """
    result = ""
    for set_ in sets:
        result += f"{set_.weight_kg} kg for {format_duration(seconds=set_.duration_seconds)}\n"
    return result


def format_short_distance_weight_result(sets: list[Set]) -> str:
    """Formats a list of sets into a string representation of short distance and weight exercises.

    Args:
        sets (list[Set]): A list of Set objects, where each Set contains information
                          about the number of reps, the distance in meters, and the
                          weight in kilograms.

    Returns:
        str: A formatted string representing the distance, weight, and reps for each set.
    """
    result = ""
    for set_ in sets:
        result += f"{set_.weight_kg} kg for {set_.distance_meters}m\n"
    return result


mapping = {
    "reps_only": format_reps_only_result,
    "bodyweight_assisted": format_bodyweight_assisted_result,
    "short_distance_weight": format_short_distance_weight_result,
    "bodyweight_weighted": format_bodyweight_weighted_result,
    "duration": format_duration_result,
    "weight_duration": format_weight_duration_result,
    "distance_duration": format_distance_duration_result,
    "weight_reps": format_weight_reps_result,
}
