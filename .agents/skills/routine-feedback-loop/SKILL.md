---
name: routine-feedback-loop
description: Reviews Hevy Routine feedback against original True Coach-to-Hevy artifacts, classifies Athlete edits as defects/preferences/session substitutions/noise, and routes confirmed generation defects to small fixes or GitHub issues. Use when checking updated Hevy Routines, reviewing post-workout Routine edits, or making Routine creation learn safely from feedback.
---

# Routine Feedback Loop

## Purpose

Manage the **Routine feedback review loop**: compare an updated Hevy Routine against the original True Coach-to-Hevy Routine creation artifacts, classify the Athlete's edits, and turn confirmed Routine generation defects into tiny safe fixes or tracked GitHub issues.

Use project language from `CONTEXT.md`:

- **Routine feedback**: reviewable difference between performed Hevy Workout/Routine update and source Routine.
- **Routine generation defect**: generated Routine contradicted Coach prescription evidence or project rules.
- **Routine preference signal**: Athlete default that may shape future prescriptions when Coach evidence is silent.
- **Session-only substitution**: change made for one performed session, not a durable preference.
- **Routine feedback ledger**: durable record with `observed`, `accepted`, `promoted`, or `rejected` status.

## Quick start

1. Discover candidates from existing Routine creation artifacts:

   ```bash
   python .agents/skills/routine-feedback-loop/scripts/find-candidates.py reports
   ```

2. For a candidate, generate the high-signal diff:

   ```bash
   uv run fitness-tracker hevy routines diff-json ROUTINE_ID \
     reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.json \
     --output-path reports/sync-review/routine-feedback/ROUTINE_ID/hevy-routine-diff.md
   ```

3. If needed, inspect low-signal noise too:

   ```bash
   uv run fitness-tracker hevy routines diff-json ROUTINE_ID \
     reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.json \
     --include-low-signal \
     --output-path reports/sync-review/routine-feedback/ROUTINE_ID/hevy-routine-diff.low-signal.md
   ```

4. Create review artifacts under:

   ```text
   reports/sync-review/routine-feedback/ROUTINE_ID/
   ├── evidence.json
   ├── classification-suggestions.json
   ├── classification-decisions.json
   ├── decision-validation.json
   ├── report.md
   ├── diagnosis.md              # only for suspected/confirmed defects
   └── issue.md                  # only when a GitHub issue is recommended/created
   ```

## Evidence requirements

Prefer original Routine creation artifacts over live reconstruction:

- `reports/sync-review/truecoach-to-hevy/WORKOUT_ID/plan.json`
- `report.md`
- `hevy-request.json`
- `hevy-response.json`
- remote Hevy Routine inspect/diff evidence
- original True Coach snapshot if available

If original artifacts are missing, downgrade to a limited review. You may record missing-evidence blockers, but do not diagnose a Routine generation defect or persist ledger entries that depend on missing evidence.

## Classification buckets

Classify each difference as one of:

- `generation_defect` — generated Routine contradicted Coach evidence/project rules.
- `routine_preference_signal` — durable Athlete preference candidate; Coach evidence was silent.
- `session_only_substitution` — one-off equipment, pain, time, or session context change.
- `low_signal_performed_result` — pure load/reps or performed cardio duration noise unless explicitly promoted.
- `unclear_ask_athlete` — artifacts do not prove defect and feedback could be preference or session-only.

Ask the Athlete before writing a ledger entry or issue when a high-signal change could reasonably be preference or session-only substitution.

## Defect path

For suspected Routine generation defects, load and follow the `diagnose` skill before changing code or prompts:

1. Reproduce from original artifacts or a focused test/fixture.
2. Minimise the failing case.
3. Decide cause type:
   - deterministic code bug
   - workflow prompt bug in `.pi/prompts/create-hevy-routine.md`
   - heuristic/model prompt bug in production prompt templates
   - data/config bug
   - not actually a bug
4. Fix only if small and safe. When Routine feedback exposes an Agent workflow mistake, repair `.pi/prompts/create-hevy-routine.md`; do not treat it as a production LLM prompt defect unless the generated review/request came from production prompt templates.
5. Regression-test the touched path.

Auto-fix is allowed only when all are true:

- cause is reproduced with a failing test or fixture;
- fix is localized;
- expected behavior is clear from Coach evidence/project rules;
- no database migration;
- no broad refactor;
- no remote mutation;
- tests pass for the touched path.

If larger, prepare `issue.md`, ask for confirmation, then create a GitHub issue with `gh issue create`. Use labels:

- confirmed larger defect: `ready-for-agent`
- needs Athlete clarification: `needs-info`
- uncertain system/design classification: `needs-triage`

## Ledger rules

Routine feedback reviews are artifact-first. Accepted classifications should eventually be persisted to the local tracker as the **Routine feedback ledger**; review artifacts remain the audit trail.

Statuses:

- `observed`: detected by review.
- `accepted`: Agent/Athlete agrees classification is correct.
- `promoted`: future Routine creation may use this signal when Coach evidence is silent.
- `rejected`: noise/session-only/misclassified.

Never auto-promote. Repeated accepted signals may recommend promotion, but promotion requires explicit review.

Promotion recommendation thresholds:

- Rest default: same Hevy template + same rest value, 2+ accepted signals.
- Exercise preference: same True Coach exercise + same preferred Hevy template, 2+ accepted signals.
- Omission/removal: never recommend automatically; ask/review.
- Notes/cues: 3+ accepted signals because free text is noisy.

In v1, Routine creation must not automatically consume ledger entries. See `docs/adr/0010-routine-feedback-ledger-is-not-auto-consumed.md`.

## Report checklist

Every `report.md` should include:

- Routine ID and source True Coach Workout ID, if known.
- Evidence paths used and missing evidence blockers.
- High-signal differences.
- Low-signal differences/noise summary.
- Classification decisions and rationale.
- Athlete questions, if any.
- Diagnosis summary for defects.
- Fix applied or issue recommendation.
- Ledger status recommendation (`observed`, `accepted`, `promoted`, `rejected`).
