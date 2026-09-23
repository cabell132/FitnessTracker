"""Health-score helpers used to derive metabolic age.

These are internal to the vesync package and not part of the public API.
"""

from __future__ import annotations

# Gender-indexed constants: (male, female)
_WS_HEIGHT_FACTOR = (100.0, 137.0)
_WS_CONSTANT = (80.0, 110.0)
_WS_FACTOR = (0.7, 0.45)
_FS_CONSTANT = (16.0, 26.0)

_HEALTH_THRESHOLDS = (50, 60, 65, 68, 70, 73, 75, 80, 85, 88, 90, 93, 95, 97, 98, 99)


def _weight_score(weight_kg: float, height_m: float, sex: int) -> int:
    """Calculate weight score (0-100).

    Args:
        weight_kg (float): Weight in kilograms.
        height_m (float): Height in metres.
        sex (int): Sex index (0=male, 1=female).

    Returns:
        int: Weight score.
    """
    res = _WS_FACTOR[sex] * (_WS_HEIGHT_FACTOR[sex] * height_m - _WS_CONSTANT[sex])
    if res <= weight_kg:
        if res * 1.3 < weight_kg:
            return 50
        return int(100 - 50 * (weight_kg - res) / (0.3 * res))
    if res * 0.7 < weight_kg:
        return int(100 - 50 * (res - weight_kg) / (0.3 * res))
    for x in range(6):
        if res * x / 10 > weight_kg:
            return x * 10
    return 0


def _fat_score(bfp: float, sex: int) -> int:
    """Calculate fat score (0-100).

    Args:
        bfp (float): Body fat percentage.
        sex (int): Sex index (0=male, 1=female).

    Returns:
        int: Fat score.
    """
    c = _FS_CONSTANT[sex]
    if c < bfp:
        if bfp >= 45:
            return 50
        return int(100 - 50 * (bfp - c) / (45 - c))
    return int(100 - 50 * (c - bfp) / (c - 5))


def _bmi_score(bmi: float) -> int:
    """Calculate BMI score.

    Args:
        bmi (float): Body mass index.

    Returns:
        int: BMI score.
    """
    if bmi >= 22:
        if bmi >= 35:
            return 50
        return int(100 - 3.85 * (bmi - 22))
    if bmi >= 15:
        return int(100 - 3.85 * (22 - bmi))
    if bmi >= 10:
        return 40
    if bmi >= 5:
        return 30
    return 20


def metabolic_age(  # noqa: PLR0913 - formula inputs are independent measurements
    weight_kg: float, height_cm: float, bfp: float, bmi: float, age: int, sex: int
) -> int:
    """Calculate metabolic age via health-score lookup.

    Args:
        weight_kg (float): Weight in kilograms.
        height_cm (float): Height in centimetres.
        bfp (float): Body fat percentage.
        bmi (float): Body mass index.
        age (int): Chronological age in years.
        sex (int): Sex index (0=male, 1=female).

    Returns:
        int: Metabolic age (minimum 18).
    """
    height_m = height_cm / 100.0
    ws = _weight_score(weight_kg, height_m, sex)
    fs = _fat_score(bfp, sex)
    bs = _bmi_score(bmi)
    health = (ws + fs + bs) // 3

    adjustment = 0
    for i, threshold in enumerate(_HEALTH_THRESHOLDS):
        if health < threshold:
            adjustment = i
            break
    else:
        adjustment = len(_HEALTH_THRESHOLDS)

    return max(18, age + 8 - adjustment)
