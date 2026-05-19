"""Regression tests for agent-facing workflow documentation."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_COMMANDS_DIR = REPO_ROOT / ".agents" / "commands"
HEVY_TRUECOACH_WORKFLOW_DOC = REPO_ROOT / "docs" / "agents" / "hevy-truecoach-workflow.md"
CREATE_HEVY_ROUTINE_DOC = "create-hevy-routine.md"

RETIRED_COMMAND_STRINGS = (
    "hevy-templates",
    "fitness-tracker truecoach import-recent",
    "fitness-tracker truecoach due",
)
CREATE_HEVY_ROUTINE_COMMAND_STRINGS = (
    "fitness-tracker hevy exercise-templates",
    "fitness-tracker truecoach workouts import-recent",
)
WORKFLOW_CONTRACT_STRINGS = (
    "Implemented platform primitive surface",
    "Future intended platform primitive surface",
    "--json stdout is machine-only",
    "warnings and progress messages go to stderr",
    "remote-first",
    "explicit `cached` commands",
    "cross-platform judgement belongs in `sync-review` and `sync-apply`",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def test_platform_primitive_agent_docs_use_canonical_command_surface() -> None:
    """Agent docs should describe the implemented platform primitive contract."""
    command_docs = {path.name: read_text(path) for path in AGENT_COMMANDS_DIR.glob("*.md")}
    workflow_doc = read_text(HEVY_TRUECOACH_WORKFLOW_DOC)
    normalized_workflow_doc = normalize_whitespace(workflow_doc)
    create_hevy_routine_doc = command_docs[CREATE_HEVY_ROUTINE_DOC]
    all_agent_docs = "\n".join([*command_docs.values(), workflow_doc])

    for command_string in RETIRED_COMMAND_STRINGS:
        assert command_string not in all_agent_docs

    for command_string in CREATE_HEVY_ROUTINE_COMMAND_STRINGS:
        assert command_string in create_hevy_routine_doc

    for contract_string in WORKFLOW_CONTRACT_STRINGS:
        assert contract_string in normalized_workflow_doc
