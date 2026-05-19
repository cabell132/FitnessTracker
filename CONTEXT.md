# Fitness Tracker

A personal system that keeps a Coach-authored training plan and the Athlete's
logged results in sync between True Coach and Hevy.

## Language

### Actors

**Athlete**:
The person who performs the training and owns this system.
_Avoid_: user, client — the Athlete is True Coach's "client", but "client" here means an API client.

**Coach**:
The personal trainer who authors training plans for the Athlete.
_Avoid_: trainer, PT

### Platforms

**True Coach**:
The third-party platform where the Coach authors training plans — system of record for the plan.

**Hevy**:
The third-party platform where the Athlete logs training — system of record for results.

### Training concepts

**Routine**:
A planned, not-yet-performed training session — a prescription. In Hevy terms, a routine.
_Avoid_: plan, template, workout

**Routine feedback**:
An Athlete-approved update to a Hevy Routine after completing a Workout, used as evidence for improving future generated Routine prescriptions without treating ordinary performed results as new Coach intent.
Pure load or rep value changes are low-signal by default; set-count changes and set-type changes are reviewable feedback because they alter Routine structure.
Warmup-row additions are structural Routine feedback, but they remain
review-required because they may reflect a one-off Workout choice rather than a
future prescription default.
Routine feedback review should classify differences by signal: template
changes, rest period changes, notes changes, set-count changes, and set-type
changes are shown by default; pure load changes, pure rep value changes, and
performed cardio durations on distance sets are low-signal unless explicitly
requested.

**Workout**:
A single training session that has been performed and logged.
_Avoid_: session, routine

**Workout backfill**:
Creating a logged Hevy Workout from an already-completed True Coach Workout
that was not originally recorded in Hevy. Backfill is historical result
transfer, not Routine creation.
Every performed Workout Item included in a backfilled Hevy Workout must resolve
to a concrete Hevy exercise template. Placeholder items may be omitted only when
they represent non-exercise context such as rest notes.
A completed backfill links the created Hevy Workout and its included exercise
blocks back to the existing local tracker rows, so the local tracker records
that the historical Workout has been transferred.
Backfilled Hevy Workouts include the source True Coach Workout id as an
idempotency marker, so retries can detect or repair an existing remote backfill
instead of creating a duplicate.
Backfill timing may be inferred from Apple Health evidence such as nearby
workout intervals and heart-rate patterns. Timing inference is a review
judgement, not a silent automatic fact; if confidence is too low, the timestamp
should remain unset until the Athlete or Agent chooses it.
The deterministic backfill plan is an audit trail of local source data. Agent or
Athlete judgement belongs in editable request or decision artifacts, not by
rewriting the deterministic plan.

**Performed results**:
The Athlete's completed set outcomes for a Workout, such as load, reps,
distance, duration, and effort. For Workout backfill, performed results are the
data being transferred; Coach-authored prescription text remains context for
review and notes.
Cardio durations added after completing a Routine, such as completed Rowing
Machine split times, are performed results by default and should not become
future Routine duration targets unless the Athlete explicitly promotes them.
When performed-result text cannot be fully represented in Hevy's structured set
fields, the raw text is preserved in Hevy exercise notes.
Exercise notes should preserve non-structured context and Athlete feedback, not
duplicate values already represented in structured Hevy set rows.

**Choice Workout Item**:
A Coach-authored Workout Item where the Coach offers multiple movement options
and the Athlete's result text identifies which option was performed. During
Workout backfill, the performed exercise is selected from the Athlete's result
text rather than the Coach's generic choice wording.
If the Athlete performed multiple options, the backfill may split one Choice
Workout Item into multiple Hevy exercise blocks. Metrics that Hevy cannot store
structurally for those blocks remain in notes.
Ambiguous Choice Workout Item mappings are resolved as explicit backfill
decisions that select the performed Hevy exercise template.

**Down Regulate**:
A Coach-authored breathing exercise normally performed at the end of a Workout.
It is performed work, not a note-only cooldown marker. When no more specific
performed result exists, the Athlete treats it as 4 minutes.

**Workout Item**:
One exercise prescription within a True Coach plan — the unit the Coach writes.

**Template selection override**:
An item-level correction where the wording of a True Coach Workout Item implies a
more specific Hevy exercise template than the default exercise link. The override
applies to the generated Routine item only; it does not change the permanent
True Coach to Hevy exercise link.
When Coach notes materially change the movement, such as "Use handles" on a
rope-named item, Routine feedback may correct the selected Hevy template rather
than preserving the original name-based mapping. Notes disappearing after an
in-workout Hevy exercise replacement are a Hevy app artifact, not necessarily
Athlete intent to drop Coach context.
Whether a note-driven replacement becomes a permanent exercise link, a
Template selection override, or a one-off correction is a case-by-case Athlete
decision and must not be applied silently.

**Exercise replacement artifact**:
A Hevy behavior where replacing an exercise while performing a Workout may drop
Routine notes and populate set values from the replacement exercise's history,
making notes and load changes lower-signal than the template replacement itself.

**Mixed-mode prescription**:
A single True Coach Workout Item that prescribes materially different set modes
for the same movement, such as timed isometric holds followed by rep-based sets.
When syncing to Hevy, a mixed-mode prescription should become multiple Routine
exercise blocks when the phases can be split deterministically. Split phases may
require different Hevy exercise templates when their set modes differ, such as a
duration-capable template for isometric holds and a reps-capable template for
dynamic reps.
Generated Hevy notes may be phase-specific, but the original Coach wording
remains the source text for traceability.

**Build work**:
Coach guidance to ramp or feel out load before the prescribed working sets, such
as "build weight then". Build work is not a concrete warmup prescription unless
the Coach gives exact sets, reps, load, or duration.

