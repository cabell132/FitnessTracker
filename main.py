"""Fitness tracker sync orchestrator — runs all platform syncs end-to-end."""

import urllib3
from sqlalchemy import create_engine

from fitness_tracker.config import Config
from fitness_tracker.sync import SyncDeps, SyncService

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

cfg = Config.from_env()
engine = create_engine(cfg.database_url)
sync = SyncService(SyncDeps.from_config(engine, cfg))
sync.run()
