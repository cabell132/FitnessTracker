#!/bin/bash
# Stop hook: Run ruff check on all modified Python files

modified_files=$(git diff --name-only --diff-filter=ACM HEAD -- '*.py' 2>/dev/null)
untracked_files=$(git ls-files --others --exclude-standard -- '*.py' 2>/dev/null)
all_files=$(echo -e "${modified_files}\n${untracked_files}" | grep -v '^$' | sort -u)

[ -z "$all_files" ] && exit 0

output=$(uv run ruff check $all_files 2>&1)
if [ $? -ne 0 ]; then
    line_count=$(echo "$output" | wc -l)
    if [ "$line_count" -gt 30 ]; then
        mkdir -p .claude
        echo "$output" > .claude/check-output.log
        echo "=== Ruff Errors ($line_count lines — truncated) ===" >&2
        echo "$output" | head -20 >&2
        echo "..." >&2
        echo "Full output saved to .claude/check-output.log" >&2
    else
        echo "=== Ruff Errors ===" >&2
        echo "$output" >&2
    fi
    exit 2
fi

exit 0
