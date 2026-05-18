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
round or conditioning sequence. Circuit blocks should remain a single generated
Hevy block unless the Coach authored the movements as separate Workout Items.

**Substitution instruction**:
Coach guidance that names alternatives when equipment or conditions differ.
Substitution instructions should stay in notes and should not automatically
change the selected Hevy exercise template.

**Rest period**:
The recovery time *prescribed* for an exercise — a single per-exercise value on a Routine. It is a prescription, not an outcome: Hevy never records the rest actually taken during a Workout.
A simple single rest value may be structured into Hevy's exercise rest period;
complex or per-set rest instructions should remain in notes.

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
