#!/bin/bash
# PreToolUse hook: No logic in __init__.py — imports and __all__ only

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

[ -z "$file_path" ] && exit 0

# Only check __init__.py files
[[ "$(basename "$file_path")" != "__init__.py" ]] && exit 0

# Get the content being written/edited
content=$(echo "$input" | jq -r '.tool_input.content // .tool_input.new_string // empty')

[ -z "$content" ] && exit 0

# Use Python to properly parse what's allowed in __init__.py
# Allowed: imports, __all__, __version__, comments, docstrings, blank lines,
#          and continuation lines (list items, closing brackets, etc.)
logic=$(python3 -c "
import sys, re

content = sys.stdin.read()
lines = content.splitlines()

i = 0
violations = []
while i < len(lines):
    line = lines[i]
    stripped = line.strip()

    # Skip blank lines and comments
    if not stripped or stripped.startswith('#'):
        i += 1
        continue

    # Skip import statements
    if stripped.startswith(('import ', 'from ')):
        i += 1
        continue

    # Skip __all__ and __version__ assignments (including multi-line)
    if re.match(r'^__(?:all|version)__\s*=', stripped):
        # Walk past continuation lines (brackets, strings, commas)
        depth = stripped.count('[') + stripped.count('(') - stripped.count(']') - stripped.count(')')
        i += 1
        while i < len(lines) and depth > 0:
            s = lines[i].strip()
            depth += s.count('[') + s.count('(') - s.count(']') - s.count(')')
            i += 1
        continue

    # Skip docstrings (triple-quoted)
    if stripped.startswith(('\"\"\"', \"'''\")):
        quote = stripped[:3]
        if stripped.count(quote) >= 2:
            i += 1
            continue
        i += 1
        while i < len(lines) and quote not in lines[i]:
            i += 1
        i += 1
        continue

    # Skip __all__/__version__ continuation lines (Edit tool sends partial content)
    # These are quoted strings, closing brackets, or trailing commas
    if re.match(r'^[\"\x27\]\),\s]+$', stripped) or re.match(r'^[\"\x27].*[\"\x27],?$', stripped):
        i += 1
        continue

    # Anything else is logic
    violations.append(stripped)
    i += 1

for v in violations[:5]:
    print(v)
" <<< "$content" 2>/dev/null)

if [ -n "$logic" ]; then
    echo "No logic in __init__.py — imports and __all__ only." >&2
    echo "Detected non-import content:" >&2
    echo "$logic" >&2
    exit 2
fi

exit 0
