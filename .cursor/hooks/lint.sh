#!/bin/bash
# Hook script to lint Python files with ruff/ty and TypeScript files with eslint after edits

# Read JSON input from stdin
input=$(cat)

# Extract file path from JSON (handle both Windows and Unix paths)
file_path=$(echo "$input" | jq -r '.file_path // empty')

# Check if file path is empty
if [ -z "$file_path" ]; then
    exit 0
fi

# Convert Windows path to Unix-style if needed (for Git Bash)
file_path=$(echo "$file_path" | sed 's|\\|/|g')

# Get the workspace root
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "$script_dir/../.." && pwd)"
backend_dir="$workspace_root/backend"
frontend_dir="$workspace_root/frontend"

# Check if file is a Python file
if [[ "$file_path" =~ \.py$ ]]; then
    # Python file - check if it's in backend
    if [ ! -f "$backend_dir/pyproject.toml" ]; then
        exit 0
    fi

    # Check if the edited file is within the backend directory structure
    if [[ "$file_path" != "$backend_dir"* ]] && [[ "$file_path" != "$workspace_root/backend"* ]]; then
        exit 0
    fi

    # Change to backend directory
    cd "$backend_dir" || exit 0

    # Get relative path from backend directory
    rel_path="${file_path#$backend_dir/}"
    rel_path="${rel_path#/}"  # Remove leading slash if present

    # Run ruff check with --fix on the specific file
    echo "Running ruff check on $rel_path..." >&2
    uv run ruff check "$rel_path" --fix 2>&1

    # Run ruff format on the specific file
    echo "Running ruff format on $rel_path..." >&2
    uv run ruff format "$rel_path" 2>&1

    # Run ty check (checks whole project, but that's fine)
    # Only run if the file is in the src directories configured in ty.toml
    if [[ "$rel_path" == tunetrove_backend/* ]] || [[ "$rel_path" == tests/* ]]; then
        echo "Running ty check..." >&2
        uv run ty check 2>&1 | head -50  # Limit output to first 50 lines
    fi

# Check if file is a TypeScript file
elif [[ "$file_path" =~ \.(ts|tsx)$ ]]; then
    # TypeScript file - check if it's in frontend
    if [ ! -f "$frontend_dir/package.json" ]; then
        exit 0
    fi

    # Check if the edited file is within the frontend directory structure
    if [[ "$file_path" != "$frontend_dir"* ]] && [[ "$file_path" != "$workspace_root/frontend"* ]]; then
        exit 0
    fi

    # Change to frontend directory
    cd "$frontend_dir" || exit 0

    # Get relative path from frontend directory
    rel_path="${file_path#$frontend_dir/}"
    rel_path="${rel_path#/}"  # Remove leading slash if present

    # Run eslint on the specific file with --fix for auto-fixing
    echo "Running eslint on $rel_path..." >&2
    npx eslint "$rel_path" --fix 2>&1

else
    # Not a supported file type, exit silently
    exit 0
fi

exit 0
