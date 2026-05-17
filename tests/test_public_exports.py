"""Public package export regression tests."""

from fitness_tracker import llm, sync
from fitness_tracker.llm.fitness_llm import FitnessLLM
from fitness_tracker.sync import SyncDeps, SyncRunResult, SyncService


def test_sync_package_should_export_current_public_entrypoints_only() -> None:
    """Sync package exports the service facade, not the legacy orchestrator."""
    assert sync.__all__ == ["SyncDeps", "SyncRunResult", "SyncService"]
    assert sync.SyncDeps is SyncDeps
    assert sync.SyncRunResult is SyncRunResult
    assert sync.SyncService is SyncService
    assert not hasattr(sync, "Syncronizer")


def test_llm_package_should_export_domain_llm() -> None:
    """LLM package exports the domain adapter used by sync dependencies."""
    assert llm.__all__ == ["FitnessLLM"]
    assert llm.FitnessLLM is FitnessLLM
    assert not hasattr(llm, "OpenAILLM")
