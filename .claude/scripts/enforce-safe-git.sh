#!/bin/bash
# PreToolUse hook: Block dangerous git operations
# Exit 2 = block with message, Exit 0 = allow

input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // .tool_args.command // empty')

[ -z "$command" ] && exit 0

# Block git push --force (but allow --force-with-lease)
if echo "$command" | grep -qE 'git push\s.*--force($|\s)' && ! echo "$command" | grep -qE -- '--force-with-lease'; then
    echo "BLOCKED: Use 'git push --force-with-lease' instead of 'git push --force'" >&2
    exit 2
fi
if echo "$command" | grep -qE 'git push\s.*\s-f($|\s)' && ! echo "$command" | grep -qE -- '--force-with-lease'; then
    echo "BLOCKED: Use 'git push --force-with-lease' instead of 'git push -f'" >&2
    exit 2
fi

# Block git reset --hard
if echo "$command" | grep -qE 'git reset\s.*--hard'; then
    echo "BLOCKED: Use 'git stash' or 'git checkout -- <file>' instead of 'git reset --hard'" >&2
    exit 2
fi

# Block git clean -fd
if echo "$command" | grep -qE 'git clean\s.*-[a-zA-Z]*f'; then
    echo "BLOCKED: 'git clean -f' is dangerous. Confirm with the user first." >&2
    exit 2
fi

exit 0
