# Load calculator: agreed behavior and experimental boundary

Consolidated 2026-09-05 from the Athlete interview. This is a local specification,
not a published PRD or implemented production feature. Domain terminology is in
[CONTEXT.md](../../CONTEXT.md). Experimental choices below are identified separately
from agreed behavior.

Companion research files identified as local below are unpublished workspace
artifacts and are not included in this policy-experiment PR.

## Objective

Recommend achievable equipment loads for the **entire Coach prescription**, using
recent Athlete performance and repeatable calculations. Support changed set/rep
prescriptions, not only copying the most recent exact match or estimating a maximum.
For a new `4 × 8–10` prescription, target at least eight reps in every Set. Reaching
ten in every Set is the progression trigger, not the initial requirement.

Completed prescribed reps establish achieved performance, not maximum capacity or
proof that the final Set was challenging. The initial system must work without RPE.

## Scope and responsibilities

- Include straight Sets, numeric rep ladders, Drop sequences, and Preparatory work.
  A straight-only product was explicitly rejected. Unsupported/open-ended structures
  must remain explicit unresolved cases, not silently become ordinary straight Sets.
- Straight working Sets share one recommended weight by default. Other structures
  can receive separate loads for each ordered effort. Preserve rounds, linked drop
  parts, unilateral instructions, tempo, and equipment weight conventions.
- The Agent interprets the Coach prescription, exercise identity, Equipment setup,
  preparatory/working role, grouping, and known order changes from source evidence.
  The calculator owns numeric selection and an explanation of its evidence.
- Explicit Coach loads take precedence under existing Routine creation behavior;
  do not silently replace them with generated estimates.
- Recommendations enter the existing review/apply workflow. This specification
  does not introduce direct remote writes or change Automatic sync eligibility.

## Agreed progression

| Situation | Behavior |
| --- | --- |
| Same straight prescription, all Sets at upper rep bound | Increase by one available equipment step |
| Results inside the rep range | Hold weight while building reps |
| Minor shortfall, e.g. `10, 9, 7` for `3 × 8–10` | Hold |
| First Set below lower bound, or any later Set at least two below lower bound | Substantial rep shortfall |
| Two consecutive substantial shortfalls at an established weight and same prescription | Reduce one equipment step, then reassess |
| Newly increased weight proves too heavy | Allow immediate rollback to previous successful weight |
| New-prescription estimate between available weights | Round down; this does not replace the next-step rule for proven-weight progression |

Shortfall interpretation assumes normal rest and no unusual interruption. Missing
records, deliberate substitutions, and an interrupted Workout do not independently
prove muscular inability. Consecutive means comparable performed exposures, not
elapsed calendar days. Exact interruption handling remains a design edge case.

### Preparatory work

Keep it separate from working-strength evidence. Increase each preparatory Set's
target by one equipment step after roughly four weeks of actual performances at
unchanged weights with consistently completed reps. Four weeks without performing
the exercise does not trigger an increase. The minimum exposure count and exact
calendar boundary have not been chosen.

The Athlete confirmed the opening Straight Arm Pushdown, Face Pull, Half Kneeling
Cable Pallof Press, and Rope Hammer Curl blocks in Pull & Core on 26 August and
2 September as preparation. This is contextual, not a permanent exercise-name rule.
Preserve increasing-weight preparatory sequences such as `15, 12, 10` reps.

### Dropsets

Assess linked efforts across all rounds. For three rounds of `10 + 10`, first
efforts of `10, 10, 10` and drops of `10, 10, 7` do not justify an increase.

After full completion at narrow-station `24 → 21.5 kg`, first try one step up on
both parts: `26 → 24 kg`. If every first effort succeeds but drops fall short,
retain `26 kg` and roll the drops back to `21.5 kg`. Retry the drop increase after
completing the whole sequence. This staged exception applies to the failed new
increase; it does not replace whole-sequence completion as the ordinary trigger.
Other failure combinations and open-ended `max` parts remain unresolved.

## Equipment and history

- Combine the Athlete's interchangeable dumbbell collections: 1–10 kg by 1 kg,
  5–20 kg by 2.5 kg, and 6–50 kg by 2 kg. Use the sorted union, not one universal step.
- Keep wide and narrow cable stations distinct. Confirmed observed narrow weights:
  `17, 19.5, 21.5, 24, 26, 28.5 kg`; wide: `18, 20.5, 22.5, 25, 27 kg`.
  These are incomplete inventories. Match historical sequences to infer station
  where supported; do not assume every future weight is known.
- Machine labels may use pounds while Recorded load uses rounded kilograms.
  Preserve that mapping; small conversion differences are not strength progression.
  Exact matching tolerance, stack inventories, and barbell/plate increments remain
  to be established. Do not invent them from generic equipment categories.
