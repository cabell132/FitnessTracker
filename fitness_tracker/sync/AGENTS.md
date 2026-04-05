# Sync Package - Agent Guidelines

> Bidirectional synchronization logic between fitness platforms

## Package Identity

- **Purpose**: Orchestrate data sync between Hevy App, True Coach, Apple Health, and internal tracker
- **Tech**: SQLAlchemy sessions, LLM for fuzzy matching, raw SQL for bulk operations
- **Pattern**: Source → Transformer → Target with event-driven updates

## Setup & Run

```bash
# Sync is triggered from main.py
python main.py

# Requires all API tokens and database to be configured
```

## Patterns & Conventions

### Sync Direction Naming

Each sync module follows `{source}_{target}/` naming:

| Module | Direction |
|--------|-----------|
| `hevy_tracker/` | Hevy App → Internal Tracker |
| `tracker_hevy/` | Internal Tracker → Hevy App |
| `true_coach_tracker/` | True Coach → Internal Tracker |
| `tracker_true_coach/` | Internal Tracker → True Coach |
| `hevy_true_coach/` | Hevy App → True Coach |
| `true_coach_hevy/` | True Coach → Hevy App |
| `apple_health_tracker/` | Apple Health → Internal Tracker |

### Synchronizer Structure

Each sync module contains:
- `sync.py` - Main synchronizer class with sync methods
- `utils.py` - Helper functions for data transformation

### Main Orchestrator

The `Syncronizer` class in `sync.py` composes all sync modules:

```python
# See sync/sync.py
class Syncronizer:
    def __init__(self, engine: Engine) -> None:
        self._database = Database(engine)
        self._hevy_app = HevyAppClient()
        self._true_coach = TrueCoachClient()
        self._llm = FitnessLLM("gpt-4o-mini-2024-07-18")
        
        self.hevy_to_tracker = HevyToFitnessTrackerSyncronizer(...)
        self.true_coach_to_hevy = TrueCoachToHevySyncronizer(...)
```

### Sync Method Pattern

- ✅ **DO**: Accept `session: Session` parameter for database operations
- ✅ **DO**: Use event-driven sync with `UpdatedWorkout | DeletedWorkout` types
- ✅ **DO**: Commit after each logical operation
- ✅ **DO**: Use LLM for fuzzy matching when exact IDs unavailable

```python
# See hevy_tracker/sync.py for full pattern
def sync_workouts(self, since: datetime) -> list[UpdatedWorkout | DeletedWorkout]:
    res = self._source.workouts.get_workout_events(since=since)
    self.sync_events(res.events[::-1])
    return res.events[::-1]

def update_workout(self, session: Session, workout: UpdatedWorkout) -> None:
    self._database.hevy_app.add_workout(session, workout.workout)
    # ... link and sync related entities
    session.commit()
```

### Linking Pattern

Workouts and exercises are linked via embedded IDs or LLM matching:

```python
# ID embedded in title (see hevy_tracker/sync.py)
true_coach_id = workout.title.split("\n")[-1]

# LLM-based linking for workout items
link_list = self._llm.link_workout_items(hevy_items=hevy_items, true_coach_items=true_coach_items)
```

## Touch Points / Key Files

| File | Purpose |
|------|---------|
| `sync.py` | Main `Syncronizer` class composing all modules |
| `base.py` | Base class (currently empty) |
| `hevy_tracker/sync.py` | Hevy → Tracker sync with full linking logic |
| `true_coach_hevy/sync.py` | True Coach → Hevy routine creation |
| `apple_health_tracker/sync.py` | Apple Health data import |

## JIT Index Hints

```bash
# Find all sync classes
rg -n "class.*Syncronizer" fitness_tracker/sync

# Find sync methods
rg -n "def sync" fitness_tracker/sync

# Find update methods
rg -n "def (update|insert|delete)_" fitness_tracker/sync

# Find linking logic
rg -n "def link" fitness_tracker/sync

# Find SQL script usage
rg -n "Path.*SQL" fitness_tracker/sync
```

## Common Gotchas

- Sync order matters: Must sync to tracker before syncing to other platforms
- `hevy_last_sync.txt` stores last sync timestamp - used for incremental sync
- LLM calls (`_llm.link_workout_items()`) can be slow - used for fuzzy matching
- Raw SQL scripts in `database/SQL/` are used for complex bulk operations
- Always reverse event lists (`::-1`) to process oldest first

## Pre-PR Checks

```bash
uv run ruff check fitness_tracker/sync && uv run ty check fitness_tracker/sync
```
