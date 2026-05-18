"""Transaction repository container boundary tests."""

from fitness_tracker.database.store import Store
from fitness_tracker.database.tx import (
    AppleHealthRepo,
    CrossDomainOps,
    HevyRepo,
    SessionOps,
    TrackerRepo,
    TrueCoachRepo,
    Tx,
)


def test_store_yields_tx_repository_container(store: Store) -> None:
    """Store.unit_of_work exposes domain-scoped repository protocols."""
    with store.unit_of_work() as tx:
        assert isinstance(tx, Tx)
        assert isinstance(tx.hevy, HevyRepo)
        assert isinstance(tx.true_coach, TrueCoachRepo)
        assert isinstance(tx.tracker, TrackerRepo)
        assert isinstance(tx.apple_health, AppleHealthRepo)
        assert isinstance(tx.cross_domain, CrossDomainOps)
        assert isinstance(tx.session, SessionOps)
