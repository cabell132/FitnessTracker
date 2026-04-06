"""Parse True Coach HTML for tracker-side helpers (shared workout-order shape).

Re-exports from :mod:`fitness_tracker.sync._true_coach_html` so existing
``from fitness_tracker.sync.tracker_true_coach import utils`` call sites keep working.
"""

from fitness_tracker.sync._true_coach_html import (
    build_superset_index as get_superset_index,
    extract_notes as create_notes,
    fallback_sets as parse_sets,
    parse_workout_order as get_workout_order,
)

__all__ = ["create_notes", "get_superset_index", "get_workout_order", "parse_sets"]
