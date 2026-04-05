# APIs Package - Agent Guidelines

> External API clients for Hevy App and True Coach fitness platforms

## Package Identity

- **Purpose**: HTTP clients for interacting with external fitness APIs
- **Tech**: requests/httpx sessions, Pydantic for response types
- **Pattern**: Client → Sub-resources (exercises, workouts, routines)

## Setup & Run

```bash
# No separate setup - uses root environment
# Requires secrets in .env:
#   - HEVY_API_KEY (or session token)
#   - TRUECOACH_* credentials
```

## Patterns & Conventions

### Client Structure

Each API has:
1. `client.py` - Main client class exposing sub-resources
2. `session.py` - Session management / auth handling
3. `types.py` - Pydantic models for request/response types
4. `exceptions.py` - Custom exception classes
5. Resource modules (`workouts.py`, `exercises.py`, etc.)

### File Examples

- ✅ **DO**: Follow client pattern like `hevy_app/client.py`
  ```python
  class HevyAppClient(BaseClient):
      def __init__(self) -> None:
          self._session = HevyAppSession()
          self.exercises = HevyAppExercises(session=self._session)
          self.workouts = HevyAppWorkouts(session=self._session)
  ```

- ✅ **DO**: Define response types in `types.py` with Pydantic
- ✅ **DO**: Use session classes for auth/token management
- ❌ **DON'T**: Make raw HTTP calls without going through session

### Resource Pattern

```python
# See hevy_app/workouts.py for full pattern
class HevyAppWorkouts:
    def __init__(self, session: HevyAppSession) -> None:
        self._session = session

    def get(self, **kwargs) -> dict:
        return self._session.get("/workouts", params=kwargs)
```

## Touch Points / Key Files

| File | Purpose |
|------|---------|
| `base.py` | Base client class (currently minimal) |
| `hevy_app/client.py` | Hevy App main client |
| `hevy_app/types.py` | Hevy response models (Workout, Exercise, etc.) |
| `hevy_app/session.py` | Hevy auth/session handling |
| `true_coach/client.py` | True Coach main client |
| `true_coach/auth.py` | True Coach OAuth flow |

## JIT Index Hints

```bash
# Find all client classes
rg -n "class.*Client" fitness_tracker/apis

# Find API response types
rg -n "class.*(Response|Workout|Exercise)" fitness_tracker/apis/**/types.py

# Find session methods
rg -n "def (get|post|put|delete)" fitness_tracker/apis/**/session.py

# Find exception classes
rg -n "class.*Error|Exception" fitness_tracker/apis/**/exceptions.py
```

## Common Gotchas

- Hevy has two sessions: `HevyAppSession` (API) and `HevyAppWebSession` (web scraping)
- True Coach requires OAuth refresh - see `true_coach/auth.py`
- urllib3 warnings are disabled in `main.py` (InsecureRequestWarning)
- Token files stored at project root (`true_coach_token.json`)

## Pre-PR Checks

```bash
uv run ruff check fitness_tracker/apis && uv run ty check fitness_tracker/apis
```
