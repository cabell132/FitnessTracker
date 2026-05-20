"""Regression tests for PI/Claude agent hook compatibility."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_CONFIG = REPO_ROOT / ".pi" / "hook" / "hooks.yaml"
SCRIPTS_DIR = REPO_ROOT / ".claude" / "scripts"


def run_hook(script_name: str, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    """Run a hook script with a PI-style stdin payload."""
    return subprocess.run(  # noqa: S603 - tests execute fixed repo-local hook scripts.
        ["/bin/bash", str(SCRIPTS_DIR / script_name)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        check=False,
    )


def test_pi_hooks_config_uses_supported_bash_actions() -> None:
    """PI hook config should load through pi-yaml-hooks, not Claude command actions."""
    config = HOOKS_CONFIG.read_text(encoding="utf-8")

    assert "hooks:" in config
    assert "event: tool.before.bash" in config
    assert "event: tool.after.write" in config
    assert "event: session.idle" in config
    assert "- command:" not in config

    script_paths = re.findall(r'bash: "(\.claude/scripts/[^"]+)"', config)
    script_paths.extend(re.findall(r'command: "(\.claude/scripts/[^"]+)"', config))
    assert script_paths
    for script_path in script_paths:
        path = REPO_ROOT / script_path
        assert path.exists(), script_path
        assert os.access(path, os.X_OK), script_path


def test_pre_bash_hooks_read_pi_tool_args_command() -> None:
    """Pre-bash guards should understand pi-yaml-hooks tool_args.command payloads."""
    payload = {"tool_args": {"command": "pytest tests"}}

    poe_result = run_hook("enforce-poe.sh", payload)

    assert poe_result.returncode == 2
    assert "Use 'uv run poe test'" in poe_result.stderr

    uv_result = run_hook("enforce-uv.sh", {"tool_args": {"command": "pip install requests"}})

    assert uv_result.returncode == 2
    assert "Use 'uv add <package>'" in uv_result.stderr

    git_result = run_hook("enforce-safe-git.sh", {"tool_args": {"command": "git reset --hard"}})

    assert git_result.returncode == 2
    assert "git reset --hard" in git_result.stderr


def test_pre_write_hooks_read_pi_tool_args_path_and_content() -> None:
    """Pre-write guards should understand pi-yaml-hooks path/content payloads."""
    config_result = run_hook("protect-config.sh", {"tool_args": {"path": ".claude/settings.json"}})

    assert config_result.returncode == 2
    assert "managed by the cookiecutter template" in config_result.stderr

    init_result = run_hook(
        "protect-init.sh",
        {
            "tool_args": {
                "path": "fitness_tracker/__init__.py",
                "content": "def nope():\n    pass\n",
            }
        },
    )

    assert init_result.returncode == 2
    assert "No logic in __init__.py" in init_result.stderr


def test_post_write_hooks_read_pi_changed_file_paths() -> None:
    """Post-write checks should accept pi-yaml-hooks changed file path payloads."""
    result = run_hook(
        "check-test-naming.sh",
        {"changes": [{"operation": "modify", "path": "tests/helpers.py"}]},
    )

    assert result.returncode == 2
    assert "Test files must be named test_*.py" in result.stderr
