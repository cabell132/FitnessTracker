#!/bin/bash
# PreToolUse hook: Block raw pip/python commands, enforce uv
# Exit 2 = block with message, Exit 0 = allow

input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // .tool_args.command // empty')

[ -z "$command" ] && exit 0

# Extract the base command (first word, ignoring leading env vars)
base_cmd=$(echo "$command" | sed 's/^[A-Z_]*=[^ ]* *//' | awk '{print $1}')

case "$base_cmd" in
    pip|pip3)
        action=$(echo "$command" | awk '{print $2}')
        case "$action" in
            install|uninstall)
                echo "BLOCKED: Use 'uv add <package>' or 'uv pip install <package>' instead of '$base_cmd $action'" >&2
                exit 2
                ;;
            freeze)
                echo "BLOCKED: Use 'uv pip freeze' or 'uv tree' instead of '$base_cmd freeze'" >&2
                exit 2
                ;;
        esac
        ;;
    python|python3)
        # Allow python -c (inline scripts) but block python script.py and python -m pip
        next=$(echo "$command" | awk '{print $2}')
        if [ "$next" = "-m" ]; then
            mod=$(echo "$command" | awk '{print $3}')
            if [ "$mod" = "pip" ]; then
                echo "BLOCKED: Use 'uv pip install' instead of '$base_cmd -m pip'" >&2
                exit 2
            fi
        elif [ "$next" != "-c" ] && [ -n "$next" ] && [[ "$next" != -* ]]; then
            echo "BLOCKED: Use 'uv run python $next' instead of '$base_cmd $next'" >&2
            exit 2
        fi
        ;;
esac

exit 0
