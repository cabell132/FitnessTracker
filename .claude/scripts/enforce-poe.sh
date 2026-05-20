#!/bin/bash
# PreToolUse hook: Block direct tool invocation, enforce poe tasks
# Exit 2 = block with message, Exit 0 = allow

input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // .tool_args.command // empty')

[ -z "$command" ] && exit 0

# Allow if the command goes through poe (uv run poe ...)
if echo "$command" | grep -qE '(^|&&|;|\|)\s*(uv run )?poe\s'; then
    exit 0
fi

# Extract the base command (first word, ignoring leading env vars)
base_cmd=$(echo "$command" | sed 's/^[A-Z_]*=[^ ]* *//' | awk '{print $1}')

# Block direct uv run <tool> as well as bare <tool>
full_prefix=$(echo "$command" | sed 's/^[A-Z_]*=[^ ]* *//' | awk '{print $1, $2, $3}')

case "$base_cmd" in
    ruff)
        action=$(echo "$command" | awk '{print $2}')
        if [ "$action" = "check" ] || [ "$action" = "format" ]; then
            echo "BLOCKED: Use 'uv run poe lint' or 'uv run poe format' instead of 'ruff $action'" >&2
            exit 2
        fi
        ;;
    pytest)
        echo "BLOCKED: Use 'uv run poe test' instead of 'pytest'" >&2
        exit 2
        ;;
    ty)
        action=$(echo "$command" | awk '{print $2}')
        if [ "$action" = "check" ]; then
            echo "BLOCKED: Use 'uv run poe typecheck' instead of 'ty check'" >&2
            exit 2
        fi
        ;;
esac

# Also catch "uv run ruff/pytest/ty" (not via poe)
if echo "$command" | grep -qE '(^|&&|;|\|)\s*uv run ruff (check|format)'; then
    echo "BLOCKED: Use 'uv run poe lint' or 'uv run poe format' instead of 'uv run ruff'" >&2
    exit 2
fi
if echo "$command" | grep -qE '(^|&&|;|\|)\s*uv run pytest'; then
    echo "BLOCKED: Use 'uv run poe test' instead of 'uv run pytest'" >&2
    exit 2
fi
if echo "$command" | grep -qE '(^|&&|;|\|)\s*uv run ty check'; then
    echo "BLOCKED: Use 'uv run poe typecheck' instead of 'uv run ty check'" >&2
    exit 2
fi

exit 0
