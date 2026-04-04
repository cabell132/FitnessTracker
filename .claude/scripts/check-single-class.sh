#!/bin/bash
# PostToolUse hook: Block multiple classes per file (>50 lines each)

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

[ -z "$file_path" ] && exit 0
[[ "$file_path" != *.py ]] && exit 0
[ ! -f "$file_path" ] && exit 0

# Skip Pydantic model files — multiple small classes per file is normal
# Handle both Unix (/) and Windows (\) path separators
[[ "$file_path" == */models/* || "$file_path" == *\\models\\* || "$file_path" == */models.py || "$file_path" == *\\models.py ]] && exit 0

class_count=$(grep -c '^class ' "$file_path" 2>/dev/null || echo 0)
line_count=$(wc -l < "$file_path")

if [ "$class_count" -gt 1 ] && [ "$line_count" -gt 50 ]; then
    echo "Multiple classes in one file ($class_count classes, $line_count lines). Extract each class > 50 lines to its own module." >&2
    exit 2
fi

exit 0
