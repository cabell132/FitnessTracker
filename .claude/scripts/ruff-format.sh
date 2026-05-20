#!/bin/bash
# PostToolUse hook: Auto-format Python files on Write|Edit

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.path // .tool_args.file_path // .tool_args.path // .files[0] // .changes[0].path // empty')

[ -z "$file_path" ] && exit 0
[[ "$file_path" != *.py ]] && exit 0

uv run ruff format "$file_path" 2>/dev/null
uv run ruff check --fix "$file_path" 2>/dev/null

exit 0
