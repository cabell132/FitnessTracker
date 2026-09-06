# CLAUDE.md

Guidance for AI agents and engineering skills working in this repository.

## Agent skills

Configuration for the engineering skills installed under `.agents/skills/`. Each subsection links to a file under `docs/agents/` with the full conventions.

### Sandcastle

Run

```bash
caffeinate -dimsu -- npx tsx .sandcastle/main.mts
```

### Issue tracker

Issues and PRDs live in GitHub Issues (`cabell132/FitnessTracker`), managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary — `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Hevy and True Coach workflow

The automatic sync workflow started by `main.py` is documented in `docs/agents/hevy-truecoach-workflow.md`.

## Simplicity

- Prefer concise, simple solutions over clever or heavy abstraction. Channel "YAGNI" principals.

- If a substantially simpler approach exists, use it or surface it clearly.
