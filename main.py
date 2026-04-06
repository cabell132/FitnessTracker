"""Fitness tracker sync orchestrator — runs all platform syncs end-to-end."""

import urllib3
from sqlalchemy import create_engine

from fitness_tracker.sync import SyncDeps, SyncService

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

engine = create_engine("sqlite:///fitness_tracker.db")
sync = SyncService(SyncDeps.from_engine(engine))
sync.run()
