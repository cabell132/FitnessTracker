"""Regression tests for agent-facing workflow documentation."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_platform_primitive_agent_docs_use_canonical_command_surface() -> None:
    """Agent docs should describe the implemented platform primitive contract."""
    command_docs = {
        path.name: path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / ".agents" / "commands").glob("*.md")
    }
    workflow_doc = (REPO_ROOT / "docs" / "agents" / "hevy-truecoach-workflow.md").read_text(
        encoding="utf-8"
    )
    all_agent_docs = "\n".join([*command_docs.values(), workflow_doc])

    assert "hevy-templates" not in all_agent_docs
    assert "fitness-tracker hevy exercise-templates" in command_docs["create-hevy-routine.md"]
    assert (
        "fitness-tracker truecoach workouts import-recent" in command_docs["create-hevy-routine.md"]
    )
    assert "fitness-tracker truecoach import-recent" not in all_agent_docs
    assert "fitness-tracker truecoach due" not in all_agent_docs
    assert "Implemented platform primitive surface" in workflow_doc
    assert "Future intended platform primitive surface" in workflow_doc
    assert "--json stdout is machine-only" in workflow_doc
    assert "warnings and progress messages go to stderr" in workflow_doc
    assert "remote-first" in workflow_doc
    assert "explicit `cached` commands" in workflow_doc
    assert "cross-platform judgement belongs in `sync-review` and `sync-apply`" in workflow_doc