**Athlete-history enrichment**:
A calculated logging default derived from the Athlete's previous Hevy Workouts,
such as a suggested load for a rep target. It is not a Coach prescription and
must remain distinguishable from values explicitly written by the Coach. When
confidence is high, enriched loads should be written into generated Hevy Routine
sets as real values, with internal provenance marking them as history-derived.

**Rep range target**:
When a Coach prescription gives a rep range but Hevy requires a single rep value,
the Athlete uses the upper bound as the structured target. The upper bound is a
progression target: if the Athlete completes all prescribed sets at that target,
they consider increasing the load next time.

**Plus-set prescription**:
A Coach prescription such as "3 x 10+10" or "3 x 10>10" means each prescribed
set has multiple dropset parts. In Hevy this should be represented as alternating
normal and dropset rows, such as normal 10, dropset 10, repeated for each
prescribed set.

**Dropset load enrichment**:
Athlete-history enrichment for a Plus-set prescription. Previous matching
dropset history is preferred; if it is missing, the system may calculate a
conservative dropset load from the normal-set load.

**Each-side marker**:
Coach shorthand such as "ES" means each side. It should be preserved in Hevy
notes and should not multiply the number of generated Hevy set rows.

**Execution marker**:
Coach wording that changes how the Athlete performs a set without changing the
number or type of generated Hevy set rows, such as "alternating" or RIR targets.
Execution markers should be preserved in notes.

**Circuit block**:
A Coach-authored Workout Item that contains multiple movements performed as a
round or conditioning sequence. When syncing to Hevy, a Circuit block should
become multiple generated Routine exercise blocks in one superset when its
movements can be identified and mapped deterministically; otherwise it remains
review-required rather than silently becoming a generic placeholder. Each
generated Routine exercise block should receive one set row per prescribed
round, with movement-specific targets where parseable. If any movement in a
split Circuit block cannot be mapped to a concrete Hevy exercise template, the
whole split is review-blocked rather than partially synced. Split Circuit blocks
use the same Hevy superset id stream as Coach-authored supersets: a standalone
Circuit block receives the next available superset id, while a Circuit block
inside an existing Coach-authored superset inherits that superset id. Movement
boundaries inside a Circuit block should be identified only from deterministic
list structure such as line breaks, bullets, numbered lines, or clear comma
lists; uncertain movement boundaries are review-blocked. A split Circuit block
must have a deterministic round count; missing or ambiguous round counts are
review-blocked. A split Circuit block may contain mixed target types because
each generated Hevy exercise block owns its own set rows. Unsupported or
ambiguous target details stay in that movement's notes. Each generated movement
block should preserve the original Circuit block wording in notes for
traceability. Split Circuit movements must resolve to concrete Hevy exercise
templates; generic placeholder templates should not be used for them. A
single-movement Circuit block remains one Routine exercise block rather than a
one-item superset. Rest between rounds should be represented as the rest period
on the final generated movement block in the circuit round. A movement duration
may be represented as that movement's rest period when the duration is the
Athlete-facing timer for the movement, such as a plank, but round-level circuit
rest takes priority over movement duration on the final movement. Cardio machine
durations, such as cycling for time, should not be represented as rest periods.
When a movement duration is structurally supported by Hevy, it should remain a
duration set target even if it is also used as that movement's rest period.
Movement-level rest should attach to the preceding generated movement block;
round-level circuit rest still takes priority on the final movement. Rest-only
lines in a Circuit block are rest metadata, not generated movements.

**AMRAP block**:
A Coach-authored Workout Item performed for as many rounds or reps as possible.
A multi-movement AMRAP should be treated as a Circuit block; a single-movement
AMRAP should remain one Routine exercise block with the AMRAP instruction
preserved in notes. For time-boxed multi-movement AMRAPs, each generated
movement block should default to half the number of cap minutes, rounded down,
with a minimum of one set row; the time cap remains in notes.

**Substitution instruction**:
Coach guidance that names alternatives when equipment or conditions differ.
Substitution instructions should stay in notes and should not automatically
change the selected Hevy exercise template.

**Rest period**:
The recovery time *prescribed* for an exercise — a single per-exercise value on a Routine. It is a prescription, not an outcome: Hevy never records the rest actually taken during a Workout.
A simple single rest value may be structured into Hevy's exercise rest period;
complex or per-set rest instructions should remain in notes.
Rest period edits made through Routine feedback are high-signal for future
Routine generation. Explicit Coach rest text in the True Coach prescription is
higher priority than Athlete feedback and should be structured when it is a
simple single rest value.
When Coach text is silent, Athlete Routine feedback may establish a reusable
default Rest period for the selected Hevy exercise template.

## Relationships

- A **Coach** authors plans on **True Coach**
- The system converts a True Coach plan into a Hevy **Routine** for the **Athlete**
- The **Athlete** performs the Routine on **Hevy**, producing a **Workout**
- A **Workout** is synced back to **True Coach** as results for the **Coach**

## Example dialogue

> **Athlete:** "When Ross writes a session, does it become a Hevy Workout?"
> **Domain expert:** "No — it becomes a Hevy **Routine**. A Routine is the prescription.
> It only becomes a **Workout** once the Athlete performs and logs it. The Workout is
> what syncs back to the Coach."

## Flagged ambiguities

- "rest timer" (Athlete's words) resolved to **Rest period** — one per-exercise value on a Routine, not a per-set timer. Resolved: rest is plan-side only; it is never measured or stored on a performed Workout.
- "client" is overloaded — the person is the **Athlete**; "client" is reserved for API clients.
- "create a new exercise" vs the current placeholder-exercise stand-in — unresolved, pending feature design.
