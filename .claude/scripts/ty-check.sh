#!/bin/bash
# Stop hook: Run ty type checker on modified Python files

modified_files=$(git diff --name-only --diff-filter=ACM HEAD -- 'fitness_tracker/*.py' 2>/dev/null)
untracked_files=$(git ls-files --others --exclude-standard -- 'fitness_tracker/*.py' 2>/dev/null)
all_files=$(echo -e "${modified_files}\n${untracked_files}" | grep -v '^$' | sort -u)

[ -z "$all_files" ] && exit 0

# Auto-recover if .venv has wrong platform layout (e.g. Linux venv on Windows)
if [ -d ".venv" ] && [ ! -f ".venv/Scripts/python.exe" ] && [ ! -f ".venv/bin/python.exe" ]; then
    if [ -f ".venv/bin/python" ] && [[ "$(uname -s)" == *MINGW* || "$(uname -s)" == *MSYS* ]]; then
        uv venv --python 3.12 >/dev/null 2>&1 && uv sync --quiet 2>/dev/null
    fi
fi

output=$(uv run ty check $all_files 2>&1)
if [ $? -ne 0 ]; then
    line_count=$(echo "$output" | wc -l)
    if [ "$line_count" -gt 30 ]; then
        mkdir -p .claude
        echo "$output" > .claude/check-output.log
        echo "=== ty Type Errors ($line_count lines — truncated) ===" >&2
        echo "$output" | head -20 >&2
        echo "..." >&2
        echo "Full output saved to .claude/check-output.log" >&2
    else
        echo "=== ty Type Errors ===" >&2
        echo "$output" >&2
    fi
    exit 2
fi

exit 0
