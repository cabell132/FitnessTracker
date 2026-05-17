"""Fitness tracker sync orchestrator — runs all platform syncs end-to-end."""

import urllib3

from fitness_tracker.database.config import create_database_engine
from fitness_tracker.sync import SyncDeps, SyncService

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

engine = create_database_engine()
sync = SyncService(SyncDeps.from_engine(engine))
sync.run()