- Establish current strength from up to three comparable same-exercise, same-setup
  working performances within six weeks, emphasizing the newest. Recency coefficients
  are experimental; the window and maximum count are agreed starting settings.
- Recent different-prescription results take precedence over an old exact match.
  Older history can inform the relationship between prescriptions.
- If only stale history exists, offer an explicitly provisional starting weight
  from that exercise. Do not transfer current strength gains from related exercises.
- Preparatory results inform preparatory progression, not working-strength estimates.

## Fatigue and effort

Keep exercise order and preceding work as context; numerical preceding-work correction
is zero until a model demonstrates predictive benefit. This is insufficient evidence,
not zero physiological fatigue. See the expanded fatigue investigation (local research: `preceding-work-expanded.md`).

RPE is optional. The Athlete will start logging whole-number RPE on the final working
Set when able to judge it, leaving uncertain ratings blank. Collect before using it
to change recommendations; test incremental predictive value against the baseline.
Do not infer effort from rep completion, HR spikes, or absent ratings. No required
failure testing, Watch replacement, or additional logging beyond this was agreed.

The database now contains Set completion timestamps and configured exercise rest
timers; see the timing analysis (local research: `set-timing-analysis.md`). Some completion taps
appear grouped or delayed, and configured timers are not measured rest. Do not
equate completion gaps with recovery intervals or infer exact execution order from
unreliable taps. Earlier experiments used snapshots without these fields. The last
queried Apple Health coverage stopped in 2025; see the WHOOP note (local research: `whoop-fatigue-and-load.md`).

Timer purpose is essential: the Athlete also uses `rest_seconds` for Hold timers,
Side timers, and Timer handoffs under the Routine creation instructions. Resolve
purpose from the prescription and surrounding group before treating a setting as
recovery. Unknown or conflicting timer purposes remain explicit. The Athlete
normally marks each Set after performing it to start the timer; this is the usual
logging habit, not a guarantee about every historical timestamp.

## Proposed calculation contract — to test, not yet a production interface

The Athlete supplied an earlier exercise catalogue; see the
catalogue assessment (local research: `exercise-catalogue-assessment.md`). It can supply proposed
family, modifier, equipment and muscle-role context through True Coach exercise IDs.
Its inferred activation scores and exercise-progression edges are not validated
fatigue coefficients or Athlete load-progression rules. Any predictive use needs
testing; preserve Workout-specific role and actual Equipment setup over catalogue
defaults. This proposed input does not authorize exercise substitution or transfer
of current strength across exercise variants.

Input: interpreted exercise/setup/role, an ordered prescription with round/part
identity, available load options and recording convention, historical performed
evidence, evaluation date, and planned preceding context.

Output: per-effort candidate loads (shared for straight Sets), evidence identifiers,
progression/hold/rollback reason, provisional status, and unresolved evidence.
If a probability is supplied, describe its endpoint and calibration. Do not invent
a confidence percentage or optimize against an arbitrary completion threshold.

Selection for a changed prescription requires a response model between candidate
load, reps, and number/structure of efforts. The first experiment compares recent
completion evidence with increasing model complexity: load change, then rep change,
then Set-count change. These are empirical candidates, not physiological equations.

## Validation and release boundary

1. Audit cohort, source provenance, roles, equipment and prescription parsing.
2. Replay chronologically; no target or future outcomes in its prediction or fit.
3. Evaluate all-effort lower-bound completion, reporting changed prescriptions
   separately. Upper-bound completion and substantial shortfalls are different
   outcomes and must not be conflated.
4. Compare on identical forecasts, with Workout-grouped uncertainty and a later-time
   evaluation segment. Retain simple baselines and report sparse structures honestly.
5. Historical completion at an observed weight is not the outcome at a hypothetical
   new weight. Validate a recommendation policy prospectively before claiming optimal
   kilograms or reliable automatic changes for new prescriptions.

No probability threshold, formula coefficients, or production fatigue/RPE adjustment
has been accepted. No production implementation or remote apply is part of this
specification-and-experiment task. The experiment's coverage limits do not narrow
the agreed product scope.

## Remaining decisions after experiments

Prefer concrete evidence over reopening the interview: coefficient/calibration
quality; sparse/new-exercise fallback; open-ended/max and non-numeric prescriptions;
other ladder/drop progression cases; equipment gaps and rounding; preparatory exposure
count; invalid/missing result handling; and criteria for promoting a model into use.

Results and runnable analysis: load-response experiment (local research: `load-response-experiment.md`).

Local implementation follow-up (2026-09-06): the
[policy experiment](load-calculator-prototype.md) now exercises deterministic
progression and equipment rules through interpreted JSON inputs and local review
artifacts. It preserves the production release boundary above; changed-prescription
models and undecided policies remain explicit unresolved cases.
