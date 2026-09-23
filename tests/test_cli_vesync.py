"""VeSync and True Coach updates after applying workout results."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fitness_tracker import cli


def test_result_apply_syncs_athlete_weight_to_true_coach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VESYNC_EMAIL", "example@example.invalid")
    monkeypatch.setenv("VESYNC_PASSWORD", "unused")
    monkeypatch.setenv("VESYNC_ATHLETE_MODE", "true")
    scale = MagicMock()
    true_coach = MagicMock()
    store = MagicMock()
    seen: dict[str, object] = {}

    monkeypatch.setattr(cli.VeSyncClient, "from_env", lambda: scale)
    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: true_coach)

    def import_scale(actual_store, actual_scale, *, athlete_mode):
        seen["scale_import"] = (actual_store, actual_scale, athlete_mode)
        return SimpleNamespace(inserted=1, updated=0)

    class FakeWeightSync:
        def __init__(self, actual_store, target):
            seen["weight_sync"] = (actual_store, target)

        def sync_vesync_weights(self):
            return 1

    monkeypatch.setattr(cli, "sync_vesync_weigh_ins", import_scale)
    monkeypatch.setattr(cli, "TrackerToTrueCoachSyncronizer", FakeWeightSync)

    assert cli._sync_scale_after_result_apply(store) == 0
    assert seen["scale_import"] == (store, scale, True)
    assert seen["weight_sync"] == (store, true_coach)
