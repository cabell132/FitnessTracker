"""Import the account owner's VeSync scale measurements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite

from fitness_tracker.apis.vesync import VeSyncClient
from fitness_tracker.apis.vesync.body_composition import calculate
from fitness_tracker.apis.vesync.models.weight import WeightMeasurement
from fitness_tracker.database import Store
from fitness_tracker.database.models.vesync import VeSyncWeighIn

PAGE_SIZE = 100


@dataclass(frozen=True)
class VeSyncImportResult:
    """Counts from a complete scan of the scale's history."""

    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    excluded: int = 0
    invalid: int = 0


def sync_vesync_weigh_ins(  # noqa: PLR0915 - scan counters and pagination belong together
    store: Store, client: VeSyncClient, *, athlete_mode: bool = False
) -> VeSyncImportResult:
    """Scan V2 history and upsert only readings from the primary profile.

    The account owner's readings have no ``subUserID``. Other profiles are
    excluded before anything is written to the database.

    Args:
        store (Store): Database for imported readings.
        client (VeSyncClient): Scale history source.
        athlete_mode (bool): Apply the athlete body-fat formula.

    Returns:
        VeSyncImportResult: Counts from the completed history scan.

    Raises:
        RuntimeError: If the device ID is missing or pagination repeats or exceeds the limit.
    """
    device = client.find_scale()
    if not device.cid:
        msg = "VeSync scale is missing a device CID"
        raise RuntimeError(msg)
    scanned = inserted = updated = excluded = invalid = 0
    previous_page: tuple[tuple[int, float, str | None], ...] | None = None

    for page_number in range(1, 10001):
        measurements = client.weight.get_weight_data_v2(
            device, page=page_number, page_size=PAGE_SIZE
        ).measurements
        if not measurements:
            break

        page_rows, page_excluded, page_invalid = _prepare_rows(
            device.cid, measurements, athlete_mode=athlete_mode
        )
        scanned += len(measurements)
        excluded += page_excluded
        invalid += page_invalid
        page_signature = tuple(
            (item.timestamp, item.weight_kg, item.sub_user_id) for item in measurements
        )
        if page_signature == previous_page and len(measurements) == PAGE_SIZE:
            msg = "VeSync repeated a full page while scanning weight history"
            raise RuntimeError(msg)
        previous_page = page_signature

        page_inserted, page_updated = _upsert_rows(store, page_rows)
        inserted += page_inserted
        updated += page_updated

        if len(measurements) < PAGE_SIZE:
            break
    else:
        msg = "VeSync weight history exceeded 10,000 pages"
        raise RuntimeError(msg)

    return VeSyncImportResult(scanned, inserted, updated, excluded, invalid)


def _prepare_rows(
    device_cid: str, measurements: list[WeightMeasurement], *, athlete_mode: bool
) -> tuple[dict[str, VeSyncWeighIn], int, int]:
    rows: dict[str, VeSyncWeighIn] = {}
    excluded = invalid = 0
    for measurement in measurements:
        if measurement.sub_user_id is not None:
            excluded += 1
            continue
        row = _as_row(device_cid, measurement, athlete_mode=athlete_mode)
        if row is None:
            invalid += 1
            continue
        rows[row.source_key] = row
    return rows, excluded, invalid


def _upsert_rows(store: Store, rows: dict[str, VeSyncWeighIn]) -> tuple[int, int]:
    if not rows:
        return 0, 0
    inserted = updated = 0
    with store.unit_of_work() as tx:
        existing = {
            row.source_key: row
            for row in tx.session.query(VeSyncWeighIn)
            .filter(VeSyncWeighIn.source_key.in_(rows))
            .all()
        }
        for key, incoming in rows.items():
            current = existing.get(key)
            if current is None:
                tx.add(incoming)
                inserted += 1
            elif _refresh(current, incoming):
                updated += 1
    return inserted, updated


def _as_row(
    device_cid: str, measurement: WeightMeasurement, *, athlete_mode: bool = False
) -> VeSyncWeighIn | None:
    if (
        measurement.timestamp <= 0
        or not isfinite(measurement.weight_kg)
        or measurement.weight_kg <= 0
    ):
        return None
    weight_g = round(measurement.weight_kg * 1000)
    if weight_g <= 0:
        return None
    source = f"{device_cid}:{measurement.timestamp}:{weight_g}:{measurement.is_manual_input}"
    composition = calculate(measurement, athlete=athlete_mode)
    return VeSyncWeighIn(
        source_key=sha256(source.encode()).hexdigest(),
        measured_at=datetime.fromtimestamp(measurement.timestamp, tz=UTC),
        weight_g=weight_g,
        impedance_ohms=measurement.impedance if measurement.impedance > 0 else None,
        body_fat_pct=composition.body_fat_pct if composition is not None else None,
        is_manual_input=measurement.is_manual_input,
    )


def _refresh(current: VeSyncWeighIn, incoming: VeSyncWeighIn) -> bool:
    changed = False
    for field in ("impedance_ohms", "body_fat_pct"):
        value = getattr(incoming, field)
        if value != getattr(current, field):
            setattr(current, field, value)
            changed = True
    return changed
