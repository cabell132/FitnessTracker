# Fitness Tracker - Agent Guidelines

> **Simple Python package** for syncing fitness data between platforms (Hevy App, True Coach, Apple Health)

## Project Snapshot

- **Type**: Single Python package (not monorepo)
- **Stack**: Python 3.12+ | SQLAlchemy 1.4 | Alembic | Pydantic | LangChain/OpenAI
- **Package Manager**: uv
- **Sub-packages have their own AGENTS.md** - see JIT Index below

## Root Setup Commands

```bash
# Install dependencies
uv sync

# Install with dev/test extras
uv sync --all-extras

# Run the main sync script
python main.py

# Update database schema
alembic revision --autogenerate && alembic upgrade head
```

## Universal Conventions

### Code Style
- **Docstrings**: Google style (enforced via ruff pydocstyle)
- **Type hints**: Required everywhere, strict mypy enabled
- **Linting**: ruff with extensive rule set (see pyproject.toml)
- **Line length**: 100 characters max

### Commit Format
- Conventional Commits (`feat:`, `fix:`, `chore:`, etc.)
- Commitizen configured for versioning

### Imports
- Absolute imports only (`from fitness_tracker.xxx import yyy`)
- No relative imports (banned via ruff)

## Security & Secrets

- **Never commit** API tokens, keys, or credentials
- Secrets go in `.env` file (python-dotenv loads them)
- Key secrets: `DROPBOX_ACCESS_TOKEN`, OpenAI API key
- Token files (`true_coach_token.json`, etc.) are gitignored

## JIT Index (what to open, not what to paste)

### Package Structure

| Area | Path | Details |
|------|------|---------|
| API Clients | `fitness_tracker/apis/` | [see apis/AGENTS.md](fitness_tracker/apis/AGENTS.md) |
| Database Layer | `fitness_tracker/database/` | [see database/AGENTS.md](fitness_tracker/database/AGENTS.md) |
| Sync Logic | `fitness_tracker/sync/` | [see sync/AGENTS.md](fitness_tracker/sync/AGENTS.md) |
| LLM Integration | `fitness_tracker/llm/` | [see llm/AGENTS.md](fitness_tracker/llm/AGENTS.md) |
| Migrations | `alembic/versions/` | Alembic migration scripts |
| Entry Point | `main.py` | Main orchestration script |

### Quick Find Commands

```bash
# Find a model class
rg -n "class.*\(BaseModel\)" fitness_tracker/database/models

# Find a repository class
rg -n "class.*Repository" fitness_tracker/database/repository

# Find a service method
rg -n "def.*\(self, session:" fitness_tracker/database/services

# Find sync logic
rg -n "def sync" fitness_tracker/sync

# Find API endpoints
rg -n "def (get|post|put|delete)" fitness_tracker/apis

# Find LLM prompts
rg -n "PROMPT_" fitness_tracker/llm/prompt_templates.py
```

## Definition of Done

Before creating a PR:

1. `uv run ruff check fitness_tracker tests` - no lint errors
2. `uv run mypy fitness_tracker` - no type errors  
3. `uv run pytest` - all tests pass
4. Docstrings follow Google style (see `.cursor/rules/` for format)

## Pre-PR Single Command

```bash
uv run ruff check fitness_tracker tests && uv run mypy fitness_tracker && uv run pytest
```
