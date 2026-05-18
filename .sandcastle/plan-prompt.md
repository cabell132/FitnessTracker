# ISSUES

Here are the open issues in the repo:

<issues-json>

!`gh issue list --state open --label ready-for-agent --json number,title,body,labels,comments --jq '[.[] | select((.title | test("^PRD:"; "i") | not) and ((.body // "") | test("## User Stories|## Implementation Decisions|## Testing Decisions"; "i") | not)) | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`

</issues-json>

The list above has already been filtered to issues ready for work.

Parent issues, PRDs, epics, and other container/specification issues are not
implementation tasks. They may explain the feature and may be referenced by
child issues, but they must never be selected for implementation, including in
the fallback case where every child issue appears blocked.

# TASK

Analyze the open issues and build a dependency graph. For each issue, determine whether it **blocks** or **is blocked by** any other open issue.

An issue B is **blocked by** issue A if:

- B requires code or infrastructure that A introduces
- B and A modify overlapping files or modules, making concurrent work likely to produce merge conflicts
- B's requirements depend on a decision or API shape that A will establish

An issue is **unblocked** if it has zero blocking dependencies on other open issues.

For each unblocked issue, assign a branch name using the format `sandcastle/issue-{id}-{slug}`.

# OUTPUT

Output your plan as a JSON object wrapped in `<plan>` tags:

<plan>
{"issues": [{"id": "42", "title": "Fix auth bug", "branch": "sandcastle/issue-42-fix-auth-bug"}]}
</plan>

Include only unblocked implementation issues. If every implementation issue is
blocked, include the single highest-priority implementation candidate (the one
with the fewest or weakest dependencies). Do not include parent issues, PRDs,
epics, or other container/specification issues.
