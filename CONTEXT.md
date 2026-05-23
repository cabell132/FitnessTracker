# Fitness Tracker Context

This context defines the project vocabulary for syncing Coach prescriptions and Athlete performed results across True Coach, Hevy, Apple Health, and the local tracker. It exists so agents use the same domain terms when changing sync, review, and backfill workflows.

## Language

### Core training records

**Routine**:
A Hevy prescription the Athlete can perform in the future.
_Avoid_: Workout template, program item

**Workout**:
A performed training session recorded in True Coach, Hevy, Apple Health, or the local tracker.
_Avoid_: Routine, session blob

**Workout Item**:
A single prescribed or performed item inside a True Coach or local tracker Workout.
_Avoid_: Exercise row when the item may be a Circuit, AMRAP, or Choice

**Set**:
A structured performed or prescribed effort within a Workout Item or Hevy exercise block.
_Avoid_: Rep row, result line

**Coach prescription**:
The Coach-authored workout text that defines intended exercises, targets, rest, and structure.
_Avoid_: Athlete result, history

**Athlete feedback**:
Athlete-provided comments or post-workout Routine changes that may inform future prescriptions after review.
_Avoid_: Source of truth, automatic prescription update

**Performed result**:
The structured evidence of what the Athlete actually did.
_Avoid_: Prescription, plan

### Sync workflows

**Automatic sync**:
The unattended workflow that imports source data, updates the local tracker, and applies only policy-safe mutations.
_Avoid_: Review workflow, manual sync

**Review workflow**:
An artifact-producing workflow where ambiguous mappings or mutations are inspected before apply.
_Avoid_: Direct sync, silent mutation

**Apply**:
The mutation step that consumes validated review artifacts and writes to Hevy, True Coach, or the local tracker.
_Avoid_: Review, planning

**Review artifact**:
A durable file produced by a review workflow that records plans, decisions, validation, requests, reports, or manifests.
_Avoid_: Temp file, cache

**Agent decision**:
An explicit editable choice made by an Agent to resolve ambiguity before apply.
_Avoid_: Deterministic evidence, inferred default

### Routine creation and backfill

**Routine creation**:
The workflow that turns a future True Coach Workout prescription into a Hevy Routine.
_Avoid_: Workout backfill, result sync

**Routine replacement batch**:
The set of due Routine creation plans that replace the Athlete's current Hevy Routine menu together.
_Avoid_: Partial routine refresh, routine sync batch

**Routine source marker**:
The embedded True Coach Workout id on a disposable Hevy Routine used to link the later performed Hevy Workout back to its source prescription.
_Avoid_: Routine link, persisted Routine identity

**Routine batch marker**:
The marker that identifies which Routine replacement batch created a disposable Hevy Routine.
_Avoid_: Routine identity, source marker

**Workout backfill**:
The workflow that creates or links a historical Hevy Workout from an already-completed True Coach Workout.
_Avoid_: Routine creation, prescription sync

**Backfilled Workout**:
A Hevy Workout created from historical performed work rather than performed live in Hevy.
_Avoid_: Routine, planned workout

**Synthetic tracker Workout Item**:
A local tracker Workout Item created during split backfill so generated Hevy rows have stable one-to-one local links.
_Avoid_: Request-only row, duplicate source item

### Circuit language

**Circuit**:
A Coach-authored multi-exercise block intended to be performed as a grouped sequence.
_Avoid_: Generic placeholder exercise

**AMRAP**:
A time-boxed or round-based multi-exercise block where the Athlete performs as much work as prescribed in the given structure.
_Avoid_: Freeform notes

**Split Circuit**:
A Circuit or multi-exercise AMRAP represented as multiple concrete Hevy exercise blocks with shared grouping intent.
_Avoid_: Circuit placeholder, unsplit block

**Superset group**:
The Hevy grouping used to keep split Circuit or AMRAP exercises together.
_Avoid_: Circuit id, block id

### Result sync and feedback

**Result sync**:
The workflow that transfers performed Hevy Workout results back to True Coach.
_Avoid_: Routine sync, backfill

**Routine feedback**:
A reviewable difference between a performed Hevy Workout and its source Routine that may affect future prescriptions.
_Avoid_: Performed result, automatic Routine truth

**Routine feedback review loop**:
The reviewed workflow that classifies Routine feedback and turns confirmed Routine generation defects into fixes or tracked work.
_Avoid_: Routine update sync, autonomous Routine learning

**Routine generation defect**:
Routine feedback showing that Routine creation contradicted Coach prescription evidence or established project rules.
_Avoid_: Preference, session substitution

**Routine preference signal**:
Routine feedback showing an Athlete default that may shape future prescriptions when Coach prescription evidence is silent.
_Avoid_: Bug, performed result

**Routine feedback ledger**:
A durable record of classified Routine feedback whose entries may be observed, accepted, promoted, or rejected.
_Avoid_: Defaults table, issue list, automatic learning store

**Routine feedback review**:
An artifact-backed review of one Routine feedback case whose accepted classifications may be written to the Routine feedback ledger.
_Avoid_: Live Routine sync, direct Routine update

**Session-only substitution**:
Routine feedback showing an exercise change made for a specific performed session rather than as a durable prescription preference.
_Avoid_: Exercise mapping fix, Routine preference

**Completion status**:
Whether the True Coach Workout should be marked complete after result sync.
_Avoid_: Sync success, apply success

## Durable workflow rules

