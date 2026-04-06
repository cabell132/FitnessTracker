# Database Package - Agent Guidelines

> SQLAlchemy-based database layer with Store + UnitOfWork pattern

## Package Identity

- **Purpose**: Data persistence layer for fitness data across all platforms
- **Tech**: SQLAlchemy 1.4, SQLite, Alembic migrations
- **Pattern**: Models → UnitOfWork (domain mixins) → Store

## Setup & Run

```bash
# Initialize database (creates tables)
python -c "from fitness_tracker.database import Store; from sqlalchemy import create_engine; Store(create_engine('sqlite:///fitness_tracker.db')).init_db()"

# Run migrations
alembic upgrade head

# Create new migration after model changes
alembic revision --autogenerate -m "description"
```

## Patterns & Conventions

### Layer Architecture

```
store.py (Store class — factory, entry point)
    └── uow/              → UnitOfWork with domain mixins
        ├── base.py        → CrudMixin: generic CRUD + SQL execution
        ├── hevy.py        → HevyMixin: Hevy App persistence
        ├── true_coach.py  → TrueCoachMixin: True Coach persistence
        ├── tracker.py     → TrackerMixin: canonical tracker ops
        ├── apple_health.py→ AppleHealthMixin: Apple Health imports
        ├── sql_ops.py     → SqlOpsMixin: cross-schema SQL wrappers
        ├── errors.py      → Domain-specific exceptions
        └── unit_of_work.py→ UnitOfWork composing all mixins
    └── models/            → SQLAlchemy ORM models
        └── base.py        → BaseModel with common methods
    └── SQL/               → Raw SQL scripts for complex queries
```

### Store Usage

- ✅ **DO**: Use `Store(engine)` as the single construction point
- ✅ **DO**: Use `with store.unit_of_work() as uow:` for all mutations
- ✅ **DO**: Use `store.query_one()` / `store.query_all()` for read-only queries
- ❌ **DON'T**: Access the session directly; use UnitOfWork methods

```python
store = Store(engine)
with store.unit_of_work() as uow:
    uow.hevy_add_workout(workout)
    uow.tracker_add_exercise(exercise)
# auto-commits on clean exit; auto-rolls back on exception
```

### UnitOfWork Domain Methods

Each domain has prefixed methods:
- `hevy_*` — Hevy App operations
- `tc_*` — True Coach operations
- `tracker_*` — Canonical tracker operations
- `ah_*` — Apple Health operations
- SQL ops — `link_hevy_tracker_workout_items()`, `insert_apple_health_metrics()`, etc.

### Model Definition

- ✅ **DO**: Inherit from `BaseModel` in `models/base.py`
- ✅ **DO**: Use `__tablename__: str = __qualname__` for table name
- ✅ **DO**: Define relationships with proper `Mapped[]` type hints
- ✅ **DO**: Use `TYPE_CHECKING` for circular import relationships

### Transaction Management

- ✅ **DO**: Use `uow.flush()` when you need auto-generated IDs mid-transaction
- ✅ **DO**: Let the UoW auto-commit on clean context exit
- ❌ **DON'T**: Call `uow.commit()` manually unless truly needed
- ❌ **DON'T**: Create sessions outside the Store

## Touch Points / Key Files

| File | Purpose |
|------|---------|
| `store.py` | `Store` class — factory and entry point |
| `uow/unit_of_work.py` | `UnitOfWork` composing all domain mixins |
| `uow/base.py` | `CrudMixin` with generic CRUD and SQL helpers |
| `models/base.py` | `BaseModel` with `insert_ignore()`, `to_dict()`, etc. |
| `models/tracker.py` | Core models: `Workout`, `WorkoutItem`, `Exercise`, `Sets` |

## JIT Index Hints

```bash
# Find all models
rg -n "class.*\(BaseModel\)" fitness_tracker/database/models

# Find all UoW domain methods
rg -n "def (hevy_|tc_|tracker_|ah_)" fitness_tracker/database/uow

# Find SQL scripts
find fitness_tracker/database/SQL -name "*.sql"

# Find foreign key relationships
rg -n "ForeignKey" fitness_tracker/database/models

# Find unique constraints
rg -n "UniqueConstraint" fitness_tracker/database/models
```

## Common Gotchas

- Using SQLAlchemy 1.4 syntax (not 2.0) — use `session.query()` not `select()`
- `insert_ignore()` uses SQLite-specific `OR IGNORE` syntax
- Always use `uow.flush()` instead of `uow.commit()` for mid-transaction ID generation
- Models use `TYPE_CHECKING` imports to avoid circular dependencies

## Pre-PR Checks

```bash
uv run poe lint && uv run poe typecheck && uv run poe doclint && uv run poe test
```
