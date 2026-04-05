C#!/bin/bash
# PostToolUse hook: Block Python files exceeding 300 code lines
# Code lines = total minus docstrings, comments, and blank lines
# Hard cap: 500 total lines regardless

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')

[ -z "$file_path" ] && exit 0
[[ "$file_path" != *.py ]] && exit 0
[ ! -f "$file_path" ] && exit 0

total_lines=$(wc -l < "$file_path")

# Hard cap on total lines
if [ "$total_lines" -gt 500 ]; then
    echo "File exceeds 500 total lines ($total_lines). Split into smaller modules." >&2
    exit 2
fi

# Count code-only lines (exclude docstrings, comments, blanks) using Python ast
code_lines=$(python3 -c "
import ast, sys

try:
    with open(sys.argv[1]) as f:
        source = f.read()
        lines = source.splitlines()
    total = len(lines)

    # Find docstring line ranges via AST
    tree = ast.parse(source)
    docstring_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                ds = node.body[0]
                for ln in range(ds.lineno, ds.end_lineno + 1):
                    docstring_lines.add(ln)

    # Count non-docstring, non-comment, non-blank lines
    code = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if i in docstring_lines:
            continue
        if not stripped or stripped.startswith('#'):
            continue
        code += 1
    print(code)
except Exception:
    # If parsing fails, fall back to total
    print(total)
" "$file_path")

if [ "$code_lines" -gt 300 ]; then
    echo "File has $code_lines code lines (excluding docstrings/comments/blanks; $total_lines total). Split into smaller modules." >&2
    exit 2
fi

exit 0
