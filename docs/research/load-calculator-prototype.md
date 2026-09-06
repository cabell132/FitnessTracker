# Local load-calculator policy experiment

Implemented 2026-09-06 against the [agreed specification](load-calculator-spec.md).
This is an executable policy experiment under `scripts/load_calculator`, outside
the production package. It produces a local review artifact. It does not connect
to the database, generate Hevy requests, or alter Automatic sync eligibility.

The response-model experiment (local research: `load-response-experiment.md`) did not establish a
useful changed-prescription formula. This implementation therefore exercises the
agreed deterministic rules and makes missing policy or evidence visible.
It does not claim validated recommendations at hypothetical new weights.

## Run it

From the repository root:

```bash
uv run python -m scripts.load_calculator docs/research/load-calculator-example.json
uv run python -m scripts.load_calculator docs/research/load-calculator-example.json --output /tmp/load-review.json
uv run python -m scripts.load_calculator --schema
```

The [example request](load-calculator-example.json) is synthetic: three working
Sets of 8–10 reps completed at 14 kg per dumbbell. The result selects 15 kg for
all three Sets, the next option in the combined dumbbell inventory.

The Python interface is `calculate(Calculation.model_validate(input_data))` from
`scripts.load_calculator`. `dumbbell_equipment()` supplies the agreed inventory;
`round_down(equipment, estimate_kg)` floors an externally supplied estimate to a
known option. The rounding function does not supply or validate a response model,
and is deliberately separate from proven-weight progression.

## Interpreted evidence contract

The Agent supplies exercise and setup identity, working/preparatory role, a stable
execution description, ordered round/part identities, numeric rep bounds or null
bounds for unresolved work, Coach loads, and original instructions. Include tempo,
unilateral execution, technique and material grouping differences in the execution
description so incompatible histories do not compare equal. Free-text instructions
are preserved; the calculator does not parse or resolve them.

Supply confirmed equipment options in ascending order and explicitly confirmed
adjacent `steps`. A partial cable inventory does not establish its remaining
weights or increments. The `recording_convention` describes per-hand, total, or
other load meaning. An option can retain a pounds label with its canonical
recorded kilograms and explicitly confirmed `recorded_aliases_kg`. There is no
generic conversion tolerance and no automatic station inference.

Every performance supplies a unique source `evidence_id`, date, its own interpreted
prescription/context, ordered results, and `conditions`. Use `normal` only when
the source interpretation supports normal rest and no unusual interruption;
`unknown`, `interrupted`, and `substitution` remain explicit evidence limitations.
Do not promote the earlier research cohort's screened working-role candidates to
confirmed working performances automatically.

Planned and historical preceding-work context is retained as text. Record timer
purpose and order uncertainty there; completion taps and configured timers do not
establish measured recovery. Optional whole-number RPE is retained in performed
efforts. Neither context nor RPE changes numeric selections.

The artifact embeds the request, per-effort load and equipment label, Coach/policy
provenance, selected evidence identifiers, explanation, provisional status, and
unresolved reasons. It contains no probability or confidence percentage. A nonempty
`unresolved` list requires further interpretation even when a held or provisional
load is present. This artifact is not an existing sync-review apply request.

## Executable behavior

| Case | Result |
| --- | --- |
| Explicit Coach loads | Preserve them exactly, including zero; partially filled prescriptions leave other efforts unresolved |
| Straight working Sets all at upper bound | Increase the shared weight by one confirmed step |
| Reps within range or minor shortfall | Hold |
| Two consecutive substantial shortfalls at the same weight and prescription | Reduce one confirmed step |
| Substantial shortfall immediately after a proven next-step increase | Restore the previous successful weight |
| Completed two-part Drop sequence | Increase both parts together across every round |
| Failed new drop increase with successful first efforts | Keep the first weight and restore the previous drop weight |
| Complete the staged sequence | Retry only the drop increase when its original failed-increase evidence is available |
| Numeric ladder | Preserve per-effort loads for the same prescription; flag progression as undecided |
| Preparatory work | Preserve per-effort targets; flag exposure count and calendar boundary as undecided |
| Changed prescription | Return unresolved; never substitute an old exact match for more recent changed work |
| Only stale same-prescription history | Offer its load profile as an explicitly provisional starting point |
| Open-ended work, unsupported drop structure or unagreed drop failure | Return unresolved |
| Unknown equipment option or required adjacent step | Return unresolved |

Substantial shortfall follows the spec: first Set below its lower bound, or any
later Set at least two below it. The immediate straight rollback uses this same
predicate as the experimental interpretation of “proves too heavy”; a minor
shortfall continues to hold.

## Conservative experimental choices

- Compare exact interpreted exercise, setup, role and execution context. Select
  up to three prior-date exposures within an inclusive 42-day window; no averaging
  or recency coefficients are needed for these progression rules. The newest
  exposure governs the current prescription and load. If no recent exposure
  exists, consider only the latest stale exposure.
- Exclude evaluation-date and future results. Multiple retained exposures on one
  date leave order unresolved. This date-level rule avoids claiming precise
  ordering from unreliable Set taps.
- Retain uncertain exposures as barriers rather than silently bridging two
  shortfalls across them. A missing/interrupted newest exposure blocks a new
  recommendation. An invalid prior exposure blocks a two-exposure adjustment and
  remains in the artifact's unresolved evidence.
- Preserve numeric ladders and preparatory sequences without inventing their
  undecided progression rules. Passing a four-week date boundary alone never
  increases preparatory loads.
- The two-part drop policy requires the same descending load profile in each
  round. Other part counts stay explicit. A staged retry requires original
  success, failed increase, and staged success in the available recent evidence;
  missing origin evidence leaves the staged decision unresolved.
- Partial Coach loads are preserved without filling the other efforts from an
  unconstrained history calculation.

These choices make ambiguous cases executable without silently accepting the
remaining design decisions. They are review behavior for this experiment, not
new Athlete-approved product rules.

## Validation and next boundary

Behavioral tests cover the specification examples, isolated equipment inventories
and aliases, role separation, missing evidence, chronology, stale history,
optional RPE, preserved context, JSON output, and malformed-input rejection:

```bash
uv run pytest tests/load_calculator -q
uv run ruff check scripts/load_calculator tests/load_calculator
uv run ruff format --check scripts/load_calculator tests/load_calculator
uv run ty check scripts/load_calculator --config 'src.include = ["scripts/load_calculator"]'
uv run pydoclint scripts/load_calculator
```

This validates implemented policy behavior on synthetic examples, not prediction
quality or optimal kilograms. Next work is an audited source-to-contract adapter
and historical policy replay with explicit role/setup provenance. Changed-
prescription load selection still needs stronger empirical evidence and
prospective validation. Production integration, preparatory exposure settings,
and promotion criteria remain separate decisions.