- A **Routine** is a prescription; a **Workout** is performed work.
- **Routine creation** creates Hevy Routines from Coach prescriptions; **Workout backfill** creates or links historical Hevy Workouts from performed results.
- Legacy direct **Routine creation** is retired; `SyncService.create_hevy_routine()` applies through `TrueCoachToHevyReviewService`, and the old direct True Coach to Hevy syncer must fail before placeholder allocation, LLM parsing, or direct Hevy mutation can run.
- A **Routine replacement batch** is the unit of automatic Hevy Routine replacement.
- Hevy **Routines** are disposable; durable linkage comes from the **Routine source marker** carried into the later performed Workout, not from persisting Routine identity.
- During migration, the **Routine source marker** should be written to both the Routine title and notes; notes are the canonical future location.
- **Routine creation** from True Coach requires a **Routine source marker**; missing markers block apply.
- A disposable Hevy **Routine** created by **Automatic sync** should carry a **Routine batch marker** so replacement can distinguish old generated Routines from newly-created Routines.
- When there are no due Workouts, there is no **Routine replacement batch** and **Automatic sync** must not clear existing Hevy **Routines**.
- **Workout backfill** uses local tracker **Workout**, **Workout Item**, and **Set** rows as primary performed-result evidence.
- Ambiguity in **Workout backfill** belongs in **Agent decisions**, not by rewriting deterministic plans.
- **Review artifacts** are the audit trail for ambiguous or brittle workflows; **Apply** consumes validated artifacts rather than silently regenerating intent.
- **Result sync** must not mark a True Coach Workout complete while known performed Hevy items remain unresolved.
- Rest periods for **Routine creation** come from the **Coach prescription**, falling back to static defaults; they do not come from training history.
- LLM-derived Routine structure may inform review, but it must not make **Automatic sync** consider **Routine creation** safe to apply.
- Placeholder Hevy templates are not safe for automatic **Routine creation**; missing concrete exercise mappings require review.
- A True Coach exercise to Hevy template mapping may be valid only for a specific prescription mode; **Routine feedback** must distinguish bad mappings from mode/template incompatibility.
- **Split Circuit** planning is shared between **Routine creation** and **Workout backfill**, but each workflow adapts the plan to its own output shape.
- A backfilled **Split Circuit** must contain only performed work; clearly omitted exercises remain review evidence, not created Hevy rows.
- Named replacement exercises in a backfilled **Split Circuit** require an **Agent decision**.
- **Synthetic tracker Workout Items** are created only during validated apply or repair, not during side-effect-free review generation.
- **Routine feedback** is reviewable prescription-shaping signal; load, rep, and cardio-duration changes remain low-signal performed results unless explicitly promoted.
- **Automatic sync** may perform **Routine creation** only when the generated plan has no warnings or blockers; otherwise it must produce **Review artifacts** for review.
- **Automatic sync** must not clear existing Hevy **Routines** unless replacement **Routine creation** plans are ready to apply safely.
- **Automatic sync** should clear only disposable Hevy **Routines** that carry a **Routine source marker**.
- **Automatic sync** treats due **Routine creation** as one replacement batch: if any due Workout requires review, it applies none of the due Routines automatically.
- A failed **Routine replacement batch** must not leave the Athlete with a partial Hevy Routine menu.
- When a due **Routine creation** batch requires review, **Review artifacts** should be written for every due Workout in the batch, including plans that are individually safe.
- **Routine creation** review artifacts should record whether each plan was automatic-safe and why review was required.

## Relationships

- A **Coach prescription** may produce one **Routine** through **Routine creation**.
- A **Routine replacement batch** contains one or more due **Routine creation** plans.
- A **Routine** carries one **Routine source marker** when it was created from a True Coach Workout.
- A **Routine replacement batch** has one **Routine batch marker** shared by its generated Routines.
- A **Workout** contains one or more **Workout Items**.
- A **Workout Item** may contain one or more **Sets**.
- A **Workout backfill** consumes one completed True Coach **Workout** and may create or link one **Backfilled Workout**.
- A **Review workflow** produces **Review artifacts**.
- **Apply** consumes validated **Review artifacts** and performs mutations.
- An **Agent decision** resolves ambiguity recorded in **Review artifacts**.
- A **Split Circuit** contains multiple generated exercises that share one **Superset group**.
- A backfilled **Split Circuit** may create **Synthetic tracker Workout Items** for generated performed exercises.
- **Result sync** transfers **Performed results** from Hevy to True Coach and may update **Completion status**.
- **Routine feedback** may influence future **Coach prescription** defaults only after review.

## Example dialogue

> **Dev:** "This completed True Coach **Workout** has a Circuit. Should we create a Hevy **Routine** first?"
> **Domain expert:** "No. Because it is already completed, this is **Workout backfill**. Generate review artifacts from performed results, use an **Agent decision** for any ambiguous replacement, and only create a **Backfilled Workout** during **Apply**."
>
> **Dev:** "If the Athlete skipped one exercise in the **Split Circuit**, do we still create a row for it?"
> **Domain expert:** "No. Omitted exercises remain review evidence, but the backfilled Hevy Workout and any **Synthetic tracker Workout Items** represent performed work only."

## Flagged ambiguities

- "Workout" may refer to either a True Coach planned/completed item, a Hevy logged session, an Apple Health interval, or a local tracker row; use the source name when the distinction matters.
- "Routine" must mean a Hevy prescription, not a completed Workout.
- "Sync" is too broad by itself; prefer **Automatic sync**, **Review workflow**, **Routine creation**, **Workout backfill**, or **Result sync**.
- "Circuit" and "AMRAP" may be source prescription structures; **Split Circuit** is the project term for representing them as concrete grouped Hevy exercises.
