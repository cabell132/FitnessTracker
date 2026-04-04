# Database Package - Agent Guidelines

> SQLAlchemy-based database layer with Repository + Service patterns

## Package Identity

- **Purpose**: Data persistence layer for fitness data across all platforms
- **Tech**: SQLAlchemy 1.4, SQLite, Alembic migrations
- **Pattern**: Models → Repositories → Services → Connection

## Setup & Run

```bash
# Initialize database (creates tables)
python -c "from fitness_tracker.database import Database; from sqlalchemy import create_engine; Database(create_engine('sqlite:///fitness_tracker.db')).init_db()"

# Run migrations
alembic upgrade head

# Create new migration after model changes
alembic revision --autogenerate -m "description"
```

## Patterns & Conventions

### Layer Architecture

```
connection.py (Database class)
    ├── services/     → Business logic, session management
    │   └── base.py   → BaseService with get_session()
    ├── repository/   → CRUD operations per model
    │   └── base.py   → BaseRepository[T] generic class
    ├── models/       → SQLAlchemy ORM models
    │   └── base.py   → BaseModel with common methods
    └── SQL/          → Raw SQL scripts for complex queries
```

### Model Definition

- ✅ **DO**: Inherit from `BaseModel` in `models/base.py`
- ✅ **DO**: Use `__tablename__: str = __qualname__` for table name
- ✅ **DO**: Define relationships with proper `Mapped[]` type hints
- ✅ **DO**: Use `TYPE_CHECKING` for circular import relationships

```python
# See models/tracker.py for full pattern
class Workout(BaseModel):
    __tablename__: str = __qualname__
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=True)
    hevy_app_id = Column(String, ForeignKey("HevyAppWorkout.id"), nullable=True)
    
    # Relationships with type hints
    workout_items: Mapped[list["WorkoutItem"]] = relationship("WorkoutItem", back_populates="workout")
```

### Repository Pattern

- ✅ **DO**: Create specific repository inheriting `BaseRepository[ModelClass]`
- ✅ **DO**: Pass session to repository constructor
- ❌ **DON'T**: Create sessions inside repositories

```python
# See repository/tracker.py
class FitnessTrackerWorkoutRepository(BaseRepository[Workout]):
    def __init__(self, session: Session) -> None:
        super().__init__(session=session, model_class=Workout)
```

### Service Pattern

- ✅ **DO**: Inherit from `BaseService` for session management
- ✅ **DO**: Use `with self.get_session() as session:` context manager
- ✅ **DO**: Create repositories inside service methods

```python
# See services/tracker.py
class FitnessTrackerService(BaseService):
    def get_workout(self, session: Session, **kwargs: Any):
        workout_repo = FitnessTrackerWorkoutRepository(session=session)
        return workout_repo.get(**kwargs)
```

### Raw SQL Scripts

For complex queries, use SQL scripts in `SQL/` directory:

```python
# See sync/hevy_tracker/sync.py for pattern
stmnt = text(
    Path("fitness_tracker/database/SQL/hevy/tracker/sets/insert.sql").read_text(encoding="utf-8")
)
session.execute(stmnt, {"param": value})
```

## Touch Points / Key Files

| File | Purpose |
|------|---------|
| `connection.py` | Main `Database` class with all services |
| `models/base.py` | `BaseModel` with `insert_ignore()`, `to_dict()`, etc. |
| `models/tracker.py` | Core models: `Workout`, `WorkoutItem`, `Exercise`, `Sets` |
| `repository/base.py` | Generic `BaseRepository[T]` with CRUD methods |
| `services/base.py` | `BaseService` with `get_session()` context manager |

## JIT Index Hints

```bash
# Find all models
rg -n "class.*\(BaseModel\)" fitness_tracker/database/models

# Find all repositories
rg -n "class.*Repository" fitness_tracker/database/repository

# Find service methods
rg -n "def (add|get|delete|update)" fitness_tracker/database/services

# Find foreign key relationships
rg -n "ForeignKey" fitness_tracker/database/models

# Find SQL scripts
find fitness_tracker/database/SQL -name "*.sql"

# Find unique constraints
rg -n "UniqueConstraint" fitness_tracker/database/models
```

## Common Gotchas

- Using SQLAlchemy 1.4 syntax (not 2.0) - use `session.query()` not `select()`
- `insert_ignore()` uses SQLite-specific `OR IGNORE` syntax
- Foreign keys are **not** auto-enforced - pragma commented out in `connection.py`
- Always commit after executing raw SQL: `session.execute(stmnt); session.commit()`
- Models use `TYPE_CHECKING` imports to avoid circular dependencies

## Pre-PR Checks

```bash
uv run ruff check fitness_tracker/database && uv run mypy fitness_tracker/database
```
