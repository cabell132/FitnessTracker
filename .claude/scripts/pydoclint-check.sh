#!/bin/bash
# PostToolUse hook: Run pydoclint on the edited Python file (skip test files)

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

[ -z "$file_path" ] && exit 0
[[ "$file_path" != *.py ]] && exit 0
[ ! -f "$file_path" ] && exit 0

# Skip test files
echo "$file_path" | grep -q '/tests/' && exit 0

output=$(uv run pydoclint "$file_path" 2>&1)
if [ $? -ne 0 ]; then
    line_count=$(echo "$output" | wc -l)
    if [ "$line_count" -gt 30 ]; then
        mkdir -p .claude
        echo "$output" > .claude/check-output.log
        echo "=== Pydoclint Errors ($line_count lines — truncated) ===" >&2
        echo "$output" | head -20 >&2
        echo "..." >&2
        echo "Full output saved to .claude/check-output.log" >&2
    else
        echo "=== Pydoclint Errors ===" >&2
        echo "$output" >&2
    fi
    exit 2
fi

exit 0
