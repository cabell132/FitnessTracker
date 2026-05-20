#!/bin/bash
# PostToolUse hook: Verify test file naming convention

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.path // .tool_args.file_path // .tool_args.path // .files[0] // .changes[0].path // empty')

[ -z "$file_path" ] && exit 0
[[ "$file_path" != *.py ]] && exit 0

# Check if path is inside a tests directory
if [[ "$file_path" == tests/* || "$file_path" == */tests/* || "$file_path" == *\\tests\\* ]]; then
    filename=$(basename "$file_path")
    if [[ "$filename" != test_* ]] && [[ "$filename" != conftest.py ]] && [[ "$filename" != __init__.py ]]; then
        echo "Test files must be named test_*.py (got '$filename')" >&2
        exit 2
    fi
fi

exit 0
