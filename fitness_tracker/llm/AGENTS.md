# LLM Package - Agent Guidelines

> LangChain-based LLM integration for parsing and matching workout data

## Package Identity

- **Purpose**: Use GPT models to parse exercise info, extract sets, and link workout items
- **Tech**: LangChain, OpenAI (gpt-4o-mini), Pydantic for structured outputs
- **Pattern**: Prompt template + Pydantic model → Structured response

## Setup & Run

```bash
# Requires OPENAI_API_KEY in environment
# No separate setup - uses root environment
```

## Patterns & Conventions

### Architecture

```
fitness_llm.py      → Domain-specific methods (FitnessLLM)
    ↓
open_ai_llm.py      → OpenAI wrapper with function_prompt()
    ↓
prompt_templates.py → System prompts for each task
    ↓
prompt_models.py    → Pydantic models for structured output
```

### Adding New LLM Methods

1. Define Pydantic model in `prompt_models.py`
2. Add prompt template in `prompt_templates.py`
3. Add method in `fitness_llm.py` using `function_prompt()`

```python
# Step 1: prompt_models.py
class MyOutput(BaseModel):
    field1: str
    field2: int

# Step 2: prompt_templates.py
PROMPT_MY_TASK = "You are an expert at... Given: {data}, extract..."

# Step 3: fitness_llm.py
def my_new_method(self, data: str) -> MyOutput:
    return self.function_prompt(data, PROMPT_MY_TASK, MyOutput)
```

### Function Prompt Pattern

The base class provides structured output via LangChain:

```python
# See open_ai_llm.py
def function_prompt(self, data: str, prompt: str, model: type[T]) -> T:
    # Uses structured output to guarantee Pydantic model response
    ...
```

### File Examples

- ✅ **DO**: Define all output schemas in `prompt_models.py`
- ✅ **DO**: Keep prompts in `prompt_templates.py` as constants
- ✅ **DO**: Add domain methods to `FitnessLLM` class
- ❌ **DON'T**: Hardcode prompts inside methods

## Touch Points / Key Files

| File | Purpose |
|------|---------|
| `fitness_llm.py` | Main `FitnessLLM` class with domain methods |
| `open_ai_llm.py` | Base `OpenAILLM` with `function_prompt()` |
| `prompt_models.py` | Pydantic models: `PostRoutinesRequestSets`, `Exercise`, `WorkoutItemLinkList` |
| `prompt_templates.py` | Prompt constants: `PROMPT_EXTRACT_INFO_SETS`, `PROMPT_EXERCISE`, etc. |

## JIT Index Hints

```bash
# Find LLM methods
rg -n "def.*\(self.*\)" fitness_tracker/llm/fitness_llm.py

# Find prompt templates
rg -n "^PROMPT_" fitness_tracker/llm/prompt_templates.py

# Find Pydantic output models
rg -n "class.*\(BaseModel\)" fitness_tracker/llm/prompt_models.py

# Find async methods
rg -n "async def" fitness_tracker/llm
```

## Current LLM Methods

| Method | Purpose | Output Model |
|--------|---------|--------------|
| `parse_the_sets()` | Extract set info from exercise text | `PostRoutinesRequestSets` |
| `parse_completed_sets()` | Parse completed workout results | `PostRoutinesRequestSets` |
| `link_workout_items()` | Match Hevy items to True Coach items | `WorkoutItemLinkList` |
| `get_exercise_info()` | Extract exercise metadata | `Exercise` |
| `parse_the_sets_async()` | Async batch parsing | `list[PostRoutinesRequestSets]` |

## Common Gotchas

- Model name is hardcoded in `Syncronizer`: `gpt-4o-mini-2024-07-18`
- Logging is suppressed for `httpcore`, `openai`, `httpx` in `fitness_llm.py`
- Async methods exist but aren't currently used in sync flow
- Temperature is 0 by default for deterministic outputs

## Pre-PR Checks

```bash
uv run ruff check fitness_tracker/llm && uv run ty check fitness_tracker/llm
```
