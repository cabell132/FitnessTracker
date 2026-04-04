#!/bin/bash
# PreToolUse hook: Block edits to template-managed config files
# These files are managed by the cookiecutter template and should not be
# modified to "fix" linting errors. Fix the code instead.

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

[ -z "$file_path" ] && exit 0

# Protected config files that are template-managed
PROTECTED_FILES=(
    "pyproject.toml"
    ".pre-commit-config.yaml"
    ".claude/settings.json"
    ".claude/scripts/"
    ".claude/agents/"
)

for pattern in "${PROTECTED_FILES[@]}"; do
    if [[ "$file_path" == *"$pattern"* ]]; then
        echo "BLOCKED: $file_path is managed by the cookiecutter template." >&2
        echo "Do not edit config files to suppress linting errors — fix the code instead." >&2
        echo "To update template files, use /sync-cookiecutter-template." >&2
        exit 2
    fi
done

exit 0
